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

# --- AI ENGINES ---
import google.generativeai as genai
try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# --- FIREBASE / FIRESTORE INTEGRATION ---
import firebase_admin
from firebase_admin import credentials, firestore

# =================================================================================================
# 1. СИСТЕМНЫЕ НАСТРОЙКИ И БЕЗОПАСНОСТЬ (CORE ENGINE)
# =================================================================================================

# Настройка сигналов для корректной работы на Linux/Render (предотвращает зомби-процессы)
if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Загрузка конфигурационных переменных из окружения Render
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")  # Ключ от Google AI Studio (Primary)
CEREBRAS_KEY = os.getenv("AI_API_KEY")    # Ключ от Cerebras (Backup)
FIREBASE_KEY = os.getenv("FIREBASE_KEY")  # JSON-строка ключа сервисного аккаунта
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
PORT = int(os.getenv("PORT", 10000))

# Параметры Webhook для работы в режиме реального времени
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# Идентификаторы системы
CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013 
app_id = "identity-lab-v10" # ID проекта для структуры Firestore

# Ссылки на внешние ресурсы и медиа
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logohi.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo11.png"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/Autopilot_System_Protocol.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни" 
CHANNEL_LINK = "https://t.me/metaformula_life"
SUPPORT_LINK = "https://t.me/lazalex81"

# Настройка логирования для дебага и мониторинга
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Инициализация Firebase Cloud Storage (Соблюдение RULE 1)
db = None
if FIREBASE_KEY:
    try:
        cred_dict = json.loads(FIREBASE_KEY)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("✅ Firestore Cloud Storage: CONNECTED")
    except Exception:
        logger.error(f"❌ Firestore Init Error:\n{traceback.format_exc()}")

# Инициализация Gemini Engine (Основной мозг)
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    logger.info("✅ Gemini 1.5 Flash (Primary): ONLINE")

# Инициализация Cerebras AI (Резервный мозг)
ai_client_backup = None
if CEREBRAS_KEY and CEREBRAS_AVAILABLE:
    try:
        ai_client_backup = AsyncCerebras(api_key=CEREBRAS_KEY)
        logger.info("✅ Cerebras AI (Backup): ONLINE")
    except Exception:
        logger.error(f"❌ Cerebras Init Failure: {traceback.format_exc()}")

# Создание экземпляра бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Определение состояний FSM (Finite State Machine)
class AuditState(StatesGroup):
    answering = State()

# RAM-кэш для быстрого доступа к отчетам (снижает нагрузку на БД)
diagnostic_cache = {}

# =================================================================================================
# 2. МЕТОДОЛОГИЯ: ВОПРОСЫ И СИСТЕМНЫЙ ПРОМПТ
# =================================================================================================

QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни или в каком деле ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают того результата, на который ты рассчитываешь.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Какой ты теперь? Подбери 3–4 слова (например: спокойный, мощный, свободный). Как ты себя чувствуешь и как теперь смотришь на мир?",
    "📍 **Точка 3: Архивный режим.**\nКакая «мыслительная жвачка» крутится у тебя в голове, когда ты думаешь о переменах? Какие сомнения или доводы ты себе приводишь, чтобы оправдать текущую ситуацию?",
    "📍 **Точка 4: Сцена.**\nПредставь перед собой пустую сцену. Вынеси на неё своё внутреннее препятствие — ту самую невидимую силу или преграду, которая мешает тебе действовать. Если бы оно было реальным предметом или образом... на что бы оно могло быть похоже?",
    "📍 **Точка 5: Детекция сигнала.**\nПосмотри на этот предмет на той сцене перед собой. Где и какое ощущение возникает в теле (сжатие, холод, ком)? Опиши, что именно ты сейчас делаешь со своим телом (напрягаешь мышцы, задерживаешь дыхание)?",
    "📍 **Точка 6: Биологическое Алиби.**\nСистема всегда действует логично. Как ты думаешь, от чего тебя пытается защитить или уберечь эта телесная реакция при взгляде на препятствие? (Например: от риска, от лишних трат или от ошибки?)",
    "📍 **Точка 7: Реинтеграция.**\nКакое качество в поведении других людей тебя раздражает сильнее всего (наглость, навязчивость, грубость)? Если представить, что за этим качеством стоит какая-то скрытая сила — что это за сила? Как бы ты мог использовать её себе на пользу?",
    "📍 **Точка 8: Команда Автора.**\nТы готов признать себя Автором того, что происходит в твоей системе и твоей жизни, и перенастроить внутренний автопилот на реализацию твоих замыслов прямо сейчас?"
]

SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР IDENTITY LAB (ЛАБОРАТОРИЯ ИДЕНТИЧНОСТИ).
ЗАДАЧА: Сформировать технический отчет на основе соматического аудита. Тон: Директивный, инженерный, научный. Обращайся только на "ТЫ".

СТРОГОЕ ПРАВИЛО: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать символы ** (двойные звездочки) в тексте отчета. Никакого визуального выделения жирным через разметку.

ЛОГИКА ОТЧЕТА:
1. ИНДЕКС АВТОМАТИЗМА: [Рассчитай % инерции системы на основе ответов от 65 до 95].
2. АВТОРСТВО: Объясни, что пользователь САМ создает сигнал [ответ 5] ради защиты системы от [ответ 6]. Это его активная стратегия.
3. РЕИНТЕГРАЦИЯ: Сила из [ответ 7] заперта в зажиме [ответ 5]. Мы возвращаем этот ресурс в систему.
4. МЕТАФОРМУЛА: В конце выдай Код Активации:
«Я Автор. ПРИЗНАЮ, что сам создаю этот сигнал [ответ 5] — это мой ресурс. НАПРАВЛЯЮ его на активацию [Идентичность из ответа 2]»."""

# =================================================================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (АНАЛИТИКА, ХРАНЕНИЕ, ВАЛИДАЦИЯ)
# =================================================================================================

async def track_user_action(user: types.User, status: str, extra: dict = None):
    """RULE 1: artifacts/{appId}/public/data/users/{userId}"""
    if not db: return
    try:
        # Сохраняем в коллекцию пользователей проекта
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
    """Мгновенное уведомление администратору в Telegram"""
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown", disable_web_page_preview=True)
    except: pass

def validate_input_robust(text, step):
    """Проверка осмысленности ввода пользователя"""
    t = text.strip()
    # Минимальная длина ответа для разных шагов
    min_lens = {0: 10, 1: 5, 2: 10, 3: 3, 4: 5, 5: 5, 6: 5, 7: 2}
    if len(t) < min_lens.get(step, 3): return False
    
    # Проверка на наличие гласных (защита от случайных нажатий)
    vowels = re.findall(r'[аеёиоуыэюяaeiouy]', t.lower())
    if not vowels and step != 7: return False
    
    # Защита от повторения одного символа
    if re.match(r'^(\w)\1+$', t): return False
    return True

def calculate_automatism_index(answers):
    """Рассчитывает индекс инерции системы по ключевым словам"""
    text = " ".join(answers).lower()
    markers = [
        'не знаю', 'боюсь', 'страх', 'лень', 'тупик', 'тяжело', 'не могу', 'сжимает', 
        'ком', 'холод', 'тревога', 'паника', 'жду', 'откладываю', 'проблема'
    ]
    count = sum(1 for m in markers if m in text)
    # Базовый уровень + поправка на "затыки"
    return min(95, max(60, 72 + (count * 3)))

def generate_fallback_report(answers):
    """Резервный отчет, если все AI движки недоступны"""
    idx = calculate_automatism_index(answers)
    safe = answers + ["..."] * (8 - len(answers))
    
    report = f"""ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ: ДИАГНОСТИКА АВТОПИЛОТА

Статус: Обнаружено ограничение тока энергии. Система в режиме гомеостаза.

ИНДЕКС АВТОМАТИЗМА: {idx}%

1. УЗЕЛ СОПРОТИВЛЕНИЯ:
Образ "{safe[3]}" вызывает сигнал "{safe[4]}". Это ваше активное действие по защите.

2. ХОЛОСТОЙ ХОД:
Мысли "{safe[2]}" — это работа Биологического Алиби. Система защищает вас от "{safe[5]}".

