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

# =================================================================================================
# 1. СИСТЕМНЫЕ НАСТРОЙКИ И БЕЗОПАСНОСТЬ (ПОЛНЫЙ КОНТУР)
# =================================================================================================

# Предотвращение зомби-процессов на Linux/Render
if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Импорт Cerebras SDK с обработкой ошибок
try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# Загрузка конфигурации из Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
AI_KEY = os.getenv("AI_API_KEY")
# URL сервиса на Render (обязательно настройте RENDER_EXTERNAL_URL в панели Render)
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
PORT = int(os.getenv("PORT", 10000))

# Параметры Webhook
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# Основные ID проекта
CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013

# Ресурсы (Эталонный стиль Obsidian & Liquid Gold)
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo11.png"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/Autopilot_System_Protocol.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни"
CHANNEL_LINK = "https://t.me/metaformula_life"
SUPPORT_LINK = "https://t.me/lazalex81"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация Cerebras AI
ai_client = None
if AI_KEY and CEREBRAS_AVAILABLE:
    try:
        ai_client = AsyncCerebras(api_key=AI_KEY)
        logger.info("✅ Cerebras AI Engine: ONLINE (Identity Lab v6.2)")
    except Exception as e:
        logger.error(f"❌ AI Engine Init Error: {e}")

# Глобальное хранилище диагностических данных для веб-отчетов
# В продакшене лучше использовать БД, но для текущих задач памяти достаточно
diagnostic_cache = {}

class AuditState(StatesGroup):
    answering = State()

# =================================================================================================
# 2. УВЕДОМЛЕНИЯ АДМИНИСТРАТОРА
# =================================================================================================

