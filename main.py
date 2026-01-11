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

# --- ДВИЖКИ ИСКУССТВЕННОГО ИНТЕЛЛЕКТА (HYBRID) ---
import google.generativeai as genai
try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# --- ИНТЕГРАЦИЯ С FIREBASE / FIRESTORE ---
import firebase_admin
from firebase_admin import credentials, firestore

# =================================================================================================
# 1. ГЛОБАЛЬНЫЕ НАСТРОЙКИ СИСТЕМЫ (CORE ENGINE)
# =================================================================================================

# Настройка сигналов для корректной работы в Linux/Render (предотвращение зомби-процессов)
if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Конфигурация из переменных окружения Render
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")  # Основной ключ (Google AI Studio)
CEREBRAS_KEY = os.getenv("AI_API_KEY")    # Резервный ключ (Cerebras)
FIREBASE_KEY = os.getenv("FIREBASE_KEY")  # JSON-строка ключа доступа
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
PORT = int(os.getenv("PORT", 10000))

# Параметры Webhook
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# Идентификаторы проекта
CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013 
app_id = "identity-lab-v10" # Уникальный ID для Firestore (Rule 1)

# Ресурсы (Медиа и Документы)
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logohi.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo1.jpg"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/Autopilot_System_Protocol.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни" 
CHANNEL_LINK = "https://t.me/metaformula_life"
SUPPORT_LINK = "https://t.me/lazalex81"

# Расширенное логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Инициализация Firestore (Соблюдение RULE 1: artifacts/{appId}/public/data/...)
db = None
if FIREBASE_KEY:
    try:
        cred_dict = json.loads(FIREBASE_KEY)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("✅ Firestore Cloud Storage: CONNECTED (Rule 1 Compliant)")
    except Exception:
        logger.error(f"❌ Firestore Init Error:\n{traceback.format_exc()}")

# Инициализация основного движка Gemini
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        logger.info("✅ Gemini 1.5 Flash (Primary): ONLINE")
    except Exception:
        logger.error(f"❌ Gemini Init Failure: {traceback.format_exc()}")

# Инициализация резервного движка Cerebras
ai_client_backup = None
if CEREBRAS_KEY and CEREBRAS_AVAILABLE:
    try:
        ai_client_backup = AsyncCerebras(api_key=CEREBRAS_KEY)
        logger.info("✅ Cerebras AI Engine (Backup): ONLINE")
    except Exception:
        logger.error(f"❌ Cerebras Init Failure: {traceback.format_exc()}")

# Объекты бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class AuditState(StatesGroup):
    answering = State()

# Временный кэш для моментальной отдачи отчетов на веб-страницах
diagnostic_cache = {}

# =================================================================================================
# 2. МЕТОДОЛОГИЯ: ВОПРОСЫ И СИСТЕМНЫЙ ПРОМПТ (USER FRIENDLY)
# =================================================================================================

QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают того результата, на который ты рассчитываешь.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Кто ты в этой точке? Опиши свою новую Идентичность (твою эталонную версию Я) 3–4 словами (например: ясный, мощный, свободный).",
    "📍 **Точка 3: Архивный режим.**\nКакая «мыслительная жвачка» крутится в голове (постоянные повторяющиеся мысли)? Какие сомнения оправдывают твой текущий застой?",
    "📍 **Точка 4: Сцена.**\nПредставь перед собой пустую сцену. Вынеси на неё своё внутреннее препятствие — ту самую силу, которая мешает тебе действовать. На что бы оно могло быть похоже?",
    "📍 **Точка 5: Детекция сигнала.**\nПосмотри на предмет на Сцене. Где в теле возникает отклик (сжатие, холод, ком)? Опиши физику своего действия (напрягаю мышцы, замираю, перестаю дышать)?",
    "📍 **Точка 6: Биологическое Алиби.**\nТвой мозг всегда действует логично. Как ты думаешь, от какой «опасности» тебя пытается защитить эта телесная реакция? (Биологическое Алиби — это оправдание мозга, чтобы сохранить твой гомеостаз — стабильность любой ценой).",
    "📍 **Точка 7: Реинтеграция.**\nКакое качество в поведении других людей тебя бесит сильнее всего? Какая скрытая сила за ним стоит? Как бы ты мог использовать её себе на пользу?",
    "📍 **Точка 8: Команда Автора.**\nТы готов признать себя Автором своей системы и запустить перенастройку своего биокомпьютера (твоей нервной системы) на реализацию твоих замыслов прямо сейчас?"
]

SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР IDENTITY LAB (ЛАБОРАТОРИЯ ИДЕНТИЧНОСТИ).
ЗАДАЧА: Сформировать технический отчет на основе соматического аудита. Тон: Директивный, инженерный, научный. Обращайся только на "ТЫ".

ПРАВИЛА ТЕРМИНОВ (ОБЯЗАТЕЛЬНО):
Если используешь сложные понятия, добавляй расшифровку в скобках:
- Коннектом (карта связей головного мозга).
- Гомеостаз (стремление системы сохранять стабильность любой ценой).
- Амигдала (центр страха в мозге).
- Префронтальная кора (зона мозга, отвечающая за логику и управление).
- DMN / ДСМ (Дефолт-система мозга, работающая в режиме "автопилота").

СТРОГОЕ ПРАВИЛО: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать символы ** (двойные звездочки) в тексте отчета.

ЛОГИКА ОТЧЕТА:
1. ИНДЕКС АВТОМАТИЗМА: [Рассчитай % инерции системы на основе ответов от 65 до 95].
2. АВТОРСТВО: Объясни, что пользователь САМ создает сигнал [ответ 5] ради защиты системы от [ответ 6]. Это его активная стратегия.
3. РЕИНТЕГРАЦИЯ: Сила из [ответ 7] заперта в зажиме [ответ 5]. Мы возвращаем ресурс в систему.
4. ИДЕНТИЧНОСТЬ (СИНТЕЗ): Назови Идентичность на базе [ответ 2]. Дай функциональную расшифровку: как в этом состоянии Префронтальная кора подавляет шум Амигдалы.
5. МЕТАФОРМУЛА (КОД АКТИВАЦИИ):
«Я Автор. ПРИЗНАЮ, что сам создаю этот сигнал [ответ 5] — это мой ресурс. НАПРАВЛЯЮ его на активацию Идентичности [Идентичность из ответа 2]»."""

# =================================================================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (АНАЛИТИКА, ВАЛИДАЦИЯ)
# =================================================================================================

async def track_user_action(user: types.User, status: str, extra: dict = None):
    """RULE 1: artifacts/{appId}/public/data/users/{userId}"""
    if not db: return
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(user.id))
        data = {
            "name": user.full_name,
            "username": user.username,
            "last_status": status,
            "last_activity": datetime.now(),
        }
        if status == "joined": data["created_at"] = datetime.now()
        if extra: data.update(extra)
        doc_ref.set(data, merge=True)
    except Exception:
        logger.error(f"Track Error: {traceback.format_exc()}")

async def send_admin_alert(text: str):
    """Уведомление владельцу проекта в Telegram"""
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown", disable_web_page_preview=True)
    except: pass

def validate_input_robust(text):
    """Entropy Filter: Защита от абракадабры и коротких ответов"""
    t = text.strip().lower()
    if len(t) < 3: return False
    # Проверка на аномальное количество согласных (более 6 подряд)
    if re.search(r'[бвгджзйклмнпрстфхцчшщ]{6,}', t): return False
    # Проверка на наличие хотя бы одной гласной
    if not re.search(r'[аеёиоуыэюяaeiouy]', t): return False
    return True

def calculate_index(answers):
    """Рассчитывает индекс инерции по ключевым маркерам застоя"""
    text = " ".join(answers).lower()
    markers = ['не знаю', 'боюсь', 'страх', 'лень', 'тупик', 'тяжело', 'сжатие', 'ком', 'холод', 'тревога', 'сомневаюсь']
    count = sum(1 for m in markers if m in text)
    return min(95, max(60, 72 + (count * 4)))

def generate_fallback_report(answers):
    """Резервный отчет на случай отказа всех AI движков"""
    idx = calculate_index(answers)
    safe = answers + ["..."] * (8 - len(answers))
    return f"ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ: ИНДЕКС {idx}%. СИСТЕМА В РЕЖИМЕ АЛИБИ (защита гомеостаза). Я Автор. ПРИЗНАЮ сигнал {safe[4]}."

async def get_ai_report(answers):
    """ГИБРИДНАЯ ГЕНЕРАЦИЯ: Gemini 1.5 Flash (Primary) -> Cerebras Llama 3.1 (Backup)"""
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    
    # 1. Попытка через Gemini
    if GEMINI_KEY:
        try:
            model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
            response = await asyncio.to_thread(model.generate_content, data_str)
            content = response.text.replace('**', '').replace('```', '')
            if content: return content
        except Exception as e:
            logger.warning(f"⚠️ Gemini Engine failure: {e}")

    # 2. Попытка через Cerebras
    if ai_client_backup:
        try:
            resp = await asyncio.wait_for(ai_client_backup.chat.completions.create(
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data_str}],
                model="llama-3.3-70b", temperature=0.4, max_completion_tokens=2500
            ), timeout=18.0)
            return resp.choices[0].message.content.replace('**', '').replace('```', '')
        except Exception as e:
            logger.warning(f"⚠️ Cerebras backup failure: {e}")

    # 3. Финальный Fallback
    return generate_fallback_report(answers)

# =================================================================================================
# 4. ШАБЛОН ВЕБ-ОТЧЕТА (PREMIUM IDENTITY LAB)
# =================================================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Identity Lab | Персональный Отчет</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; }}
        body {{ background-color: var(--bg); color: #e5e5e5; font-family: 'Rajdhani', sans-serif; }}
        .cyber-card {{ background: rgba(18, 18, 18, 0.98); border: 1px solid #333; border-left: 5px solid var(--gold); padding: 30px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 15px 40px rgba(0,0,0,0.8); }}
        .btn-gold {{ background: linear-gradient(to right, #b4932c, #D4AF37); color: #000; font-weight: bold; padding: 16px 32px; border-radius: 8px; text-transform: uppercase; transition: 0.3s; display: inline-block; text-decoration: none; text-align: center; }}
        .mono {{ font-family: 'Roboto Mono', monospace; line-height: 1.8; }}
    </style>
</head>
<body class="p-4 md:p-10 max-w-5xl mx-auto flex flex-col min-h-screen selection:bg-yellow-900 selection:text-white">
    <header class="text-center mb-16 border-b border-gray-900 pb-10">
        <p class="text-xs text-cyan-400 tracking-[0.3em] uppercase mb-4 font-mono animate-pulse">Neuro-Architecture System v11.14</p>
        <h1 class="text-6xl md:text-8xl font-bold text-gold mb-4 uppercase tracking-tighter leading-none">( IDENTITY LAB )</h1>
        <p class="text-gray-500 uppercase font-mono text-sm tracking-widest">Карта дешифровки коннектома (связей мозга): {user_name}</p>
    </header>
    
    <main class="flex-grow">
        <div class="cyber-card flex flex-col md:flex-row items-center gap-10 justify-center">
            <div class="relative w-44 h-44 flex-shrink-0">
                 <canvas id="statusChart"></canvas>
                 <div class="absolute inset-0 flex items-center justify-center flex-col">
                    <span class="text-4xl font-bold text-white tracking-tighter">{idx}%</span>
                    <span class="text-[10px] text-gray-500 uppercase tracking-widest mt-1">Инерция</span>
                 </div>
            </div>
            <div class="text-center md:text-left space-y-2">
                <h2 class="text-2xl font-bold text-white uppercase tracking-widest">Индекс Автоматизма</h2>
                <p class="text-gray-400 text-base italic max-w-md italic leading-relaxed">Система работает в режиме "Биологического Алиби" (защитная ложь мозга). Энергия блокируется для сохранения гомеостаза (стабильности любой ценой).</p>
            </div>
        </div>

        <div class="cyber-card">
            <h2 class="text-2xl font-bold text-white mb-8 border-b border-gray-800 pb-4 uppercase tracking-[0.2em] flex items-center">
                <span class="text-gold mr-4 text-3xl">⚡️</span> Нейро-Синтез Диагностики
            </h2>
            <div class="mono whitespace-pre-wrap text-gray-300 text-base md:text-lg leading-loose">{report_text}</div>
        </div>

        <div class="text-center py-16 space-y-8 border border-gray-900 rounded-3xl bg-black/40">
            <p class="text-gold text-lg uppercase tracking-[0.3em] font-bold">Окно пластичности открыто (Лимит: 4 часа)</p>
            <p class="text-gray-400 max-w-2xl mx-auto px-6 font-light leading-relaxed">Чтобы миелинизировать (физически укрепить белком) новый нейронный путь, необходимо выполнить материальное действие в реальности.</p>
            <div class="flex flex-col md:flex-row gap-8 justify-center items-center">
                <a href="{practicum_link}" target="_blank" class="btn-gold shadow-2xl hover:scale-105 transform transition duration-500">🚀 Запустить Практикум</a>
                <a href="{protocol_link}" target="_blank" class="border border-gray-700 text-gray-300 py-4 px-10 rounded-lg uppercase font-bold text-sm hover:bg-gray-800 transition">📥 Скачать Протокол</a>
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
                    backgroundColor: ['#1a1a1a', '#D4AF37'], 
                    borderWidth: 0, 
                    cutout: '88%' 
                }}] 
            }},
            options: {{ plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }} }}
        }});
    </script>
    <footer class="mt-24 py-10 border-t border-gray-900 text-center text-[10px] text-gray-700 font-mono tracking-widest uppercase font-light">
        © 2026 Identity Lab Core | Alexander Lazarenko | Neuro-Architecture
    </footer>
</body>
</html>
"""

