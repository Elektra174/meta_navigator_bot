import os
import asyncio
import traceback
import logging
import re
import signal
import sys
import json
from datetime import datetime
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

# Настройка сигналов для Linux/Render
if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Загрузка конфигурации Firebase
firebase_key_raw = os.getenv("FIREBASE_KEY")
app_id = "identity-lab-v6" # ID для структуры Firestore

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
    logging.warning("⚠️ FIREBASE_KEY не найден. Данные не будут сохраняться постоянно.")
    db = None

# Импорт Cerebras AI
try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# Основные переменные
TOKEN = os.getenv("BOT_TOKEN")
AI_KEY = os.getenv("AI_API_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
PORT = int(os.getenv("PORT", 10000))

WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013

# Ресурсы проекта
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo11.png"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/Autopilot_System_Protocol.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни" # Заглушка на ваш канал
CHANNEL_LINK = "https://t.me/metaformula_life"
SUPPORT_LINK = "https://t.me/lazalex81"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# AI Client
ai_client = None
if AI_KEY and CEREBRAS_AVAILABLE:
    try:
        ai_client = AsyncCerebras(api_key=AI_KEY)
        logger.info("✅ Cerebras AI Engine: ONLINE")
    except Exception as e:
        logger.error(f"❌ AI Engine Init Error: {e}")

class AuditState(StatesGroup):
    answering = State()

# =================================================================================================
# 2. ЛОГИКА ХРАНЕНИЯ (FIRESTORE)
# =================================================================================================

async def save_diagnostic(user_id, data):
    """Сохранение результатов аудита в базу данных"""
    if db:
        try:
            # Путь: artifacts/{app_id}/public/data/reports/{user_id}
            doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("reports").document(str(user_id))
            doc_ref.set(data)
            return True
        except Exception as e:
            logger.error(f"Firestore Save Error: {e}")
    return False

async def get_diagnostic(user_id):
    """Получение результатов из базы данных для веб-страницы"""
    if db:
        try:
            doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("reports").document(str(user_id))
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.error(f"Firestore Read Error: {e}")
    return None

# =================================================================================================
# 3. МЕТОДОЛОГИЯ: ВОПРОСЫ И ПРОМПТ
# =================================================================================================

QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни или в каком деле ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают результата.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Какой ты теперь? Подбери 3–4 слова (например: спокойный, мощный, свободный). Как ты себя чувствуешь?",
    "📍 **Точка 3: Архивный режим.**\nКакая «мыслительная жвачка» крутится у тебя в голове, когда ты думаешь о переменах? Какие сомнения ты себе приводишь?",
    "📍 **Точка 4: Сцена.**\nПредставь перед собой пустую сцену и вынеси на неё то, что тебе мешает (твой затык). На что бы оно могло быть похоже?",
    "📍 **Точка 5: Детекция сигнала.**\nПосмотри на этот предмет на сцене. Где и какое ощущение возникает в теле (сжатие, холод, ком)? Что ты именно сейчас делаешь своим телом (напрягаешь мышцы, задерживаешь дыхание)?",
    "📍 **Точка 6: Биологическое Алиби.**\nТело всегда действует логично. Как ты думаешь, от чего тебя пытается защитить или уберечь эта телесная реакция?",
    "📍 **Точка 7: Реинтеграция.**\nКакое качество в поведении других людей тебя раздражает сильнее всего? Если представить, что за этим стоит сила — что это за сила и как бы ты мог использовать её себе на пользу?",
    "📍 **Точка 8: Команда Автора.**\nТы готов признать себя Автором того, что происходит в твоем теле и твоей жизни, и перенастроить внутренний автопилот на реализацию твоих замыслов прямо сейчас?"
]

SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР ИДЕНТИЧНОСТИ IDENTITY LAB.
Твой тон: Директивный, технический, научный. Обращайся только на "ТЫ".

