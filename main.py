import os
import asyncio
import traceback
import logging
import re
import signal
import sys
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web, ClientSession

# --- FIREBASE / FIRESTORE INTEGRATION ---
import firebase_admin
from firebase_admin import credentials, firestore

# =================================================================================================
# 1. ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ И ОБЛАКА
# =================================================================================================

# Настройка сигналов для Linux/Render (защита от зомби-процессов)
if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Загрузка конфигурации Firebase
firebase_key_raw = os.getenv("FIREBASE_KEY")
app_id = "identity-lab-v7" 

if firebase_key_raw:
    try:
        cred_dict = json.loads(firebase_key_raw)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("✅ Firestore Cloud Storage: CONNECTED")
    except Exception as e:
        logging.error(f"❌ Firestore Init Error: {e}")
        db = None
else:
    logging.warning("⚠️ FIREBASE_KEY не найден. Данные будут храниться только в RAM.")
    db = None

# Импорт Cerebras AI
try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# Основные переменные конфигурации
TOKEN = os.getenv("BOT_TOKEN")
AI_KEY = os.getenv("AI_API_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
PORT = int(os.getenv("PORT", 10000))

WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013 # ID Александра Лазаренко

# Ресурсы проекта (Медиа и файлы)
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo1.jpg"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/Autopilot_System_Protocol.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни" 
CHANNEL_LINK = "https://t.me/metaformula_life"
SUPPORT_LINK = "https://t.me/lazalex81"

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация ИИ клиента
ai_client = None
if AI_KEY and CEREBRAS_AVAILABLE:
    try:
        ai_client = AsyncCerebras(api_key=AI_KEY)
        logger.info("✅ Cerebras AI Engine: ONLINE")
    except Exception as e:
        logger.error(f"❌ AI Engine Init Error: {e}")

class AuditState(StatesGroup):
    answering = State()

# Кэш для временного хранения данных (ускоряет работу веб-страниц)
diagnostic_cache = {}

# =================================================================================================
# 2. МЕТОДОЛОГИЯ: ВОПРОСЫ И ВАЛИДАЦИЯ
# =================================================================================================

QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни или в каком деле ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают того результата, на который ты рассчитываешь.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Какой ты теперь? Подбери 3–4 слова (например: спокойный, мощный, свободный). Как ты себя чувствуешь и как теперь смотришь на мир?",
    "📍 **Точка 3: Архивный режим.**\nКакая «мыслительная жвачка» крутится у тебя в голове, когда ты думаешь о переменах? Какие сомнения или доводы ты себе приводишь, чтобы оправдать текущую ситуацию?",
    "📍 **Точка 4: Сцена.**\nПредставь перед собой пустую сцену и вынеси на неё то, что тебе мешает (твой затык). Если бы оно было образом или предметом... на что бы оно могло быть похоже?",
    "📍 **Точка 5: Детекция сигнала.**\nПосмотри на этот предмет на той сцене перед собой. Где и какое ощущение возникает в теле (сжатие, холод, ком)? Опиши, что именно ты сейчас делаешь со своим телом?",
    "📍 **Точка 6: Биологическое Алиби.**\nТело всегда действует логично. Как ты думаешь, от чего тебя пытается защитить или уберечь эта телесная реакция при взгляде на препятствие?",
    "📍 **Точка 7: Реинтеграция.**\nКакое качество в поведении других людей тебя раздражает сильнее всего (наглость, навязчивость, грубость)? Если представить, что за этим качеством стоит какая-то скрытая сила — что это за сила? Как бы ты мог использовать её себе на пользу?",
    "📍 **Точка 8: Команда Автора.**\nТы готов признать себя Автором того, что происходит в твоем теле и твоей жизни, и перенастроить внутренний автопилот на реализацию твоих замыслов прямо сейчас?"
]

SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР ИДЕНТИЧНОСТИ IDENTITY LAB. 
Тон: Директивный, технический, научный. Обращайся только на "ТЫ".

