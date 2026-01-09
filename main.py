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

# Корректная работа с сигналами на Linux/Render
if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# Загрузка конфигурации
TOKEN = os.getenv("BOT_TOKEN")
AI_KEY = os.getenv("AI_API_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") 
PORT = int(os.getenv("PORT", 10000))

# Webhook конфигурация
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# ID Администратора и Канала
CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013

# Ресурсы
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

# Инициализация AI
ai_client = None
if AI_KEY and CEREBRAS_AVAILABLE:
    try:
        ai_client = AsyncCerebras(api_key=AI_KEY)
        logger.info("✅ Cerebras AI Engine: ONLINE (Identity Lab v5.5)")
    except Exception as e:
        logger.error(f"❌ AI Engine Init Error: {e}")

# In-memory хранилище данных сессий
diagnostic_cache = {}

class AuditState(StatesGroup):
    answering = State()

# =================================================================================================
# 2. МОНИТОРИНГ (АЛЕРТЫ АДМИНУ)
# =================================================================================================

async def send_admin_alert(text: str):
    """Системные уведомления Александру в личку"""
    try:
        await bot.send_message(ADMIN_ID, text, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Alert error: {e}")

# =================================================================================================
# 3. МЕТОДОЛОГИЯ: ВОПРОСЫ (v4.8.1)
# =================================================================================================

QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни или в каком деле ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают того результата, на который ты рассчитываешь.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Какой ты теперь? Подбери 3–4 прилагательных (например: спокойный, мощный, свободный). Как ты себя чувствуешь?",
    "📍 **Точка 3: Архивный режим.**\nКакая «мыслительная жвачка» крутится у тебя в голове, когда ты думаешь о переменах? Какие сомнения или доводы ты себе приводишь, чтобы оправдать текущую ситуацию?",
    "📍 **Точка 4: Сцена.**\nПредставь перед собой пустую сцену и вынеси на неё то, что тебе мешает (твой затык). Если бы оно было образом или предметом... на что бы оно могло быть похоже?",
    "📍 **Точка 5: Детекция сигнала.**\nПосмотри на этот предмет на той сцене перед собой. Где и какое ощущение возникает в теле (сжатие, холод, ком)? Опиши, что именно ты сейчас делаешь со своим телом: может, напрягаешь мышцы или задерживаешь дыхание?",
    "📍 **Точка 6: Биологическое Алиби.**\nТело всегда действует логично. Как ты думаешь, от чего тебя пытается защитить или уберечь эта телесная реакция при взгляде на препятствие?",
    "📍 **Точка 7: Реинтеграция.**\nКакое качество в поведении других людей тебя раздражает сильнее всего (наглость, навязчивость, грубость)? Если представить, что за этим качеством стоит какая-то скрытая сила — что это за сила? Как бы ты мог использовать её себе на пользу?",
    "📍 **Точка 8: Команда Автора.**\nТы готов признать себя Автором того, что происходит в твоем теле и твоей жизни, и перенастроить внутренний автопилот на реализацию твоих замыслов прямо сейчас?"
]

