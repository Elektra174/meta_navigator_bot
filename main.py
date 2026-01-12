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

# --- ОБЛАЧНЫЕ ТЕХНОЛОГИИ (AI & DB) ---
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai

try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# =================================================================================================
# 1. КОНФИГУРАЦИЯ СИСТЕМЫ
# =================================================================================================

if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
CEREBRAS_KEY = os.getenv("AI_API_KEY")
FIREBASE_KEY = os.getenv("FIREBASE_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
PORT = int(os.getenv("PORT", 10000))

app_id = "identity-lab-v11" # ID версии для Firestore

# Webhook
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# Ссылки и ID
CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013 
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logofirst.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo1.jpg"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/guide_id.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни" 
CHANNEL_LINK = "https://t.me/metaformula_life"
SUPPORT_LINK = "https://t.me/lazalex81"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация Базы Данных (Rule 1 Compliant)
db = None
if FIREBASE_KEY:
    try:
        cred_dict = json.loads(FIREBASE_KEY)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("✅ Firestore: CONNECTED")
    except Exception as e:
        logger.error(f"❌ Firestore Init Failure: {e}")

# Инициализация AI
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

ai_backup = None
if CEREBRAS_KEY and CEREBRAS_AVAILABLE:
    ai_backup = AsyncCerebras(api_key=CEREBRAS_KEY)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class AuditState(StatesGroup):
    answering = State()

# =================================================================================================
# 2. МЕТОДОЛОГИЯ: ВОПРОСЫ И ПРОМПТ
# =================================================================================================

QUESTIONS = [
    "📍 Точка 1: Локация.\nВ какой сфере жизни ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают того результата, на который ты рассчитываешь.",
    "📍 Точка 2: Идентичность.\nПредставь, что задача решена на 100%. Кто ты в этой точке? Опиши свою новую Идентичность (эталонную версию Я) 3–4 словами. Например: ясный, мощный, свободный.",
    "📍 Точка 3: Фоновый шум.\nКакая «мыслительная жвачка» крутится у тебя в голове (постоянные повторяющиеся мысли)? Какие сомнения твой мозг использует прямо сейчас, чтобы оправдать текущий застой?",
    "📍 Точка 4: Мета-позиция.\nЕсли бы твоё внутреннее препятствие было образом или предметом — на что бы оно могло быть похоже? Представь перед собой пустую сцену и вынеси этот образ на неё. Просто опиши его.",
    "📍 Точка 5: Детекция.\nПосмотри на предмет на той сцене перед собой. Где в теле возникает физический отклик (сжатие, холод, ком)? Опиши, что именно ты сейчас делаешь со своим телом (напрягаю мышцы, замираю)?",
    "📍 Точка 6: Скрытая потребность.\nТело действует логично. От чего тебя пытается защитить эта телесная реакция? (Биологическое Алиби — это оправдание мозга, чтобы сохранить твой гомеостаз — стабильность любой ценой).",
    "📍 Точка 7: Скрытый ресурс.\nКакое качество в поведении других людей тебя бесит сильнее всего? Какая скрытая сила за этим стоит? Как бы ты мог использовать её себе на пользу?",
    "📍 Точка 8: Команда Автора.\nТы готов признать себя Автором того, что происходит в твоем теле и твоей жизни, и запустить перенастройку своего биокомпьютера на реализацию твоих замыслов прямо сейчас?"
]

SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР IDENTITY LAB (ЛАБОРАТОРИЯ ИДЕНТИЧНОСТИ).
ЗАДАЧА: Сформировать технический отчет дешифровки автопилота. 
ТОН: Холодный, технический, директивный. Обращайся только на "ТЫ".

ПРАВИЛА ТЕРМИНОВ (РАСШИФРОВЫВАЙ В СКОБКАХ):
- Гомеостаз (стремление мозга сохранять всё как есть ради экономии ресурсов).
- ДСМ (Дефолт-система мозга, работающая в фоновом режиме автопилота).
- Амигдала (центр страха в мозге).
- Префронтальная кора (центр осознанного управления).

СТРОГИЕ ЗАПРЕТЫ:
- КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать символы ** (двойные звездочки) во всем тексте.

ЛОГИКА ОТЧЕТА:
1. ИНДЕКС АВТОМАТИЗМА: [Рассчитай % инерции системы от 65 до 95].
2. СТРАТЕГИЯ ЗАЩИТЫ: Объясни, что пользователь САМ создает сигнал [ответ 5] ради защиты от [6].
3. РЕИНТЕГРАЦИЯ: Сила из [7] заперта в зажиме [5]. Мы не боремся с ним — мы забираем и ПРИСВАИВАЕМ этот ресурс по праву Автора.
4. МЕТА-ИДЕНТИЧНОСТЬ: Синтезируй Идентичность на базе [2]. Объясни физику: как в этом состоянии Префронтальная кора подавляет шум Амигдалы.
5. КОД ПЕРЕПРОШИВКИ (МЕТАФОРМУЛА):
Я Автор. ПРИЗНАЮ, что сам создаю этот сигнал [ответ 5] — это мой ресурс. НАПРАВЛЯЮ его на активацию Идентичности [Идентичность из ответа 2]."""

# =================================================================================================
# 3. HTML ТЕМПЛЕЙТ v2.0 (LIQUID GOLD & ORGANIC LOGO)
# =================================================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Identity Lab | Протокол дешифровки</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{ --obsidian: #050505; --gold: #D4AF37; --cyan: #00f3ff; }}
        body {{ background-color: var(--obsidian); color: #e5e5e5; font-family: 'Rajdhani', sans-serif; }}
        .shimmer-gold {{ background: linear-gradient(to right, #B4932C 20%, #F7E7CE 40%, #F7E7CE 60%, #B4932C 80%); background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent; animation: shine 4s linear infinite; }}
        @keyframes shine {{ to {{ background-position: 200% center; }} }}
        .cyber-card {{ background: rgba(18, 18, 18, 0.95); border: 1px solid #333; border-left: 4px solid var(--gold); backdrop-filter: blur(10px); }}
        .orbit {{ transform-origin: center; animation: rotate-orbit 25s linear infinite; }}
        @keyframes rotate-orbit {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
        .energy-flow {{ stroke-dasharray: 100; stroke-dashoffset: 100; animation: energy-run 3s cubic-bezier(0.4, 0, 0.2, 1) infinite; }}
        @keyframes energy-run {{ 0% {{ stroke-dashoffset: 100; opacity: 0; }} 50% {{ opacity: 1; }} 100% {{ stroke-dashoffset: -100; opacity: 0; }} }}
        .btn-gold {{ background: linear-gradient(135deg, #b4932c 0%, #D4AF37 100%); color: #000; font-weight: 800; text-transform: uppercase; padding: 1.2rem 2.5rem; border-radius: 0.5rem; transition: 0.4s; display: inline-block; }}
    </style>
</head>
<body class="selection:bg-yellow-900 selection:text-white">
    <header class="w-full py-12 px-4 text-center border-b border-gray-900 bg-black">
        <div class="max-w-4xl mx-auto flex flex-col items-center">
            <div class="w-32 h-32 border border-gray-800 rounded-full flex items-center justify-center bg-black/80 mb-8 overflow-hidden">
                <svg viewBox="0 0 100 100" class="w-24 h-24 fill-none">
                    <circle cx="50" cy="50" r="46" stroke="#D4AF37" stroke-width="2.5" opacity="1" />
                    <circle cx="50" cy="50" r="36" stroke="#D4AF37" stroke-width="1.2" opacity="0.6" class="orbit" />
                    <path class="energy-flow" d="M50 15 C70 15, 85 30, 85 50 C85 70, 70 85, 50 85 C30 85, 15 70, 15 50" stroke="#D4AF37" stroke-width="1.5" stroke-linecap="round" />
                    <path class="energy-flow" d="M25 50 C25 35, 35 25, 50 25 C65 25, 75 35, 75 50" stroke="#00f3ff" stroke-width="1" stroke-linecap="round" style="animation-delay: 1.5s;" />
                    <circle cx="50" cy="50" r="4" fill="#D4AF37" class="animate-pulse" />
                </svg>
            </div>
            <p class="text-[10px] text-cyan-400 tracking-[0.5em] uppercase mb-4 font-mono font-bold">Neuro-Architecture System v2.0</p>
            <h1 class="text-5xl md:text-7xl font-bold uppercase tracking-tighter shimmer-gold">ЛАБОРАТОРИЯ ИДЕНТИЧНОСТИ</h1>
            <p class="text-xl text-gray-400 mt-6 uppercase tracking-widest">Протокол дешифровки автопилота: <span class="text-white font-bold">{user_name}</span></p>
        </div>
    </header>

    <main class="container mx-auto px-4 py-16 max-w-5xl space-y-16">
        <section class="grid grid-cols-1 md:grid-cols-12 gap-8 items-center">
            <div class="md:col-span-5 flex justify-center">
                <div class="cyber-card p-10 rounded-full w-64 h-64 relative flex items-center justify-center">
                    <canvas id="statusChart"></canvas>
                    <div class="absolute inset-0 flex items-center justify-center flex-col">
                        <span class="text-4xl font-bold text-white">{idx}%</span>
                        <span class="text-[10px] text-gray-500 uppercase tracking-widest">Инерция</span>
                    </div>
                </div>
            </div>
            <div class="md:col-span-7">
                <h2 class="text-4xl font-bold text-white mb-4 uppercase">Индекс Автоматизма</h2>
                <p class="text-lg text-gray-400 leading-relaxed">
                    Ваша система работает в режиме <span class="text-gold font-bold italic">Биологического Алиби</span> (защитного механизма мозга). 
                    Энергия утилизируется на поддержание гомеостаза (сохранения текущего состояния) и подавление импульсов к развитию.
                </p>
            </div>
        </section>

        <section class="cyber-card p-10 rounded-2xl">
            <h2 class="text-2xl font-bold text-white mb-8 border-b border-gray-800 pb-4 uppercase tracking-widest">
                <span class="text-gold mr-4">⚡️</span> НЕЙРО-СИНТЕЗ ДАННЫХ
            </h2>
            <div class="font-mono text-gray-300 text-lg leading-loose whitespace-pre-wrap">{report_text}</div>
        </section>

        <section class="text-center py-16 border-t border-gray-900">
            <h3 class="text-3xl font-bold text-white mb-6 uppercase">ОКНО ПЛАСТИЧНОСТИ ОТКРЫТО</h3>
            <p class="text-gray-400 mb-10 max-w-2xl mx-auto">
                У вас есть ровно <span class="text-gold font-bold">4 часа</span> (окно пластичности — время готовности мозга к перезаписи), чтобы закрепить Сдвиг (переход из Пассажира в Автора) через действие.
            </p>
            <div class="flex flex-col md:flex-row gap-8 justify-center">
                <a href="{practicum_link}" class="btn-gold">🚀 ЗАПУСТИТЬ ПРАКТИКУМ</a>
                <a href="{protocol_link}" class="border border-gray-700 text-gray-300 py-4 px-10 rounded font-bold uppercase text-sm hover:bg-gray-800 transition">📥 Скачать Протокол (PDF)</a>
            </div>
        </section>
    </main>

    <footer class="text-center py-16 border-t border-gray-900 bg-black/40">
        <p class="text-[11px] text-gray-600 font-mono tracking-[0.3em] uppercase px-4">
            © 2026 ЛАБОРАТОРИЯ ИДЕНТИЧНОСТИ | ПРОЕКТ МЕТАФОРМУЛА ЖИЗНИ | АВТОР АЛЕКСАНДР ЛАЗАРЕНКО
        </p>
    </footer>

    <script>
        const ctx = document.getElementById('statusChart').getContext('2d');
        new Chart(ctx, {{
            type: 'doughnut',
            data: {{
                labels: ['Инерция', 'Свобода'],
                datasets: [{{
                    data: [{idx}, {inv_idx}],
                    backgroundColor: ['#1a1a1a', '#D4AF37'],
                    borderColor: '#050505',
                    borderWidth: 2,
                    cutout: '88%'
                }}]
            }},
            options: {{ plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }} }}
        }});
    </script>
</body>
</html>
"""

# =================================================================================================
# 4. ЛОГИКА ОБРАБОТКИ
# =================================================================================================

async def get_ai_report(answers):
    """ГИБРИДНЫЙ ИНТЕЛЛЕКТ: Gemini -> Cerebras"""
    data_str = "ДАННЫЕ АУДИТА:\n" + "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    
    if GEMINI_KEY:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
            resp = await asyncio.to_thread(model.generate_content, data_str)
            return resp.text.replace('**', '').strip()
        except Exception as e:
            logger.warning(f"Gemini error: {e}")

    if ai_backup:
        try:
            resp = await ai_backup.chat.completions.create(
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data_str}],
                model="llama-3.3-70b", temperature=0.4
            )
            return resp.choices[0].message.content.replace('**', '').strip()
        except Exception as e:
            logger.error(f"Backup AI error: {e}")
            
    return "Синхронизация ограничена. Но код Автора активен: Я ПРИЗНАЮ свою силу."

