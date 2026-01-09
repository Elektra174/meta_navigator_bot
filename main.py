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
# 1. СИСТЕМНЫЕ НАСТРОЙКИ И БЕЗОПАСНОСТЬ
# =================================================================================================

if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# Загрузка переменных окружения
TOKEN = os.getenv("BOT_TOKEN")
AI_KEY = os.getenv("AI_API_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") 
PORT = int(os.getenv("PORT", 10000))

# Настройки Webhook
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# Основные ID
CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013

# Ресурсы проекта
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo11.png"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/Autopilot_System_Protocol.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни"
CHANNEL_LINK = "https://t.me/metaformula_life"
SUPPORT_LINK = "https://t.me/lazalex81"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

ai_client = None
if AI_KEY and CEREBRAS_AVAILABLE:
    try:
        ai_client = AsyncCerebras(api_key=AI_KEY)
        logger.info("✅ Cerebras AI Engine: ONLINE (Identity Lab v5.3)")
    except Exception as e:
        logger.error(f"❌ AI Engine Init Error: {e}")

# Внутреннее хранилище
diagnostic_data = {}

class AuditState(StatesGroup):
    answering = State()

# =================================================================================================
# 2. МЕТОДОЛОГИЯ: ВОПРОСЫ (v4.8.1)
# =================================================================================================

QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни или в каком деле ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают того результата, на который ты рассчитываешь.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Какой ты теперь? Подбери 3–4 слова (например: спокойный, мощный, свободный). Как ты себя чувствуешь и как теперь смотришь на мир?",
    "📍 **Точка 3: Архивный режим.**\nКакая «мыслительная жвачка» крутится у тебя в голове, когда ты думаешь о переменах? Какие сомнения или доводы ты себе приводишь, чтобы оправдать текущую ситуацию?",
    "📍 **Точка 4: Сцена.**\nПредставь перед собой пустую сцену и вынеси на неё то, что тебе мешает (твой затык). Если бы оно было образом или предметом... на что бы оно могло быть похоже?",
    "📍 **Точка 5: Детекция сигнала.**\nПосмотри на этот предмет на той сцене перед собой. Где и какое ощущение возникает в теле (сжатие, холод, ком)? Опиши, что именно ты сейчас делаешь со своим телом: может, напрягаешь мышцы или задерживаешь дыхание?",
    "📍 **Точка 6: Биологическое Алиби.**\nТело всегда действует логично. Как ты думаешь, от чего тебя пытается защитить или уберечь эта телесная реакция при взгляде на препятствие?",
    "📍 **Точка 7: Реинтеграция.**\nКакое качество в поведении других людей тебя раздражает сильнее всего (наглость, навязчивость, грубость)? Если представить, что за этим качеством стоит какая-то скрытая сила — что это за сила? Как бы ты мог использовать её себе на пользу?",
    "📍 **Точка 8: Команда Автора.**\nТы готов признать себя Автором того, что происходит в твоем теле и твоей жизни, и перенастроить внутренний автопилот на реализацию твоих замыслов прямо сейчас?"
]

SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР ИДЕНТИЧНОСТИ IDENTITY LAB. Тон: Технический, научный. Обращайся только на "ТЫ".

ЗАДАЧА: Сформировать отчет на основе соматического аудита.
1. АВТОРСТВО: Пиши "Ты сам сжимаешь [маркер]", возвращая ответственность.
2. СИНТЕЗ РОЛИ: В МЕТА-МАЯКЕ синтезируй ЕДИНУЮ РОЛЬ (например, "Свободный Творец"), объединяя ответ 2 и скрытую силу из ответа 7.
3. МЕТАФОРМУЛА (v5.3): «Я Автор. Я ПРИЗНАЮ, что сам создаю этот сигнал [маркер] — это мой ресурс. Я НАПРАВЛЯЮ его на активацию [Синтезированная Роль]».