async def send_admin_alert(text: str):
    """Отправка системных уведомлений Александру"""
    try:
        await bot.send_message(ADMIN_ID, text, disable_web_page_preview=True, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Alert error: {e}")

# =================================================================================================
# 3. МЕТОДОЛОГИЯ: ВОПРОСЫ И ПРОМПТ (v6.2)
# =================================================================================================

QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни или в каком деле ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают результата.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Какой ты теперь? Подбери 3–4 слова (например: спокойный, мощный, свободный). Как ты себя чувствуешь?",
    "📍 **Точка 3: Архивный режим.**\nКакая «мыслительная жвачка» крутится у тебя в голове, когда ты думаешь о переменах? Какие сомнения ты себе приводишь?",
    "📍 **Точка 4: Сцена.**\nПредставь перед собой пустую сцену и вынеси на неё то, что тебе мешает (твой затык). На что бы оно могло быть похоже?",
    "📍 **Точка 5: Детекция сигнала.**\nПосмотри на этот предмет на сцене. Где и какое ощущение возникает в теле (сжатие, холод, ком)? Что ты именно сейчас делаешь своим телом (напрягаешь мышцы, задерживаешь дыхание)?",
    "📍 **Точка 6: Биологическое Алиби.**\nТело всегда действует логично. Как ты думаешь, от чего тебя пытается защитить или уберечь эта телесная реакция?",
    "📍 **Точка 7: Реинтеграция.**\nКакое качество в поведении других людей тебя раздражает сильнее всего? Если представить, что за этим качеством стоит какая-то скрытая сила — что это за сила и как бы ты мог использовать её себе на пользу?",
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
# 4. HTML ШАБЛОН ВЕБ-ОТЧЕТА
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
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; }}
        body {{ background-color: var(--bg); color: #e0e0e0; font-family: 'Rajdhani', sans-serif; }}
        .card {{ background: rgba(15,15,15,0.98); border: 1px solid #222; border-left: 5px solid var(--gold); border-radius: 12px; transition: all 0.4s; }}
        .card:hover {{ border-left-color: var(--cyan); box-shadow: 0 0 30px rgba(212, 175, 55, 0.15); }}
        .gold-text {{ color: var(--gold); text-shadow: 0 0 10px rgba(212, 175, 55, 0.3); }}
        .btn {{ background: linear-gradient(135deg, #b4932c 0%, #D4AF37 100%); color: black; font-weight: 800; padding: 16px 40px; border-radius: 8px; text-transform: uppercase; letter-spacing: 2px; display: inline-block; text-decoration: none; }}
        .mono {{ font-family: 'Roboto Mono', monospace; }}
        canvas {{ max-width: 200px !important; max-height: 200px !important; }}
    </style>
</head>
<body class="p-6 md:p-12 max-w-5xl mx-auto">
    <header class="text-center mb-16 border-b border-gray-900 pb-10">
        <h1 class="text-5xl md:text-7xl font-bold gold-text uppercase tracking-tighter">IDENTITY LAB</h1>
        <p class="text-xl text-gray-500 mt-4 tracking-widest font-mono">ПЕРСОНАЛЬНАЯ КАРТА: {user_name}</p>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
        <div class="card p-8 flex flex-col items-center justify-center text-center">
            <h3 class="text-gray-400 uppercase text-xs mb-6 tracking-widest">Индекс Автоматизма</h3>
            <canvas id="idxChart"></canvas>
            <div class="text-5xl font-bold mt-6 gold-text">{index}%</div>
        </div>
        <div class="card p-8">
            <h3 class="text-gray-400 uppercase text-xs mb-4 tracking-widest">Статус системы</h3>
            <p class="text-gray-300 leading-relaxed text-lg">
                Зафиксирована высокая инерция биологических программ. Ваша Дефолт-система мозга (ДСМ) утилизирует энергию на удержание текущего состояния. Требуется немедленный Сдвиг в роль Автора.
            </p>
        </div>
    </div>

    <div class="card p-8 md:p-12 mb-12">
        <h2 class="text-2xl font-bold mb-8 border-b border-gray-800 pb-4 uppercase gold-text tracking-widest">Нейро-Синтез Данных</h2>
        <div class="mono text-gray-300 leading-relaxed text-sm md:text-base whitespace-pre-wrap">
{report_html}
        </div>
    </div>

    <div class="text-center space-y-12">
        <p class="text-gray-500 italic text-sm">Окно нейропластичности для фиксации этого результата открыто в течение 4 часов.</p>
        <a href="{practicum_link}" class="btn transform transition hover:scale-105">АКТИВИРОВАТЬ ИДЕНТИЧНОСТЬ</a>
        <div class="pt-8">
            <a href="{protocol_link}" class="text-gray-600 hover:gold-text text-xs uppercase tracking-widest font-mono underline">Скачать PDF Протокол</a>
        </div>
    </div>

    <script>
        const ctx = document.getElementById('idxChart').getContext('2d');
        new Chart(ctx, {{
            type: 'doughnut',
            data: {{
                datasets: [{{
                    data: [{index}, {remain}],
                    backgroundColor: ['#D4AF37', '#111'],
                    borderWidth: 0
                }}]
            }},
            options: {{ 
                cutout: '85%',
                plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }}
            }}
        }});
    </script>
</body>
</html>
"""

# =================================================================================================
# 5. ЛОГИКА АНАЛИЗА (AI + FALLBACK)
# =================================================================================================

def calculate_index(answers):
    """Расчет уровня застоя по ключевым словам (Fallback)"""
    text = " ".join(answers).lower()
    markers = ['не знаю', 'боюсь', 'страх', 'лень', 'тупик', 'тяжело', 'сжатие', 'ком', 'холод']
    count = sum(1 for m in markers if m in text)
    return min(95, max(60, 72 + (count * 4)))

async def get_ai_report(answers):
    """Запрос к Cerebras с механизмом ретраев и фолбэка"""
    if not ai_client:
        return "Ошибка: AI не инициализирован. Но ты — Автор. ПРИЗНАЙ свою силу."
    
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    
    for attempt in range(3):
        try:
            resp = await ai_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": data_str}
                ],
                model="llama-3.3-70b",
                temperature=0.4,
                max_completion_tokens=2500
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"AI Synthesis Error (Attempt {attempt+1}): {e}")
            if attempt == 2:
                await send_admin_alert(f"🚨 **КРИТИЧЕСКИЙ СБОЙ AI!**\nПользователь: {len(answers)} ответов.\nОшибка: `{str(e)[:100]}`")
            await asyncio.sleep(2 ** attempt)
    
    return "Синхронизация временно недоступна. Но код остается прежним: Я Автор. ПРИЗНАЮ свою силу."

async def check_sub(user_id):
    """Проверка подписки на канал"""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# =================================================================================================
# 6. КЛАВИАТУРЫ
# =================================================================================================

def get_reply_menu():
    """Нижняя синяя кнопка меню"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="≡ МЕНЮ"))
    return builder.as_markup(resize_keyboard=True)

def get_main_keyboard():
    """Инлайн-кнопки управления"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🚀 ЗАПУСТИТЬ АУДИТ", callback_data="run"))
    builder.row(types.InlineKeyboardButton(text="📥 СКАЧАТЬ ГАЙД", callback_data="get_guide"))
    builder.row(types.InlineKeyboardButton(text="⚡️ ПРАКТИКУМ", url=PRACTICUM_URL))
    builder.row(types.InlineKeyboardButton(text="💬 ПОДДЕРЖКА", url=SUPPORT_LINK))
    return builder.as_markup()

# =================================================================================================
# 7. ОБРАБОТЧИКИ ТЕЛЕГРАМ (HANDLERS)
# =================================================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    is_sub = await check_sub(message.from_user.id)
    
    if not is_sub:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check"))
        cap = (
            "👋 Лаборатория идентичности «Метаформула жизни»\n\n"
            "Я — Мета-Навигатор. Я помогу тебе найти точки утечки энергии и перехватить управление у биологического автопилота.\n\n"
            "Для начала работы подпишись на наш канал:"
        )
        await message.answer_photo(LOGO_URL, caption=cap, reply_markup=kb.as_markup())
    else:
        cap = (
            "🧠 Система синхронизирована.\n\n"
            "Я готов обнаружить программы, которые управляют твоими реакциями автоматически. Готов занять место Автора?"
        )
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption=cap, reply_markup=get_reply_menu())
        await message.answer("Выбери действие из панели управления:", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "check")
async def check_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ открыт!")
        await cmd_start(cb.message, state)
    else:
        await cb.answer("❌ Подписка не найдена!", show_alert=True)

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 Панель управления Identity Lab:", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "run")
async def audit_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(step=0, answers=[])
    await cb.message.answer("🔬 **Инициализация протокола.**\nОтвечай честно. Твоё тело — самый точный прибор.")
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0], parse_mode="Markdown")
    await state.set_state(AuditState.answering)

@dp.callback_query(F.data == "get_guide")
async def get_guide(cb: types.CallbackQuery):
    if cb.from_user.id not in diagnostic_cache:
        await cb.answer("🚫 Сначала пройдите Аудит!", show_alert=True)
        return
    await cb.answer("Отправляю...")
    await send_gaid(cb.message)

async def send_gaid(message: types.Message):
    try:
        await message.answer("📥 Формирую твой Технический Паспорт (Гайд)...")
        async with ClientSession() as session:
            async with session.get(PROTOCOL_URL) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    await message.answer_document(
                        types.BufferedInputFile(data, filename="ПРОТОКОЛ_IDENTITY.pdf"),
                        caption="📘 Твой Гайд готов. Изучи раздел «Ловушка Интеллекта»."
                    )
                else: raise Exception()
    except:
        await message.answer(f"📥 Ссылка на Гайд: {PROTOCOL_URL}")

@dp.message(AuditState.answering)
async def process_answers(message: types.Message, state: FSMContext):
    if not message.text or message.text == "≡ МЕНЮ": return
    
    data = await state.get_data()
    step, answers = data.get('step', 0), data.get('answers', [])
    answers.append(message.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step+1, answers=answers)
        await message.answer(QUESTIONS[step+1], parse_mode="Markdown")
    else:
        # Финал диагностики
        msg = await message.answer("🧠 **Дешифровка Коннектома... [||||||||||] 100%**")
        report = await get_ai_report(answers)
        idx = calculate_index(answers)
        
        # Сохранение в кэш для Веб-отчета
        diagnostic_cache[message.from_user.id] = {
            "name": message.from_user.full_name,
            "report": report,
            "index": idx,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        await msg.edit_text(report)
        await send_gaid(message)
        
        # Кнопки после завершения
        kb = InlineKeyboardBuilder()
        report_url = f"{RENDER_URL}/report/{message.from_user.id}"
        kb.row(types.InlineKeyboardButton(text="📊 ОТКРЫТЬ ВЕБ-ОТЧЕТ", url=report_url))
        kb.row(types.InlineKeyboardButton(text="⚡️ ПЕРЕЙТИ К ПРАКТИКУМУ", url=PRACTICUM_URL))
        kb.row(types.InlineKeyboardButton(text="≡ МЕНЮ", callback_data="menu_call"))
        
        await asyncio.sleep(2)
        await message.answer(
            "🎯 Аудит завершен. Изучи свою карту дешифровки и переходи к глубокой инсталляции новой роли:",
            reply_markup=kb.as_markup()
        )
        
        # Логирование админу
        try:
            ans_log = "\n".join([f"{i+1}: {a}" for i, a in enumerate(answers)])
            await send_admin_alert(f"🔔 **НОВАЯ ДИАГНОСТИКА!**\n👤 {message.from_user.full_name}\n\n**ОТВЕТЫ:**\n{ans_log}\n\n**ОТЧЕТ:**\n{report[:1000]}...")
        except: pass
        
        await state.clear()

@dp.callback_query(F.data == "menu_call")
async def menu_callback(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.answer("📋 Панель управления Identity Lab:", reply_markup=get_main_keyboard())

# =================================================================================================
# 8. ВЕБ-СЕРВЕР (AIOHTTP)
# =================================================================================================

async def handle_home(request):
    return web.Response(text="Identity Lab System v6.2 ONLINE", content_type='text/plain')

async def handle_report(request):
    """Генерация красивой страницы отчета"""
    try:
        user_id = int(request.match_info['user_id'])
        if user_id in diagnostic_cache:
            d = diagnostic_cache[user_id]
            html = HTML_TEMPLATE.format(
                user_name=d['name'],
                index=d['index'],
                remain=100-d['index'],
                report_html=d['report'].replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL,
                protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="Отчет не найден. Пройдите диагностику в боте @meta_navigator_bot", status=404)
    except Exception as e:
        logger.error(f"Web Report Error: {e}")
        return web.Response(text="Ошибка доступа к отчету.", status=500)

async def on_startup(bot: Bot):
    """Действия при запуске (Установка команд и вебхука)"""
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Запуск/Синхронизация"),
        types.BotCommand(command="menu", description="Панель управления"),
        types.BotCommand(command="help", description="Поддержка")
    ])
    
    if RENDER_URL:
        logger.info(f"🚀 Установка Webhook: {WEBHOOK_URL}")
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    
    await send_admin_alert("🚀 **Identity Lab v6.2 ЗАПУЩЕН**\nWebhook активен. Система дешифровки готова.")

def main():
    """Точка входа"""
    app = web.Application()
    app.router.add_get('/', handle_home)
    app.router.add_get('/report/{user_id}', handle_report)
    
    # Регистрация обработчика входящих обновлений Telegram
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    
    # Настройка aiogram-приложения внутри aiohttp
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    
    # Запуск
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