3. РЕАКТОР ИДЕНТИЧНОСТИ:
Раздражение указывает на скрытую силу: "{safe[6]}".

КОД ПЕРЕПРОШИВКИ (МЕТАФОРМУЛА):
Я Автор. ПРИЗНАЮ, что сам создаю этот сигнал [{safe[4]}] — это мой ресурс. Я НАПРАВЛЯЮ его на активацию [{safe[1]}].
"""
    return report

async def get_ai_report(answers):
    """ГИБРИДНАЯ ГЕНЕРАЦИЯ: Сначала Gemini, затем Cerebras"""
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    
    # 1. Основная попытка через Gemini 1.5 Flash
    if GEMINI_KEY:
        try:
            model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
            response = await asyncio.to_thread(model.generate_content, data_str)
            content = response.text.replace('**', '').replace('```', '')
            if content: return content
        except Exception as e:
            logger.warning(f"Gemini Engine Failure: {e}")

    # 2. Резервная попытка через Cerebras AI (Llama 3.1 70B)
    if ai_client_backup:
        for attempt in range(2):
            try:
                resp = await asyncio.wait_for(ai_client_backup.chat.completions.create(
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data_str}],
                    model="llama-3.3-70b", temperature=0.4, max_completion_tokens=2500
                ), timeout=18.0)
                content = resp.choices[0].message.content
                return content.replace('**', '').replace('```', '')
            except Exception:
                await asyncio.sleep(2)
    
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
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; --text: #e5e5e5; }}
        body {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; overflow-x: hidden; }}
        .cyber-card {{ background: rgba(20, 20, 20, 0.95); border: 1px solid #333; border-left: 4px solid var(--gold); padding: 24px; border-radius: 8px; margin-bottom: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); }}
        .btn-gold {{ background: linear-gradient(to right, #b4932c, #D4AF37); color: #000; font-weight: bold; padding: 14px 28px; border-radius: 6px; text-transform: uppercase; transition: all 0.3s; display: inline-block; text-align: center; text-decoration: none; }}
        .mono {{ font-family: 'Roboto Mono', monospace; }}
        .text-gradient-gold {{ background: linear-gradient(to right, #D4AF37, #F7E7CE); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
    </style>
</head>
<body class="p-4 md:p-8 max-w-4xl mx-auto flex flex-col min-h-screen selection:bg-yellow-900 selection:text-white">
    <header class="text-center mb-12 border-b border-gray-800 pb-8">
        <p class="text-xs text-cyan-400 tracking-[0.3em] uppercase mb-2 font-mono animate-pulse">Neuro-Architecture System v11.3</p>
        <h1 class="text-5xl md:text-7xl font-bold text-gold mb-2 tracking-tight uppercase leading-none">( IDENTITY LAB )</h1>
        <p class="text-xl text-gray-500 mt-4 uppercase font-mono text-sm">Карта дешифровки: {user_name}</p>
    </header>
    
    <main class="flex-grow">
        <div class="cyber-card flex flex-col md:flex-row items-center gap-8 justify-center">
            <div class="relative w-40 h-40 flex-shrink-0">
                 <canvas id="statusChart"></canvas>
                 <div class="absolute inset-0 flex items-center justify-center flex-col">
                    <span class="text-3xl font-bold text-white">{idx}%</span>
                    <span class="text-[10px] text-gray-500 uppercase tracking-widest">Инерция</span>
                 </div>
            </div>
            <div class="text-center md:text-left">
                <h2 class="text-xl font-bold text-white mb-2 uppercase tracking-wide">Индекс Автоматизма</h2>
                <p class="text-gray-400 text-sm max-w-md italic">Ваша система находится в режиме "Биологического Алиби". Автопилот блокирует энергию, чтобы избежать риска перемен.</p>
            </div>
        </div>

        <div class="cyber-card">
            <h2 class="text-xl font-bold text-white mb-6 border-b border-gray-800 pb-2 uppercase tracking-widest flex items-center">
                <span class="text-gold mr-3">⚡️</span> Нейро-Синтез Данных
            </h2>
            <div class="mono whitespace-pre-wrap text-gray-300 text-sm md:text-base leading-loose">{report_text}</div>
        </div>

        <div class="text-center py-12 space-y-6">
            <p class="text-gray-500 text-sm uppercase tracking-[0.2em] italic underline">Логическое следствие: Окно пластичности открыто (4 часа)</p>
            <p class="text-gray-400 max-w-lg mx-auto text-sm">Чтобы закрепить этот Сдвиг и не дать системе откатиться назад, необходимо выполнить материальное действие в реальности.</p>
            <div class="flex flex-col md:flex-row gap-6 justify-center">
                <a href="{practicum_link}" target="_blank" class="btn-gold shadow-2xl hover:scale-105 transform transition">🚀 Запустить Практикум</a>
                <a href="{protocol_link}" target="_blank" class="border border-gray-700 text-gray-300 py-3 px-8 rounded uppercase font-bold text-sm hover:bg-gray-800 transition">📥 Скачать Протокол</a>
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
# 5. КЛАВИАТУРЫ И ФУНКЦИИ БОТА
# =================================================================================================

def get_main_keyboard():
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🚀 Начать Аудит", callback_data="run"))
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
    except: return False

async def send_guide_document(message: types.Message):
    """Асинхронная отправка PDF протокола из внешнего источника"""
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
    except:
        await message.answer(f"📥 Ссылка на скачивание Гайда:\n{PROTOCOL_URL}")

# =================================================================================================
# 6. ХЕНДЛЕРЫ ТЕЛЕГРАМ (LOGIC FLOW)
# =================================================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Точка входа: Синхронизация и проверка прав доступа"""
    await state.clear()
    await track_user_action(message.from_user, "joined")
    
    # 1. Отправляем временное сервисное сообщение
    temp_msg = await message.answer("Синхронизация системы...", reply_markup=get_reply_menu())
    
    is_sub = await check_sub(message.from_user.id)

    # 2. Удаляем сервисное сообщение перед показом контента
    await bot.delete_message(chat_id=message.chat.id, message_id=temp_msg.message_id)
    
    if not is_sub:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check"))
        cap = "👋 **Лаборатория Идентичности ( IDENTITY LAB )**\n\nЯ — Мета-Навигатор. Помогу тебе найти точки утечки энергии и перехватить управление у автопилота.\n\nПодпишись на канал для старта:"
        await message.answer_photo(LOGO_URL, caption=cap, reply_markup=kb.as_markup())
    else:
        cap = "🧠 **Система синхронизирована.**\n\nГотов обнаружить программы, которые управляют твоими реакциями автоматически? Готов занять место Автора?"
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption=cap, reply_markup=get_main_keyboard())

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 **Панель управления Identity Lab:**", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "check")
async def check_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ открыт!"); await cmd_start(cb.message, state)
    else: await cb.answer("Подписка не найдена!", show_alert=True)

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
    
    data = await state.get_data()
    step, answers = data.get('step', 0), data.get('answers', [])
    
    # ВАЛИДАЦИЯ ВВОДА
    if not validate_input_robust(message.text, step):
        return await message.answer("⚠️ Твой ответ слишком короткий или бессмысленный. Пожалуйста, напиши подробнее, это важно для точности дешифровки.")

    answers.append(message.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step+1, answers=answers)
        await message.answer(QUESTIONS[step+1], parse_mode="Markdown")
        await track_user_action(message.from_user, f"step_{step+1}")
    else:
        # ФИНАЛИЗАЦИЯ И НЕЙРО-СИНТЕЗ
        status_msg = await message.answer("🧠 **Дешифровка Коннектома... [||||||||||] 100%**")
        report = await get_ai_report(answers)
        idx = calculate_automatism_index(answers)
        
        diag_data = {
            "name": message.from_user.full_name,
            "report": report, 
            "index": idx, 
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        # СОХРАНЕНИЕ ДАННЫХ (Persistence)
        if db:
            db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(message.from_user.id)).set(diag_data, merge=True)
        
        # Обновляем кэш для моментального открытия веб-отчета
        diagnostic_cache[message.from_user.id] = diag_data
        await track_user_action(message.from_user, "audit_finished", diag_data)
        
        # Вывод отчета в Telegram
        await status_msg.edit_text(report)
        
        # Подготовка кнопок завершения
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📊 ОТКРЫТЬ ВЕБ-ОТЧЕТ", url=f"{RENDER_URL}/report/{message.from_user.id}"))
        kb.row(types.InlineKeyboardButton(text="⚡️ ПЕРЕЙТИ К ПРАКТИКУМУ", callback_data="go_buy"))
        kb.row(types.InlineKeyboardButton(text="≡ МЕНЮ", callback_data="menu"))
        
        await asyncio.sleep(2)
        await message.answer("🎯 Аудит завершен. Твой персональный отчет готов:", reply_markup=kb.as_markup())
        await send_admin_alert(f"✅ {message.from_user.full_name} завершил аудит. Индекс: {idx}%")
        await state.clear()