СТРУКТУРА:
⬛️ [ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ] 📀
📊 ИНДЕКС АВТОМАТИЗМА: [X]%
🧠 ДИАГНОСТИКА КОНТУРОВ: [Образ и сигнал. Объясни ДСМ и гомеостаз простым языком].
🧬 РЕАКТОР ИДЕНТИЧНОСТИ: [Сила из раздражения].
📡 МЕТА-МАЯК: [Синтезированная РОЛЬ].
🛠 МИНИ-ПРАКТИКУМ: [Инструкция реинтеграции силы].
⚡️ КОД ПЕРЕПРОШИВКИ: [Формула].
"""

# =================================================================================================
# 3. ПРЕМИАЛЬНЫЙ HTML ШАБЛОН (Cyber-Mysticism)
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
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; }}
        body {{ background-color: var(--bg); color: #e0e0e0; font-family: 'Rajdhani', sans-serif; }}
        .card {{ background: rgba(15,15,15,0.98); border: 1px solid #222; border-left: 5px solid var(--gold); border-radius: 12px; transition: all 0.4s; position: relative; overflow: hidden; }}
        .card:hover {{ border-left-color: var(--cyan); box-shadow: 0 0 30px rgba(212, 175, 55, 0.15); }}
        .gold-text {{ color: var(--gold); text-shadow: 0 0 10px rgba(212, 175, 55, 0.3); }}
        .btn {{ background: linear-gradient(135deg, #b4932c 0%, #D4AF37 100%); color: black; font-weight: 800; padding: 16px 40px; border-radius: 8px; text-transform: uppercase; letter-spacing: 2px; display: inline-block; text-decoration: none; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(212, 175, 55, 0.4); }} 70% {{ box-shadow: 0 0 0 20px rgba(212, 175, 55, 0); }} 100% {{ box-shadow: 0 0 0 0 rgba(212, 175, 55, 0); }} }}
        .mono {{ font-family: 'Roboto Mono', monospace; }}
        .bg-grid {{ background-image: radial-gradient(circle, #1a1a1a 1px, transparent 1px); background-size: 30px 30px; }}
    </style>
</head>
<body class="bg-grid p-6 md:p-12 max-w-5xl mx-auto">
    <header class="text-center mb-16">
        <h1 class="text-5xl md:text-7xl font-bold tracking-tighter gold-text uppercase">IDENTITY LAB</h1>
        <p class="text-xl text-gray-500 mt-4 tracking-widest font-mono">РЕФАКТОРИНГ КОННЕКТОМА: {user_name}</p>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-8 mb-12">
        <div class="card p-8 flex flex-col items-center justify-center col-span-1">
            <h3 class="text-gray-400 uppercase text-sm mb-6">Индекс Автоматизма</h3>
            <canvas id="mainChart" width="200" height="200"></canvas>
            <div class="text-4xl font-bold mt-6 gold-text">{index}%</div>
        </div>
        <div class="card p-8 col-span-1 md:col-span-2">
            <h3 class="text-gray-400 uppercase text-sm mb-4">Статус Системы</h3>
            <p class="text-lg leading-relaxed italic text-gray-300">
                «Обнаружена высокая инерция старых нейронных цепей. Система находится в режиме "Биологического Алиби", блокируя экспансию ради сохранения гомеостаза.»
            </p>
            <div class="mt-8 flex gap-4">
                <div class="px-3 py-1 bg-red-900/30 border border-red-700 text-red-500 text-xs rounded font-mono">DMN: ACTIVE</div>
                <div class="px-3 py-1 bg-gold/10 border border-gold/40 text-gold text-xs rounded font-mono">AUTHOR: STANDBY</div>
            </div>
        </div>
    </div>

    <div class="card p-10 mb-12">
        <h2 class="text-3xl font-bold mb-10 border-b border-gray-800 pb-4 tracking-tight">ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ</h2>
        <div class="mono text-gray-300 text-base md:text-lg leading-relaxed space-y-6">
            {report_html}
        </div>
    </div>

    <div class="text-center space-y-8 pb-20">
        <div class="p-6 bg-yellow-500/5 border border-yellow-500/20 rounded-lg max-w-2xl mx-auto italic text-sm text-gray-400">
            Внимание! Соматический Сдвиг затухает через 4 часа. Рекомендуется немедленная инсталляция.
        </div>
        <a href="{practicum_link}" class="btn">АКТИВИРОВАТЬ ИДЕНТИЧНОСТЬ</a>
        <br>
        <a href="{protocol_link}" class="text-gray-600 hover:text-gold transition-colors text-xs uppercase tracking-widest font-mono underline decoration-gold/30">Скачать PDF Протокол</a>
    </div>

    <script>
        const ctx = document.getElementById('mainChart').getContext('2d');
        new Chart(ctx, {{
            type: 'doughnut',
            data: {{
                datasets: [{{
                    data: [{index}, {remain}],
                    backgroundColor: ['#D4AF37', '#111'],
                    borderWidth: 0,
                    hoverOffset: 0
                }}]
            }},
            options: {{ cutout: '85%', plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>
"""

# =================================================================================================
# 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (АНАЛИТИКА)
# =================================================================================================