ЗАДАЧА: Сформировать отчет.
1. АВТОРСТВО: Объясни, что пользователь САМ создает сигнал [ответ 5] ради защиты системы от [ответ 6].
2. РЕИНТЕГРАЦИЯ: Сила из [ответ 7] заперта в зажиме [ответ 5]. Мы её возвращаем.
3. МЕТАФОРМУЛА: В конце выдели жирным Код Активации:
«Я Автор. ПРИЗНАЮ, что сам создаю этот сигнал [ответ 5] — это мой ресурс. НАПРАВЛЯЮ его на активацию [Роль из ответа 2]»."""

def validate_input_robust(text, step):
    """Интеллектуальная проверка каждого ответа на осмысленность"""
    t = text.strip()
    # Пороги длины по шагам
    min_lens = {0: 10, 1: 5, 2: 10, 3: 4, 4: 5, 5: 5, 6: 5, 7: 2}
    if len(t) < min_lens.get(step, 3):
        return False
    
    # Проверка на гласные (защита от "ывмывм")
    vowels = re.findall(r'[аеёиоуыэюяaeiouy]', t.lower())
    if not vowels and step != 7: # В Т8 (готов?) допустимо "Да"
        return False

    # Проверка на повторы ("ааааа")
    if re.match(r'^(\w)\1+$', t):
        return False
        
    return True

def calculate_index(answers):
    """Расчет индекса автоматизма на основе маркеров в тексте"""
    text = " ".join(answers).lower()
    markers = ['не знаю', 'боюсь', 'страх', 'лень', 'тупик', 'тяжело', 'сжатие', 'ком', 'холод', 'ошибка']
    count = sum(1 for m in markers if m in text)
    return min(95, max(60, 72 + (count * 3)))

# =================================================================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (FIREBASE, AI, REMINDERS)
# =================================================================================================

async def track_user_action(user: types.User, status: str, extra: dict = None):
    """Сохранение данных в Firebase по пути /artifacts/{appId}/public/data/users/{userId}"""
    if not db: return
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(user.id))
        data = {
            "full_name": user.full_name,
            "username": user.username,
            "last_status": status,
            "last_activity": datetime.now(),
        }
        if status == "joined": data["created_at"] = datetime.now()
        if extra: data.update(extra)
        doc_ref.set(data, merge=True)
    except Exception as e:
        logger.error(f"Tracking error: {e}")

async def send_admin_alert(text: str):
    """Уведомления Александру"""
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown", disable_web_page_preview=True)
    except: pass

async def send_guide_document(message: types.Message):
    """Загрузка PDF с GitHub и отправка пользователю файлом"""
    try:
        async with ClientSession() as session:
            async with session.get(PROTOCOL_URL) as resp:
                if resp.status == 200:
                    pdf_bytes = await resp.read()
                    await message.answer_document(
                        document=types.BufferedInputFile(pdf_bytes, filename="Протокол_Дешифровки.pdf"),
                        caption="📘 Твой Гайд по рефакторингу биологического автопилота готов."
                    )
                else: raise Exception(f"HTTP {resp.status}")
    except Exception as e:
        logger.error(f"Guide sending failed: {e}")
        await message.answer(f"📥 Не удалось отправить файл напрямую. Скачай по ссылке:\n{PROTOCOL_URL}")

async def reminder_task(user_id: int):
    """Фоновая задача: напоминание через 2 часа, если аудит не завершен"""
    await asyncio.sleep(7200) # 2 часа
    try:
        if db:
            doc = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(user_id)).get()
            if doc.exists and doc.to_dict().get("last_status") == "audit_started":
                await bot.send_message(user_id, "🔍 Твой Автопилот пытается тебя остановить. Дешифровка коннектома прервана. Не дай системе откатиться назад, заверши аудит!")
    except: pass

async def get_ai_report(answers):
    """Генерация отчета через Cerebras AI с экспоненциальным бэкаффом"""
    if not ai_client: return "Я Автор. ПРИЗНАЮ силу своего сигнала."
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    
    for delay in [1, 2, 4]:
        try:
            resp = await asyncio.wait_for(ai_client.chat.completions.create(
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data_str}],
                model="llama-3.3-70b", temperature=0.4, max_completion_tokens=2500
            ), timeout=15.0)
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"AI Attempt failed: {e}")
            await asyncio.sleep(delay)
    
    await send_admin_alert("🚨 **Сбой ИИ!** Проверьте токены Cerebras.")
    return "Синхронизация ограничена. Помни: Я Автор. ПРИЗНАЮ силу своего сигнала."

# =================================================================================================
# 4. ШАБЛОН ВЕБ-ОТЧЕТА (PREMIUM CYBER-MYSTICISM)
# =================================================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Identity Lab: Personal Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; --text: #e5e5e5; }}
        body {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; overflow-x: hidden; }}
        .cyber-card {{ background: rgba(20, 20, 20, 0.95); border: 1px solid #333; border-left: 4px solid var(--gold); padding: 24px; border-radius: 8px; margin-bottom: 24px; box-shadow: 0 10px 30px -10px rgba(0,0,0,0.8); }}
        .btn-gold {{ background: linear-gradient(to right, #b4932c, #D4AF37); color: #000; font-weight: bold; padding: 14px 28px; border-radius: 6px; text-transform: uppercase; transition: all 0.3s; display: inline-block; }}
        .text-gold {{ color: var(--gold); }}
    </style>
</head>
<body class="p-4 md:p-8 max-w-4xl mx-auto selection:bg-yellow-900 selection:text-white">
    <header class="text-center mb-12 border-b border-gray-800 pb-8">
        <p class="text-xs text-cyan tracking-[0.3em] uppercase mb-2 font-mono animate-pulse">Neuro-Architecture System v10.0</p>
        <h1 class="text-5xl md:text-7xl font-bold text-gold mb-2 tracking-tight uppercase">IDENTITY LAB</h1>
        <p class="text-xl text-gray-400">Персональный отчет: <span class="text-white font-bold">{user_name}</span></p>
    </header>
    
    <main class="w-full">
        <div class="cyber-card flex flex-col md:flex-row items-center gap-8 justify-center">
            <div class="relative w-40 h-40">
                 <canvas id="statusChart"></canvas>
                 <div class="absolute inset-0 flex items-center justify-center flex-col">
                    <span class="text-3xl font-bold text-white">{idx}%</span>
                    <span class="text-[10px] text-gray-500 uppercase tracking-widest">Инерция</span>
                 </div>
            </div>
            <div class="text-center md:text-left">
                <h2 class="text-xl font-bold text-white mb-2 uppercase tracking-wide">Индекс Автоматизма</h2>
                <p class="text-gray-400 text-sm max-w-md italic">Ваша система работает в режиме «Биологического Алиби». Ресурс тратится на защиту гомеостаза.</p>
            </div>
        </div>

        <div class="cyber-card">
            <h2 class="text-xl font-bold text-white mb-6 border-b border-gray-800 pb-2 uppercase tracking-widest flex items-center">
                <span class="text-gold mr-3">⚡️</span> Нейро-Синтез Данных
            </h2>
            <div class="font-mono whitespace-pre-wrap text-gray-300 text-sm md:text-base leading-loose">
{report_text}
            </div>
        </div>

        <div class="text-center py-12 space-y-6">
            <p class="text-gray-500 text-xs uppercase tracking-[0.2em]">Окно пластичности открыто (4 часа)</p>
            <div class="flex flex-col md:flex-row gap-6 justify-center">
                <a href="{practicum_link}" class="btn-gold shadow-2xl hover:scale-105 transform transition">🚀 Запустить Практикум</a>
                <a href="{protocol_link}" class="border border-gray-700 text-gray-400 py-3 px-8 rounded uppercase font-bold text-sm hover:bg-gray-800 transition">📥 Скачать PDF</a>
            </div>
        </div>
    </main>
    <script>
        new Chart(document.getElementById('statusChart').getContext('2d'), {{
            type: 'doughnut',
            data: {{ 
                labels: ['Инерция', 'Автор'], 
                datasets: [{{ 
                    data: [{idx}, {inv_idx}], 
                    backgroundColor: ['#171717', '#D4AF37'], 
                    borderWidth: 0, 
                    cutout: '85%' 
                }}] 
            }},
            options: {{ plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }} }}
        }});
    </script>
    <footer class="mt-20 py-8 border-t border-gray-900 text-center text-[10px] text-gray-700 font-mono tracking-widest uppercase">
        © 2026 Identity Lab | Alexander Lazarenko
    </footer>
</body>
</html>
"""