# =================================================================================================
# 5. КЛАВИАТУРЫ И ФУНКЦИИ БОТА
# =================================================================================================

def get_main_keyboard():
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🚀 Запустить Аудит", callback_data="run"))
    b.row(types.InlineKeyboardButton(text="📥 Скачать Гайд", callback_data="get_guide"))
    b.row(types.InlineKeyboardButton(text="⚡️ Практикум", url=PRACTICUM_URL))
    b.row(types.InlineKeyboardButton(text="💬 ПОДДЕРЖКА", url=SUPPORT_LINK))
    return b.as_markup()

def get_reply_menu():
    return ReplyKeyboardBuilder().row(types.KeyboardButton(text="≡ МЕНЮ")).as_markup(resize_keyboard=True)

async def check_sub(user_id):
    """Проверка подписки на основной канал проекта"""
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ["member", "administrator", "creator"]
    except Exception: return False

async def send_guide_document(message: types.Message):
    """Асинхронная отправка PDF протокола из GitHub"""
    try:
        async with ClientSession() as session:
            async with session.get(PROTOCOL_URL) as resp:
                if resp.status == 200:
                    pdf = await resp.read()
                    await message.answer_document(
                        types.BufferedInputFile(pdf, filename="Identity_Lab_Protocol.pdf"),
                        caption="📘 Ваш технический паспорт Автора.\n\nИзучите раздел «Биологическое Алиби»."
                    )
                else: raise Exception()
    except Exception:
        await message.answer(f"📥 Ссылка на скачивание системного Протокола:\n{PROTOCOL_URL}")