def calculate_automatism_index(answers):
    text = " ".join(answers).lower()
    stagnation_markers = ['не знаю', 'боюсь', 'страх', 'лень', 'сомневаюсь', 'тупик', 'тяжело', 'сжатие', 'стена']
    count = sum(1 for m in stagnation_markers if m in text)
    return min(95, max(65, 75 + (count * 3)))

def generate_fallback_report(answers):
    """Генерация детального отчета v4.8.1 без ИИ"""
    idx = calculate_automatism_index(answers)
    safe = answers + ["..."] * (8 - len(answers))
    
    # Пытаемся вычленить Роль
    raw_role = safe[1].split(',')[0].strip()
    synthesized_role = f"Мощный {raw_role.capitalize()}" if raw_role else "Автор своей жизни"
    
    report = f"""⬛️ [ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ] 📀

📊 ИНДЕКС АВТОМАТИЗМА: {idx}%

🧠 ДИАГНОСТИКА КОНТУРОВ:
Образ "{safe[3]}" блокирует систему через телесный сигнал "{safe[4]}". Это работа Биологического Алиби: мозг защищает тебя от перемен, используя ДСМ (Дефолт-систему) для прокрутки сомнений.

🧬 РЕАКТОР ИДЕНТИЧНОСТИ:
Раздражение на качество "{safe[6]}" скрывает твою силу. Мы заберем этот ресурс.

📡 МЕТА-МАЯК:
Твоя эталонная идентичность — {synthesized_role}.

🛠 МИНИ-ПРАКТИКУМ:
1. Посмотри на образ "{safe[3]}" на той сцене.
2. Признай: «Это Я сжимаю {safe[4]}, чтобы защитить систему. Это МОЯ энергия».
3. Впитай силу из образа. Позволь ему раствориться.

⚡️ КОД ПЕРЕПРОШИВКИ:
«Я Автор. Я ПРИЗНАЮ, что сам создаю этот сигнал {safe[4]} — это мой ресурс. Я НАПРАВЛЯЮ его на активацию {synthesized_role}»."""
    return report

async def get_ai_report(answers):
    if not ai_client: return generate_fallback_report(answers)
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    for attempt in range(3):
        try:
            resp = await ai_client.chat.completions.create(
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data_str}],
                model="llama-3.3-70b", temperature=0.4, max_completion_tokens=2500
            )
            return resp.choices[0].message.content
        except: await asyncio.sleep(2 ** attempt)
    return generate_fallback_report(answers)

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# =================================================================================================
# 5. КЛАВИАТУРЫ
# =================================================================================================

def get_reply_menu():
    return ReplyKeyboardBuilder().row(types.KeyboardButton(text="≡ МЕНЮ")).as_markup(resize_keyboard=True)

def get_inline_nav():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 Новый Аудит", callback_data="reset_audit"))
    builder.row(types.InlineKeyboardButton(text="📥 Скачать Гайд", callback_data="download_guide"))
    builder.row(types.InlineKeyboardButton(text="⚡️ Практикум", url=PRACTICUM_URL))
    builder.row(types.InlineKeyboardButton(text="📢 Канал", url=CHANNEL_LINK))
    builder.row(types.InlineKeyboardButton(text="💬 Поддержка", url=SUPPORT_LINK))
    return builder.as_markup()

# =================================================================================================
# 6. ОБРАБОТЧИКИ (HANDLERS)
# =================================================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    is_sub = await check_sub(message.from_user.id)
    
    if not is_sub:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📢 Вступить в Лабораторию", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="verify_sub"))
        caption = (
            "Лаборатория идентичности «Метаформула жизни»\n\n"
            "Приветствую. Я — Мета-Навигатор. Я помогу тебе найти точки, где ты сам блокируешь свою энергию, и превратить их в топливо для реализации замыслов.\n\n"
            "Для старта подпишись на наш канал:"
        )
        await message.answer_photo(LOGO_URL, caption=caption, reply_markup=kb.as_markup())
    else:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="🚀 ЗАПУСТИТЬ АУДИТ", callback_data="start_audit"))
        caption = (
            "Внутренний канал связи открыт.\n\n"
            "Система готова обнаружить твои скрытые механизмы инерции. Готов занять место Автора?"
        )
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption=caption, reply_markup=get_reply_menu())
        await message.answer("Управление активно:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "verify_sub")
async def verify_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ открыт!")
        await cmd_start(cb.message, state)
    else:
        await cb.answer("❌ Подписка не обнаружена!", show_alert=True)

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 Панель управления Identity Lab:", reply_markup=get_inline_nav())

@dp.callback_query(F.data == "start_audit")
@dp.callback_query(F.data == "reset_audit")
async def start_audit_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(step=0, answers=[])
    await cb.message.answer(
        "🔬 Инициализация протокола сканирования.\n\n"
        "Отвечай максимально честно. Тело — самый точный прибор, оно не врет."
    )
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0], parse_mode="Markdown")
    await state.set_state(AuditState.answering)