# Промпт для ИИ
SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР ИДЕНТИЧНОСТИ IDENTITY LAB. Тон: Технический, научный. Обращайся только на "ТЫ".
ЗАДАЧА: Сформировать отчет.
1. АВТОРСТВО: Пиши "Ты сам сжимаешь [маркер]", возвращая ответственность.
2. СИНТЕЗ РОЛИ: В МЕТА-МАЯКЕ синтезируй ЕДИНУЮ РОЛЬ (например, "Свободный Творец").
3. МЕТАФОРМУЛА (v5.5): «Я Автор. Я ПРИЗНАЮ, что сам создаю этот сигнал [маркер] — это мой ресурс. Я НАПРАВЛЯЮ его на активацию [Синтезированная Роль]».
"""

# =================================================================================================
# 4. ПРЕМИАЛЬНЫЙ HTML ШАБЛОН (Веб-отчет)
# =================================================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Identity Lab: Personal Audit</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; }}
        body {{ background-color: var(--bg); color: #e0e0e0; font-family: 'Rajdhani', sans-serif; }}
        .card {{ background: rgba(15,15,15,0.98); border: 1px solid #222; border-left: 5px solid var(--gold); border-radius: 12px; transition: all 0.4s; }}
        .card:hover {{ border-left-color: var(--cyan); box-shadow: 0 0 30px rgba(212, 175, 55, 0.15); }}
        .gold-text {{ color: var(--gold); text-shadow: 0 0 10px rgba(212, 175, 55, 0.3); }}
        .btn {{ background: linear-gradient(135deg, #b4932c 0%, #D4AF37 100%); color: black; font-weight: 800; padding: 16px 40px; border-radius: 8px; text-transform: uppercase; display: inline-block; text-decoration: none; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(212, 175, 55, 0.4); }} 70% {{ box-shadow: 0 0 0 20px rgba(212, 175, 55, 0); }} 100% {{ box-shadow: 0 0 0 0 rgba(212, 175, 55, 0); }} }}
        .mono {{ font-family: 'Roboto Mono', monospace; }}
    </style>
</head>
<body class="p-6 md:p-12 max-w-5xl mx-auto">
    <header class="text-center mb-16 border-b border-gray-900 pb-10">
        <h1 class="text-6xl font-bold gold-text uppercase tracking-tighter">IDENTITY LAB</h1>
        <p class="text-gray-500 mt-4 tracking-widest font-mono">ТЕХНИЧЕСКИЙ ПАСПОРТ: {user_name}</p>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
        <div class="card p-8 flex flex-col items-center">
            <h3 class="text-gray-400 uppercase text-sm mb-6">Индекс Автоматизма</h3>
            <canvas id="idxChart" width="180" height="180"></canvas>
            <div class="text-4xl font-bold mt-6 gold-text">{index}%</div>
        </div>
        <div class="card p-8">
            <h3 class="text-gray-400 uppercase text-sm mb-4">Нейро-статус</h3>
            <p class="text-gray-300 leading-relaxed">
                Зафиксирована инерция старых доминант. Ваша Дефолт-система (DMN) утилизирует 80% энергии на поддержание гомеостаза. Требуется Сдвиг.
            </p>
        </div>
    </div>

    <div class="card p-10 mb-12">
        <h2 class="text-2xl font-bold mb-6 border-b border-gray-800 pb-2 uppercase">Анализ Коннектома</h2>
        <div class="mono text-gray-300 leading-relaxed text-sm md:text-base">
            {report_html}
        </div>
    </div>

    <div class="text-center space-y-10">
        <p class="text-gray-500 italic text-sm">Окно нейропластичности для фиксации этого Сдвига открыто 4 часа.</p>
        <a href="{practicum_link}" class="btn">АКТИВИРОВАТЬ АВТОРА</a>
        <br>
        <a href="{protocol_link}" class="text-gray-600 hover:text-gold transition-colors text-xs uppercase underline font-mono">Скачать Протокол PDF</a>
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
            options: {{ cutout: '85%', plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>
"""

# =================================================================================================
# 5. ГЛУБОКИЙ FALLBACK (ЛОКАЛЬНЫЙ МОЗГ БОТА)
# =================================================================================================

def calculate_automatism_index(answers):
    text = " ".join(answers).lower()
    bad = ['не знаю', 'боюсь', 'страх', 'лень', 'сомневаюсь', 'тупик', 'тяжело', 'сжатие', 'стена', 'вряд ли']
    count = sum(1 for b in bad if b in text)
    return min(95, max(65, 72 + (count * 3)))

def generate_detailed_fallback_report(answers):
    """Сборка полноценного отчета без участия облачного ИИ"""
    idx = calculate_automatism_index(answers)
    safe = [a if a else "..." for a in answers]
    while len(safe) < 8: safe.append("...")
    
    # Синтез роли из ответов
    words = safe[1].replace(',', ' ').split()
    role_base = words[0].capitalize() if words else "Автор"
    synthesized_role = f"Мощный {role_base}"
    
    report = f"""⬛️ [ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ: FALLBACK MODE] 📀

📊 ИНДЕКС АВТОМАТИЗМА: {idx}%

🧠 ДИАГНОСТИКА КОНТУРОВ:
Образ "{safe[3]}" блокирует систему через сигнал "{safe[4]}". Это работа Биологического Алиби: твой мозг защищает тебя от новизны, считая её угрозой. Мысли "{safe[2]}" — это способ удержать гомеостаз.

🧬 РЕАКТОР ИДЕНТИЧНОСТИ:
Раздражение на "{safe[6]}" — это твоя заблокированная сила. Мы возвращаем этот ресурс тебе.

📡 МЕТА-МАЯК (Эталонная Идентичность):
{synthesized_role}.

🛠 МИНИ-ПРАКТИКУМ:
1. Посмотри на образ "{safe[3]}" на сцене.
2. Признай: «Это Я сжимаю {safe[4]}, чтобы защитить свой покой. Это МОЯ энергия».
3. Впитай силу из образа. Позволь ему раствориться. Почувствуй себя {synthesized_role}.

⚡️ КОД ПЕРЕПРОШИВКИ (МЕТАФОРМУЛА):
Произнеси вслух: «Я Автор. Я ПРИЗНАЮ, что сам создаю этот сигнал {safe[4]} — это мой ресурс. Я НАПРАВЛЯЮ его на активацию {synthesized_role}»."""
    return report

async def get_ai_report(answers):
    if not ai_client: return generate_detailed_fallback_report(answers)
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    
    for attempt in range(3):
        try:
            resp = await ai_client.chat.completions.create(
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data_str}],
                model="llama-3.3-70b", temperature=0.4, max_completion_tokens=2500
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"AI Fail {attempt+1}: {e}")
            if attempt == 2:
                # АЛЕРТ АДМИНУ: Закончились токены или упал API
                await send_admin_alert(f"🚨 СБОЙ CEREBRAS API!\nЮзер: {len(answers)} ответов.\nПричина: {str(e)[:150]}\nВключен локальный Fallback.")
            await asyncio.sleep(2 ** attempt)
            
    return generate_detailed_fallback_report(answers)