# =================================================================================================
# 6. ХЕНДЛЕРЫ ТЕЛЕГРАМ (LOGIC FLOW)
# =================================================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Точка входа: Синхронизация и проверка прав доступа"""
    await state.clear()
    await track_user_action(message.from_user, "joined")
    
    temp_msg = await message.answer("Синхронизация нейро-профиля...", reply_markup=get_reply_menu())
    is_sub = await check_sub(message.from_user.id)
    await bot.delete_message(chat_id=message.chat.id, message_id=temp_msg.message_id)
    
    if not is_sub:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check"))
        cap = "👋 **Лаборатория Идентичности ( IDENTITY LAB )**\n\nЯ — Мета-Навигатор. Помогу тебе найти точки утечки энергии и перехватить управление у автопилота.\n\nПодпишись на канал для старта:"
        await message.answer_photo(LOGO_URL, caption=cap, reply_markup=kb.as_markup())
    else:
        cap = "🧠 **Система синхронизирована.**\n\nГотов обнаружить программы, которые управляют твоими реакциями автоматически? Готов занять место Автора и начать дешифровку?"
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption=cap, reply_markup=get_main_keyboard())

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 **Панель управления Identity Lab:**", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "check")
async def check_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ открыт!"); await cmd_start(cb.message, state)
    else: await cb.answer("Подписка не найдена в системе!", show_alert=True)

@dp.callback_query(F.data == "run")
async def audit_init(cb: types.CallbackQuery, state: FSMContext):
    """Запуск процесса 8-точечной дешифровки"""
    await cb.answer()
    await track_user_action(cb.from_user, "audit_started")
    await send_admin_alert(f"👤 {cb.from_user.full_name} (@{cb.from_user.username}) начал аудит.")
    
    await state.update_data(step=0, answers=[])
    await cb.message.answer("🔬 Инициализация протокола. Будь предельно искренен с собой. Твоё тело — самый точный прибор. Мы начинаем глубокий аудит.")
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0], parse_mode="Markdown")
    await state.set_state(AuditState.answering)