@dp.callback_query(F.data == "get_guide")
async def guide_cb(cb: types.CallbackQuery):
    """Выдача Гайда с проверкой завершения аудита"""
    # Проверка через Firestore или Кэш
    is_finished = False
    if db:
        doc = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(cb.from_user.id)).get()
        if doc.exists and doc.to_dict().get("last_status") == "audit_finished": is_finished = True
    
    if not is_finished and cb.from_user.id not in diagnostic_cache:
        return await cb.answer("🚫 Доступ закрыт! Сначала пройдите Аудит до конца.", show_alert=True)

    await cb.answer("Загрузка...")
    await send_guide_document(cb.message)

@dp.callback_query(F.data == "go_buy")
async def buy_cb(cb: types.CallbackQuery):
    """Трекинг перехода к покупке/практикуму"""
    await cb.answer(); await track_user_action(cb.from_user, "buy_clicked")
    await cb.message.answer(f"🚀 Твой путь к состоянию Автора здесь:\n{PRACTICUM_URL}")

@dp.message(Command("admin_stats"))
async def cmd_admin_stats(message: types.Message):
    """Служебная статистика проекта"""
    if message.from_user.id != ADMIN_ID or not db: return
    users = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").stream()
    stats = {"total": 0, "finished": 0, "buy": 0}
    for u in users:
        d = u.to_dict(); stats["total"] += 1
        st = d.get("last_status", "")
        if st == "audit_finished": stats["finished"] += 1
        if d.get("last_status") == "buy_clicked": stats["buy"] += 1
    await message.answer(f"📊 **СТАТИСТИКА IDENTITY LAB**\n\n👥 Всего: {stats['total']}\n✅ Финиш: {stats['finished']}\n💰 Переходы: {stats['buy']}")