# =================================================================================================
# 5. ОБРАБОТЧИКИ ТЕЛЕГРАМ (HANDLERS)
# =================================================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await track_user_action(message.from_user, "joined")
    
    # Проверка подписки
    is_sub = False
    try:
        m = await bot.get_chat_member(CHANNEL_ID, message.from_user.id)
        is_sub = m.status in ["member", "administrator", "creator"]
    except: pass

    await message.answer("Система загружается...", reply_markup=ReplyKeyboardBuilder().row(types.KeyboardButton(text="≡ МЕНЮ")).as_markup(resize_keyboard=True))
    
    kb = InlineKeyboardBuilder()
    if not is_sub:
        kb.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub"))
        cap = "👋 Лаборатория идентичности «Метаформула жизни»\n\nЯ — Мета-Навигатор. Подпишись на канал для синхронизации системы."
        await message.answer_photo(LOGO_URL, caption=cap, reply_markup=kb.as_markup())
    else:
        cap = "🧠 Система синхронизирована. Готов занять место Автора и начать аудит своего автопилота?"
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption=cap, reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "check_sub")
async def check_sub_cb(cb: types.CallbackQuery, state: FSMContext):
    m = await bot.get_chat_member(CHANNEL_ID, cb.from_user.id)
    if m.status in ["member", "administrator", "creator"]:
        await cb.answer("Доступ открыт!")
        await cmd_start(cb.message, state)
    else: await cb.answer("Подписка не найдена!", show_alert=True)

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 Панель управления:", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "run")
async def audit_init(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await track_user_action(cb.from_user, "audit_started")
    await send_admin_alert(f"👤 {cb.from_user.full_name} (@{cb.from_user.username}) начал аудит.")
    
    # Запуск таймера-напоминалки
    asyncio.create_task(reminder_task(cb.from_user.id))
    
    await state.update_data(step=0, answers=[])
    await cb.message.answer("🔬 Инициализация протокола. Будь предельно искренен с собой. Твоё тело — самый точный прибор.")
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0], parse_mode="Markdown")
    await state.set_state(AuditState.answering)