ЗАДАЧА: Сформировать отчет на основе данных аудита.
1. АВТОРСТВО: Подчеркивай, что зажим в теле — это активное действие пользователя по защите системы.
2. СИНТЕЗ РОЛИ: Из ответов на Точку 2 создай ЕДИНУЮ РОЛЬ (например, "Мощный Творец").
3. МЕТАФОРМУЛА: В конце отчета обязательно выдай формулу: 
«Я Автор. Я ПРИЗНАЮ, что сам создаю этот сигнал [ответ 5] — это мой ресурс. Я НАПРАВЛЯЮ его на активацию [Синтезированная Роль]».
"""

# =================================================================================================
# 4. ШАБЛОН ВЕБ-ОТЧЕТА (GOLD & OBSIDIAN - STYLED)
# =================================================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Identity Lab Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; --text: #e5e5e5; --card-bg: rgba(20, 20, 20, 0.95); }}
        body {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; }}
        .mono {{ font-family: 'Roboto Mono', monospace; }}
        .cyber-card {{ background: var(--card-bg); border: 1px solid #333; border-left: 4px solid var(--gold); padding: 24px; border-radius: 8px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
        .btn-gold {{ background: linear-gradient(to right, #b4932c, #D4AF37); color: #000; font-weight: bold; padding: 14px 28px; border-radius: 6px; text-transform: uppercase; letter-spacing: 0.05em; transition: all 0.3s; display: inline-block; }}
        .btn-gold:hover {{ transform: translateY(-2px); box-shadow: 0 0 15px rgba(212, 175, 55, 0.4); }}
        .text-gold {{ color: var(--gold); }}
        .text-cyan {{ color: var(--cyan); }}
    </style>
</head>
<body class="p-4 md:p-8 max-w-4xl mx-auto min-h-screen flex flex-col items-center selection:bg-yellow-900 selection:text-white">
    <header class="text-center mb-12 border-b border-gray-800 pb-8">
        <p class="text-xs text-cyan tracking-[0.3em] uppercase mb-2 mono">Neuro-Architecture System</p>
        <h1 class="text-5xl md:text-7xl font-bold text-gold mb-2 tracking-tight">IDENTITY LAB</h1>
        <p class="text-xl text-gray-400">Персональная карта дешифровки: <span class="text-white">{user_name}</span></p>
    </header>
    
    <main class="w-full flex-grow">
        <!-- Chart Section -->
        <div class="cyber-card flex flex-col md:flex-row items-center gap-8 justify-center">
            <div class="relative w-40 h-40 flex-shrink-0">
                 <canvas id="statusChart"></canvas>
                 <div class="absolute inset-0 flex items-center justify-center flex-col">
                    <span class="text-2xl font-bold text-white">{idx}%</span>
                 </div>
            </div>
            <div class="text-center md:text-left">
                <h2 class="text-xl font-bold text-white mb-2">Индекс Автоматизма</h2>
                <p class="text-gray-400 text-sm max-w-md">
                    Ваша система работает в режиме защиты (<span class="text-gold">Биологическое Алиби</span>).
                    Большая часть энергии уходит на удержание старой идентичности.
                </p>
            </div>
        </div>

        <!-- Report Text -->
        <div class="cyber-card">
            <h2 class="text-xl font-bold text-white mb-4 border-b border-gray-800 pb-2 flex items-center">
                <span class="text-gold mr-2">⚡️</span> НЕЙРО-СИНТЕЗ ДАННЫХ
            </h2>
            <div class="mono whitespace-pre-wrap text-gray-300 text-sm md:text-base leading-relaxed">
{report_text}
            </div>
        </div>

        <!-- CTA -->
        <div class="text-center py-8 space-y-6">
            <p class="text-gray-400 text-sm">Окно нейропластичности открыто (4 часа).<br>Закрепите результат действием.</p>
            <div class="flex flex-col md:flex-row gap-4 justify-center">
                <a href="{practicum_link}" class="btn-gold">🚀 ЗАПУСТИТЬ ПРАКТИКУМ</a>
                <a href="{protocol_link}" class="border border-gray-700 text-gray-400 hover:text-white py-3 px-8 rounded uppercase font-bold transition hover:bg-gray-800 flex items-center justify-center text-sm">
                    📥 Скачать Гайд (PDF)
                </a>
            </div>
        </div>
    </main>

    <footer class="w-full text-center py-8 mt-auto border-t border-gray-900 text-[10px] text-gray-600 mono">
        © 2026 IDENTITY LAB | ALEXANDER LAZARENKO
    </footer>

    <script>
        const ctx = document.getElementById('statusChart').getContext('2d');
        new Chart(ctx, {{
            type: 'doughnut',
            data: {{
                labels: ['Автоматизм', 'Авторство'],
                datasets: [{{
                    data: [{idx}, {inv_idx}],
                    backgroundColor: ['#1f1f1f', '#D4AF37'],
                    borderColor: '#050505',
                    borderWidth: 3,
                    cutout: '85%'
                }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }} }}
        }});
    </script>
</body>
</html>
"""

# =================================================================================================
# 5. СЛУЖЕБНЫЕ ФУНКЦИИ И ЛОГИКА
# =================================================================================================