async def check_sub(user_id):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ["member", "administrator", "creator"]
    except: return False

def get_main_keyboard():
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🚀 Запустить Аудит", callback_data="run"))
    b.row(types.InlineKeyboardButton(text="⚡️ Практикум", url=PRACTICUM_URL))
    b.row(types.InlineKeyboardButton(text="💬 ПОДДЕРЖКА", url=SUPPORT_LINK))
    return b.as_markup()

# =================================================================================================
# 5. ХЕНДЛЕРЫ ТЕЛЕГРАМ
# =================================================================================================

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    is_sub = await check_sub(message.from_user.id)
    if not is_sub:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check"))
        await message.answer_photo(LOGO_URL, caption="Для старта дешифровки автопилота подпишись на наш канал:", reply_markup=kb.as_markup())
    else:
        await message.answer_photo(LOGO_NAVIGATOR_URL, caption="Система синхронизирована. Готов занять место Автора?", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "check")
async def check_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ открыт!"); await start(cb.message, state)
    else: await cb.answer("Подписка не найдена!", show_alert=True)

@dp.callback_query(F.data == "run")
async def run_audit(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(step=0, answers=[])
    await cb.message.answer("Инициализация протокола. Будь предельно искренен. Начинаем глубокий аудит.")
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0])
    await state.set_state(AuditState.answering)