@dp.message(AuditState.answering)
async def process_answers(message: types.Message, state: FSMContext):
    if message.text == "≡ МЕНЮ" or message.text.startswith("/"): return
    
    data = await state.get_data()
    step, answers = data.get('step', 0), data.get('answers', [])
    
    # МГНОВЕННАЯ ВАЛИДАЦИЯ
    if not validate_input_robust(message.text, step):
        return await message.answer("⚠️ Твой ответ слишком короткий или не содержит смысла. Пожалуйста, напиши подробнее, чтобы система могла провести точную дешифровку.")

    answers.append(message.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step+1, answers=answers)
        await message.answer(QUESTIONS[step+1], parse_mode="Markdown")
        # Сохраняем прогресс шага в Firebase
        await track_user_action(message.from_user, f"step_{step+1}")
    else:
        # ЗАВЕРШЕНИЕ
        status_msg = await message.answer("🧠 **Дешифровка данных... 100%**")
        report = await get_ai_report(answers)
        idx = calculate_index(answers)
        
        diag_data = {
            "name": message.from_user.full_name,
            "report": report, 
            "index": idx, 
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        # Сохранение итогового результата
        await track_user_action(message.from_user, "audit_finished", diag_data)
        diagnostic_cache[message.from_user.id] = diag_data
        
        # Вывод отчета
        await status_msg.edit_text(report.replace('**', '*'))
        
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📊 ВЕБ-ОТЧЕТ", url=f"{RENDER_URL}/report/{message.from_user.id}"))
        kb.row(types.InlineKeyboardButton(text="⚡️ ПРАКТИКУМ", callback_data="go_practicum"))
        
        await asyncio.sleep(2)
        await message.answer("🎯 Аудит завершен. Твой персональный отчет готов:", reply_markup=kb.as_markup())
        await send_admin_alert(f"✅ {message.from_user.full_name} завершил аудит.")
        await state.clear()

@dp.callback_query(F.data == "go_practicum")
async def practicum_click(cb: types.CallbackQuery):
    await cb.answer()
    await track_user_action(cb.from_user, "practicum_clicked")
    await cb.message.answer(f"🚀 Твой доступ к состоянию Автора здесь:\n{PRACTICUM_URL}")

@dp.callback_query(F.data == "get_guide")
async def guide_click(cb: types.CallbackQuery):
    await cb.answer()
    await track_user_action(cb.from_user, "guide_requested")
    await send_guide_document(cb.message)

@dp.message(Command("admin_stats"))
async def cmd_admin_stats(message: types.Message):
    """Статистика из Firebase для Александра"""
    if message.from_user.id != ADMIN_ID or not db: return
    users = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").stream()
    stats = {"total": 0, "audit_started": 0, "audit_finished": 0, "buy_clicked": 0}
    for u in users:
        d = u.to_dict()
        stats["total"] += 1
        st = d.get("last_status", "")
        if "step_" in st or st == "audit_started": stats["audit_started"] += 1
        elif st == "audit_finished": stats["audit_finished"] += 1
        if d.get("practicum_clicked"): stats["buy_clicked"] += 1
    
    await message.answer(f"📊 **БАЗА КЛИЕНТОВ (IDENTITY LAB)**\n\n👥 Всего зашло: {stats['total']}\n⏳ Не закончили аудит: {stats['audit_started']}\n✅ Завершили полностью: {stats['audit_finished']}\n💰 Кликов по покупке: {stats['buy_clicked']}")

def get_main_keyboard():
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🚀 Начать Аудит", callback_data="run"))
    b.row(types.InlineKeyboardButton(text="📥 Скачать Гайд", callback_data="get_guide"))
    b.row(types.InlineKeyboardButton(text="⚡️ Практикум", url=PRACTICUM_URL))
    return b.as_markup()

# =================================================================================================
# 6. ВЕБ-СЕРВЕР (HEALTH & WEB-REPORTS)
# =================================================================================================

async def handle_home(r): return web.Response(text="Identity Lab System Active")

async def handle_report(request):
    try:
        uid = int(request.match_info['user_id'])
        # Сначала из RAM, потом из Firebase
        d = diagnostic_cache.get(uid)
        if not d and db:
            doc = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(uid)).get()
            if doc.exists: d = doc.to_dict()
        
        if d:
            html = HTML_TEMPLATE.format(
                user_name=d['name'], idx=d['index'], inv_idx=100-d['index'],
                report_text=d['report'].replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="<h1>Отчет не найден.</h1><p>Пройдите аудит в боте @meta_navigator_bot</p>", content_type='text/html', status=404)
    except: return web.Response(text="Ошибка доступа к данным.", status=500)

async def on_startup(bot: Bot):
    if RENDER_URL: await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Запуск/Синхронизация"),
        types.BotCommand(command="menu", description="Главное меню")
    ])
    await send_admin_alert("🚀 **Identity Lab v10.0 СИНХРОНИЗИРОВАН**\nFirebase Connected. AI Active. Webhook Online.")

def main():
    app = web.Application()
    app.router.add_get('/', handle_home); app.router.add_get('/report/{user_id}', handle_report)
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    try: main()
    except (KeyboardInterrupt, SystemExit): pass