async def send_admin_alert(text: str):
    """Уведомления для владельца бота"""
    try:
        await bot.send_message(ADMIN_ID, text, disable_web_page_preview=True, parse_mode="Markdown")
    except: pass

def calculate_index(answers):
    """Оценка степени застоя по ключевым словам в ответах"""
    text = " ".join(answers).lower()
    markers = ['не знаю', 'боюсь', 'страх', 'лень', 'тупик', 'тяжело', 'сжатие', 'ком']
    count = sum(1 for m in markers if m in text)
    return min(95, max(60, 72 + (count * 4)))

async def get_ai_report(answers):
    """Формирование экспертного отчета через ИИ с повторами при сбоях"""
    if not ai_client: return "⬛️ [ДЕМО-РЕЖИМ]\nТы — Автор. Признай силу и действуй."
    
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    for attempt in range(3):
        try:
            resp = await ai_client.chat.completions.create(
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data_str}],
                model="llama-3.3-70b", temperature=0.4, max_completion_tokens=2500
            )
            return resp.choices[0].message.content
        except Exception as e:
            if attempt == 2: await send_admin_alert(f"🚨 **СБОЙ AI API!**\n`{str(e)[:150]}`")
            await asyncio.sleep(2 ** attempt)
    return "Синхронизация ограничена. Но код прежний: Я Автор. ПРИЗНАЮ свою силу."

async def check_sub(user_id):
    """Проверка подписки на канал проекта"""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

def get_reply_menu():
    """Нижняя синяя кнопка меню (Reply Keyboard)"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="≡ МЕНЮ"))
    return builder.as_markup(resize_keyboard=True)

def get_main_keyboard():
    """Инлайн-кнопки управления"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🚀 Новый Аудит", callback_data="run"))
    builder.row(types.InlineKeyboardButton(text="📥 Скачать Гайд", callback_data="get_guide"))
    builder.row(types.InlineKeyboardButton(text="⚡️ Практикум", url=PRACTICUM_URL))
    builder.row(types.InlineKeyboardButton(text="💬 ПОДДЕРЖКА", url=SUPPORT_LINK))
    return builder.as_markup()

async def send_guide(message: types.Message):
    """Отправка PDF Гайда"""
    try:
        await message.answer("📥 **Формирую ваш Технический Паспорт (Гайд)...**", parse_mode="Markdown")
        async with ClientSession() as session:
            async with session.get(PROTOCOL_URL) as resp:
                if resp.status == 200:
                    pdf_data = await resp.read()
                    await message.answer_document(
                        document=types.BufferedInputFile(pdf_data, filename="ПРОТОКОЛ_ДЕШИФРОВКИ.pdf"),
                        caption="📘 Ваш Гайд готов.\n\nВнутри — секрет 'Ловушки Интеллекта' и почему просто 'понимать' недостаточно для роста."
                    )
                else:
                    raise Exception(f"Failed to download PDF: {resp.status}")
    except Exception as e:
        logger.error(f"Guide send error: {e}")
        await message.answer(f"📥 Не удалось отправить файл напрямую. Скачайте его по ссылке:\n{PROTOCOL_URL}")

async def send_admin_log(user: types.User, report: str, answers: list):
    """Логирование действий в админку"""
    try:
        ans_log = "\n".join([f"{i+1}: {a}" for i, a in enumerate(answers)])
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 **НОВАЯ ДИАГНОСТИКА!**\n👤 {user.full_name} (@{user.username})\n\n**ОТВЕТЫ:**\n{ans_log}\n\n**ОТЧЕТ:**\n{report[:1000]}...",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Admin log error: {e}")

# =================================================================================================
# 6. ОБРАБОТЧИКИ ТЕЛЕГРАМ (HANDLERS)
# =================================================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    is_sub = await check_sub(message.from_user.id)
    
    # Показываем нижнюю клавиатуру сразу (для всех)
    await message.answer("Система загружается...", reply_markup=get_reply_menu())
    
    kb = InlineKeyboardBuilder()
    if not is_sub:
        kb.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check"))
        cap = (
            "👋 **Лаборатория Идентичности 'Метаформула жизни'**\n\n"
            "Я — Мета-Навигатор. Я помогу тебе найти точки утечки энергии и перехватить управление у биологического автопилота.\n\n"
            "Для начала работы подпишись на наш канал:"
        )
        await message.answer_photo(LOGO_URL, caption=cap, reply_markup=kb.as_markup())
    else:
        cap = "🧠 Система синхронизирована. Готов занять место Автора и начать дешифровку коннектома?"
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption=cap, reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "check")
async def check_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ открыт!")
        await cmd_start(cb.message, state)
    else:
        await cb.answer("Подписка не найдена!", show_alert=True)

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 **Меню Identity Lab:**", reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "run")
async def audit_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(step=0, answers=[])
    await cb.message.answer("🔬 **Инициализация протокола.**\nОтвечай честно. Твоё тело — самый точный прибор.")
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0], parse_mode="Markdown")
    await state.set_state(AuditState.answering)