@dp.message(AuditState.answering)
async def process_answers(message: types.Message, state: FSMContext):
    """Пошаговый сбор данных аудита"""
    if not message.text or message.text == "≡ МЕНЮ" or message.text.startswith("/"): return
    
    # ВАЛИДАЦИЯ (Защита от мусора)
    if not validate_input_robust(message.text):
        return await message.answer("⚠️ Ошибка сигнала. Опиши свои ощущения словами (без абракадабры).")

    data = await state.get_data()
    step, answers = data.get('step', 0), data.get('answers', [])
    answers.append(message.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step+1, answers=answers)
        await message.answer(QUESTIONS[step+1], parse_mode="Markdown")
        await track_user_action(message.from_user, f"step_{step+1}")
    else:
        # ФИНАЛИЗАЦИЯ И СИНТЕЗ
        status_msg = await message.answer("🧠 **Дешифровка Коннектома... [||||||||||] 100%**")
        report = await get_ai_report(answers)
        idx = calculate_index(answers)
        
        diag_data = {
            "name": message.from_user.full_name,
            "report": report, 
            "index": idx, 
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        # СОХРАНЕНИЕ ДАННЫХ (Persistence - Rule 1)
        if db:
            db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(message.from_user.id)).set(diag_data, merge=True)
        
        # Обновляем кэш
        diagnostic_cache[message.from_user.id] = diag_data
        await track_user_action(message.from_user, "audit_finished", diag_data)
        
        # Вывод отчета в Telegram
        await status_msg.edit_text(f"⬛️ **[ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ]**\n\n{report}")
        await send_guide_document(message)
        
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📊 ОТКРЫТЬ ВЕБ-ОТЧЕТ", url=f"{RENDER_URL}/report/{message.from_user.id}"))
        kb.row(types.InlineKeyboardButton(text="⚡️ ПЕРЕЙТИ К ПРАКТИКУМУ", url=PRACTICUM_URL))
        
        await asyncio.sleep(2)
        await message.answer("🎯 Аудит завершен. Твой персональный отчет и карта дешифровки готовы:", reply_markup=kb.as_markup())
        await send_admin_alert(f"✅ {message.from_user.full_name} завершил аудит. Индекс: {idx}%")
        await state.clear()

@dp.callback_query(F.data == "get_guide")
async def guide_cb(cb: types.CallbackQuery):
    """Выдача Гайда с проверкой завершения аудита"""
    is_finished = False
    if db:
        doc = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(cb.from_user.id)).get()
        if doc.exists and doc.to_dict().get("last_status") == "audit_finished": is_finished = True
    
    if not is_finished and cb.from_user.id not in diagnostic_cache:
        return await cb.answer("🚫 Доступ к Протоколу закрыт! Сначала пройдите Аудит системы до конца.", show_alert=True)

    await cb.answer("Загрузка данных..."); await send_guide_document(cb.message)

@dp.message(Command("admin_stats"))
async def cmd_admin_stats(message: types.Message):
    """Служебная статистика проекта"""
    if message.from_user.id != ADMIN_ID or not db: return
    users = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").stream()
    stats = {"total": 0, "finished": 0}
    for u in users:
        d = u.to_dict(); stats["total"] += 1
        if d.get("last_status") == "audit_finished": stats["finished"] += 1
    await message.answer(f"📊 **СТАТИСТИКА IDENTITY LAB CORE**\n\n👥 Всего: {stats['total']}\n✅ Завершили аудит: {stats['finished']}")

# =================================================================================================
# 7. ВЕБ-СЕРВЕР (REPORTS & WEBHOOK)
# =================================================================================================

async def handle_root(r): return web.Response(text="Identity Lab System Core v11.14 Active")

async def handle_report(request):
    """Генерация динамической HTML страницы отчета"""
    try:
        uid_str = request.match_info['user_id']
        uid = int(uid_str)
        data = diagnostic_cache.get(uid)
        
        if not data and db:
            doc = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(uid_str).get()
            if doc.exists: data = doc.to_dict()
        
        if data:
            html = HTML_TEMPLATE.format(
                user_name=data.get('name', 'Гость'), 
                idx=data.get('index', 75), inv_idx=100-data.get('index', 75),
                report_text=data.get('report', '').replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="<h1>Ошибка 404: Отчет не найден. Пройдите аудит в Telegram-боте.</h1>", content_type='text/html', status=404)
    except Exception: 
        return web.Response(text="Ошибка доступа к ядру данных.", status=500)

async def on_startup(bot: Bot):
    if RENDER_URL: await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Запуск и синхронизация"),
        types.BotCommand(command="menu", description="Главное меню управления")
    ])
    await send_admin_alert("🚀 **Identity Lab v11.14 СИНХРОНИЗИРОВАН**\nAI Engines: Gemini 1.5 Flash + Cerebras Active.")

def main():
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_get('/report/{user_id}', handle_report)
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    try: main()
    except (KeyboardInterrupt, SystemExit): pass