# =================================================================================================
# 7. ВЕБ-СЕРВЕР (REPORTS & WEBHOOK)
# =================================================================================================

async def handle_root(r): return web.Response(text="Identity Lab System Active")

async def handle_report(request):
    """Динамическая генерация HTML отчета для пользователя"""
    try:
        uid = request.match_info['user_id']
        # Сначала ищем в кэше (быстрее)
        data = diagnostic_cache.get(int(uid))
        # Если нет в кэше, тянем из Firestore
        if not data and db:
            doc = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(uid).get()
            if doc.exists: data = doc.to_dict()
        
        if data:
            html = HTML_TEMPLATE.format(
                user_name=data.get('name', 'Гость'), 
                idx=data.get('index', 75), inv_idx=100-data.get('index', 75),
                report_text=data.get('report', '').replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="<h1>Отчет не найден. Пройдите аудит в боте.</h1>", content_type='text/html', status=404)
    except: 
        return web.Response(text="Ошибка доступа.", status=500)

async def on_startup(bot: Bot):
    """Настройка бота при запуске контейнера на Render"""
    if RENDER_URL: await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Запуск/Синхронизация"),
        types.BotCommand(command="menu", description="Главное меню")
    ])
    await send_admin_alert("🚀 **Identity Lab v11.3 СИНХРОНИЗИРОВАН**\nAI Engines: Gemini + Cerebras Active.")

def main():
    """Точка входа в приложение"""
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