@dp.callback_query(F.data == "get_guide")
async def get_guide_cb(cb: types.CallbackQuery):
    # Проверка базы данных (Firestore)
    user_id = cb.from_user.id
    data = await get_diagnostic(user_id)
    
    # Если данных нет в базе, проверяем локальный кэш
    if not data and user_id not in diagnostic_cache:
        await cb.answer("🚫 Сначала пройдите Аудит!", show_alert=True)
        return
    
    await cb.answer("Отправляю...")
    await send_guide(cb.message)

@dp.message(AuditState.answering)
async def process_answers(message: types.Message, state: FSMContext):
    if not message.text or message.text == "≡ МЕНЮ": return
    
    # ВАЛИДАЦИЯ ТЕКСТА (Защита от мусора)
    if len(message.text) < 3 or re.match(r'^(\w)\1+$', message.text):
        await message.answer("⚠️ Данные некорректны. Пожалуйста, напишите осмысленный ответ.")
        return

    data = await state.get_data()
    step, answers = data.get('step', 0), data.get('answers', [])
    answers.append(message.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step+1, answers=answers)
        await message.answer(QUESTIONS[step+1], parse_mode="Markdown")
    else:
        status_msg = await message.answer("🧠 **Дешифровка Коннектома... [||||||||||] 100%**")
        report = await get_ai_report(answers)
        idx = calculate_index(answers)
        
        # Данные для сохранения
        diag_data = {
            "name": message.from_user.full_name,
            "report": report,
            "index": idx,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        # СОХРАНЕНИЕ: И в базу (Firestore), и в кэш (RAM)
        await save_diagnostic(message.from_user.id, diag_data)
        diagnostic_cache[message.from_user.id] = diag_data
        
        await status_msg.edit_text(report.replace('**', '*'))
        await send_guide(message)
        
        kb = InlineKeyboardBuilder()
        report_url = f"{RENDER_URL}/report/{message.from_user.id}"
        kb.row(types.InlineKeyboardButton(text="📊 ОТКРЫТЬ ВЕБ-ОТЧЕТ", url=report_url))
        kb.row(types.InlineKeyboardButton(text="⚡️ ПЕРЕЙТИ К ПРАКТИКУМУ", url=PRACTICUM_URL))
        
        await asyncio.sleep(2)
        await message.answer("🎯 Аудит завершен. Твой веб-отчет готов:", reply_markup=kb.as_markup())
        
        # Лог админу
        try:
            ans_log = "\n".join([f"{i+1}: {a}" for i, a in enumerate(answers)])
            await send_admin_alert(f"🔔 **НОВАЯ ДИАГНОСТИКА!**\n👤 {message.from_user.full_name}\n\n**ОТВЕТЫ:**\n{ans_log}\n\n**ОТЧЕТ:**\n{report[:1000]}...")
        except: pass
        await state.clear()

# =================================================================================================
# 7. ВЕБ-СЕРВЕР
# =================================================================================================

async def handle_home(request):
    return web.Response(text="Identity Lab System v6.6 Active")

async def handle_report(request):
    try:
        user_id = int(request.match_info['user_id'])
        # Ищем сначала в базе, потом в кэше
        d = await get_diagnostic(user_id) 
        if not d:
            d = diagnostic_cache.get(user_id)
            
        if d:
            html = HTML_TEMPLATE.format(
                user_name=d['name'], index=d['index'], remain=100-d['index'],
                report_html=d['report'].replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="Отчет не найден. Пройдите диагностику в боте.", status=404)
    except Exception as e:
        logger.error(f"Web Error: {e}")
        return web.Response(text="Ошибка доступа.", status=500)

async def on_startup(bot: Bot):
    if RENDER_URL:
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Запуск"),
        types.BotCommand(command="menu", description="Управление")
    ])
    await send_admin_alert("🚀 **Identity Lab v6.6 СИНХРОНИЗИРОВАН**\nFirestore Active. Webhook Active.")

def main():
    app = web.Application()
    app.router.add_get('/', handle_home)
    app.router.add_get('/report/{user_id}', handle_report)
    
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