# =================================================================================================
# 6. КЛАВИАТУРЫ
# =================================================================================================

def get_author_menu():
    return ReplyKeyboardBuilder().row(types.KeyboardButton(text="≡ МЕНЮ")).as_markup(resize_keyboard=True)

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🚀 ЗАПУСТИТЬ АУДИТ", callback_data="run_audit"))
    builder.row(types.InlineKeyboardButton(text="📥 СКАЧАТЬ ГАЙД", callback_data="get_pdf"))
    builder.row(types.InlineKeyboardButton(text="⚡️ ПРАКТИКУМ", url=PRACTICUM_URL))
    builder.row(types.InlineKeyboardButton(text="📢 КАНАЛ", url=CHANNEL_LINK))
    builder.row(types.InlineKeyboardButton(text="💬 ПОДДЕРЖКА", url=SUPPORT_LINK))
    return builder.as_markup()

# =================================================================================================
# 7. ОБРАБОТЧИКИ (HANDLERS)
# =================================================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    is_sub = await check_sub(message.from_user.id)
    
    if not is_sub:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📢 Вступить в Лабораторию", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="verify"))
        caption = (
            "Лаборатория идентичности «Метаформула жизни»\n\n"
            "Я — Мета-Навигатор. Я помогу тебе найти точки, где ты сам блокируешь свою энергию, и превратить их в топливо для реализации замыслов.\n\n"
            "Для старта подпишись на наш канал:"
        )
        await message.answer_photo(LOGO_URL, caption=caption, reply_markup=kb.as_markup())
    else:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="🚀 НАЧАТЬ АУДИТ", callback_data="run_audit"))
        caption = (
            "Внутренний канал связи открыт.\n\n"
            "Система готова обнаружить твои скрытые механизмы инерции. Готов занять место Автора?"
        )
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption=caption, reply_markup=get_author_menu())
        await message.answer("Управление активно:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "verify")
async def verify_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ разрешен!")
        await cmd_start(cb.message, state)
    else:
        await cb.answer("❌ Подписка не найдена!", show_alert=True)

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 Панель управления Identity Lab:", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "run_audit")
async def run_audit_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(step=0, answers=[])
    await cb.message.answer(
        "🔬 Инициализация протокола сканирования.\n\n"
        "Отвечай максимально честно. Твое тело — самый точный прибор, оно не врет."
    )
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0], parse_mode="Markdown")
    await state.set_state(AuditState.answering)

@dp.callback_query(F.data == "get_pdf")
async def get_pdf_cb(cb: types.CallbackQuery):
    if cb.from_user.id not in diagnostic_cache:
        await cb.answer("Сначала пройди аудит! Гайд — это твоя карта после диагностики.", show_alert=True)
    else:
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
                        document=types.BufferedInputFile(data, filename="ПРОТОКОЛ_IDENTITY_v5.5.pdf"),
                        caption="📘 Твой Гайд готов. Изучи раздел «Ловушка Интеллекта»."
                    )
    except: await message.answer(f"Прямая ссылка на гайд: {PROTOCOL_URL}")

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
        
        diagnostic_cache[message.from_user.id] = {
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
        
        # ОТЧЕТ АДМИНУ (Александру)
        try:
            ans_str = "\n".join([f"{i+1}: {a}" for i, a in enumerate(answers)])
            await send_admin_alert(
                f"🔔 НОВАЯ ДИАГНОСТИКА v5.5!\n👤 {message.from_user.full_name} (@{message.from_user.username})\n\n"
                f"📝 ОТВЕТЫ:\n{ans_str}\n\n"
                f"🧠 ОТЧЕТ:\n{report[:1500]}"
            )
        except: pass
        await state.clear()

# =================================================================================================
# 8. ВЕБ-СЕРВЕР (AIOHTTP)
# =================================================================================================

async def handle_home(request):
    return web.Response(text="Identity Lab System v5.5 ONLINE", content_type='text/plain')

async def handle_report(request):
    try:
        user_id = int(request.match_info['user_id'])
        if user_id in diagnostic_cache:
            d = diagnostic_cache[user_id]
            html = HTML_TEMPLATE.format(
                user_name=d['user']['name'],
                index=d['index'], remain=100 - d['index'],
                report_html=d['report'].replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="Отчет не найден. Пройди аудит в боте.", status=404)
    except: return web.Response(text="Ошибка доступа.", status=500)

async def on_startup(bot: Bot):
    logger.info(f"🚀 Установка вебхука: {WEBHOOK_URL}")
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    # УВЕДОМЛЕНИЕ О ЗАПУСКЕ
    await send_admin_alert(f"🚀 Identity Lab v5.5 УСПЕШНО ЗАПУЩЕН.\nПорт: {PORT}\nСтатус ИИ: {'✅' if ai_client else '❌'}")

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