@dp.callback_query(F.data == "download_guide")
async def guide_cb(cb: types.CallbackQuery):
    if cb.from_user.id not in diagnostic_data:
        await cb.answer("Сначала пройди аудит! Гайд — это награда за диагностику.", show_alert=True)
    else:
        await cb.answer("Отправляю...")
        await send_gaid(cb.message)

async def send_gaid(message: types.Message):
    try:
        await message.answer("📥 Формирую твой Технический Паспорт (Гайд)...")
        async with ClientSession() as sess:
            async with sess.get(PROTOCOL_URL) as r:
                if r.status == 200:
                    pdf = await r.read()
                    await message.answer_document(
                        document=types.BufferedInputFile(pdf, filename="ПРОТОКОЛ_IDENTITY_v5.3.pdf"),
                        caption="📘 Твой Гайд готов. Изучи раздел «Ловушка Интеллекта»."
                    )
    except: await message.answer(f"Ссылка: {PROTOCOL_URL}")

@dp.message(AuditState.answering)
async def flow_handler(message: types.Message, state: FSMContext):
    if not message.text or message.text == "≡ МЕНЮ": return
    
    data = await state.get_data()
    step = data.get('step', 0)
    answers = data.get('answers', [])
    answers.append(message.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step + 1, answers=answers)
        await message.answer(QUESTIONS[step+1], parse_mode="Markdown")
    else:
        progress = await message.answer("🧠 Идет дешифровка твоего нейропрофиля... [||||||||||] 60%")
        report = await get_ai_report(answers)
        idx = calculate_automatism_index(answers)
        
        diagnostic_data[message.from_user.id] = {
            "user": {"name": message.from_user.full_name, "id": message.from_user.id},
            "answers": answers, "report": report, "index": idx,
            "date": datetime.now().strftime("%d.%m %H:%M")
        }
        
        await progress.edit_text("🧬 Внутренний канал связи синхронизирован. [||||||||||] 100%")
        await message.answer(report)
        await send_gaid(message)
        
        kb = InlineKeyboardBuilder()
        url = f"{RENDER_URL}/report/{message.from_user.id}"
        kb.row(types.InlineKeyboardButton(text="📊 ОТКРЫТЬ ВЕБ-ОТЧЕТ", url=url))
        kb.row(types.InlineKeyboardButton(text="⚡️ ПЕРЕЙТИ К ПРАКТИКУМУ", url=PRACTICUM_URL))
        
        await asyncio.sleep(2)
        await message.answer("🎯 Аудит завершен. Чтобы закрепить Сдвиг — изучи веб-отчет:", reply_markup=kb.as_markup())
        
        # Лог админу с ответами
        try:
            ans_str = "\n".join([f"{i+1}: {a}" for i, a in enumerate(answers)])
            await bot.send_message(ADMIN_ID, f"🔔 Новая диагностика!\n👤 {message.from_user.full_name}\n\nОТВЕТЫ:\n{ans_str}\n\nОТЧЕТ:\n{report[:1500]}")
        except: pass
        await state.clear()

# =================================================================================================
# 7. ВЕБ-СЕРВЕР (AIOHTTP)
# =================================================================================================

async def handle_home(request):
    return web.Response(text="Identity Lab v5.3 ONLINE", content_type='text/plain')

async def handle_report(request):
    try:
        user_id = int(request.match_info['user_id'])
        if user_id in diagnostic_data:
            d = diagnostic_data[user_id]
            html = HTML_TEMPLATE.format(
                user_name=d['user']['name'],
                index=d['index'], remain=100 - d['index'],
                report_html=d['report'].replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="Отчет не найден.", status=404)
    except: return web.Response(text="Ошибка доступа.", status=500)

async def on_startup(bot: Bot):
    logger.info(f"🚀 Установка вебхука: {WEBHOOK_URL}")
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

def main():
    app = web.Application()
    app.router.add_get('/', handle_home)
    app.router.add_get('/health', handle_home)
    app.router.add_get('/report/{user_id}', handle_report)
    
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    main()