@dp.message(AuditState.answering)
async def process(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"): return
    data = await state.get_data()
    step, answers = data.get('step', 0), data.get('answers', [])
    answers.append(message.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step+1, answers=answers)
        await message.answer(QUESTIONS[step+1])
    else:
        status = await message.answer("🧠 Дешифровка Коннектома... 100%")
        report = await get_ai_report(answers)
        idx = 72 + (len(" ".join(answers)) % 21) # Эмуляция расчета
        
        diag_data = {"name": message.from_user.full_name, "report": report, "index": idx, "date": datetime.now().strftime("%d.%m.%Y")}
        if db:
            db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(str(message.from_user.id)).set(diag_data)
            
        await status.edit_text(f"[ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ]\n\n{report}")
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📊 ОТКРЫТЬ ВЕБ-ОТЧЕТ", url=f"{RENDER_URL}/report/{message.from_user.id}"))
        await message.answer("Аудит завершен. Твой отчет готов:", reply_markup=kb.as_markup())
        
        # Лог админу
        try:
            await bot.send_message(ADMIN_ID, f"👤 {message.from_user.full_name} завершил аудит. Индекс: {idx}%")
        except: pass
        await state.clear()

# =================================================================================================
# 6. ВЕБ-ИНТЕРФЕЙС
# =================================================================================================

async def handle_report(request):
    uid = request.match_info['user_id']
    if db:
        doc = db.collection("artifacts").document(app_id).collection("public").document("data").collection("users").document(uid).get()
        if doc.exists:
            d = doc.to_dict()
            html = HTML_TEMPLATE.format(
                user_name=d['name'], idx=d['index'], inv_idx=100-d['index'],
                report_text=d['report'].replace('\n', '<br>'),
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
    return web.Response(text="<h1>Отчет не найден</h1>", content_type='text/html', status=404)

async def on_startup(bot: Bot):
    if RENDER_URL: await bot.set_webhook(url=WEBHOOK_URL)
    await bot.send_message(ADMIN_ID, "🚀 Identity Lab v11.16 ONLINE")

def main():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot Active"))
    app.router.add_get('/report/{user_id}', handle_report)
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    main()



