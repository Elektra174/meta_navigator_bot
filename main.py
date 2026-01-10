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
from aiohttp import web, ClientSession

# --- СИСТЕМНЫЕ НАСТРОЙКИ ---
if sys.platform != 'win32':
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

try:
    from cerebras.cloud.sdk import AsyncCerebras
    CEREBRAS_AVAILABLE = True
except ImportError:
    CEREBRAS_AVAILABLE = False

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
AI_KEY = os.getenv("AI_API_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
PORT = int(os.getenv("PORT", 10000))

WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013

# Ресурсы
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png"
LOGO_NAVIGATOR_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo11.png"
PROTOCOL_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/Autopilot_System_Protocol.pdf"
PRACTICUM_URL = "https://www.youtube.com/@МетаформулаЖизни"
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

# Хранилище данных (в памяти - временно, для демонстрации)
# В продакшене лучше использовать базу данных (Firestore/Redis/Postgres)
diagnostic_data = {} 

class AuditState(StatesGroup):
    answering = State()

# --- ВОПРОСЫ (v5.0) ---
QUESTIONS = [
    "📍 **Точка 1: Локация.**\nВ какой сфере жизни или в каком деле ты сейчас чувствуешь пробуксовку? Опиши ситуацию, где твои усилия не дают результата.",
    "📍 **Точка 2: Мета-Маяк.**\nПредставь, что задача решена на 100%. Опиши свое состояние: какой ты теперь? (Например: спокойный, мощный, свободный). Как ты себя чувствуешь?",
    "📍 **Точка 3: Мысли.**\nКакая «мыслительная жвачка» крутится у тебя в голове, когда ты думаешь о переменах? Какие сомнения ты себе говоришь?",
    "📍 **Точка 4: Образ.**\nПредставь перед собой пустую сцену и вынеси на неё то, что тебе мешает. Если бы это было образом или предметом, на что бы это было похоже? (Стена, туман, камень?)",
    "📍 **Точка 5: Ощущение.**\nПосмотри на этот образ на сцене. Где и какое ощущение возникает в теле? Опиши физику: сжатие, холод, напряжение? Что ты делаешь мышцами?",
    "📍 **Точка 6: Смысл реакции.**\nТело всегда действует логично. Как ты думаешь, от чего тебя пытается защитить эта телесная реакция? (От риска, от лишних трат, от ошибки?)",
    "📍 **Точка 7: Скрытая сила.**\nКакое качество в других людях тебя раздражает сильнее всего? (Например: наглость, навязчивость, грубость). Если представить, что за этим стоит сила — что это за сила и как бы ты мог использовать её себе на пользу?",
    "📍 **Точка 8: Готовность.**\nТы готов признать себя Автором того, что происходит в твоем теле и жизни, и перенастроить свой автопилот прямо сейчас?"
]

SYSTEM_PROMPT = """ТЫ — СТАРШИЙ АРХИТЕКТОР ИДЕНТИЧНОСТИ IDENTITY LAB.
ЗАДАЧА: Провести соматическую дешифровку автопилота.
ОБЩЕНИЕ: На "ты", директивно, но с уважением.

ЛОГИКА ОТЧЕТА:
1. СИНТЕЗ РОЛИ: В пункте "МЕТА-МАЯК" создай Целостный Образ (Роль) на основе прилагательных из ответа 2.
2. АВТОРСТВО: Объясни, что пользователь САМ создает сигнал [ответ 5] ради [ответ 6].
3. РЕИНТЕГРАЦИЯ: Сила из [ответ 7] заперта в [ответ 5]. Мы её присваиваем.
4. СДВИГ: Опиши процесс мягко: сила из образа возвращается в тело, образ на сцене растворяется за ненадобностью.

СТРУКТУРА ОТЧЕТА (СТРОГО):
⬛️ [ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ: ДИАГНОСТИКА АВТОПИЛОТА] 📀

Статус: Обнаружено ограничение тока энергии. Режим гомеостаза активен.

📊 ИНДЕКС АВТОМАТИЗМА (Инерция связей): [X]%

🧠 ДИАГНОСТИКА КОНТУРОВ:

1. УЗЕЛ СОПРОТИВЛЕНИЯ: Образ "[ответ 4]" вызывает сигнал "[ответ 5]". Это твое активное действие по блокировке импульса.
2. ХОЛОСТОЙ ХОД (ДСМ): Мысли "[ответ 3]" — это Биологическое Алиби. Мозг тратит энергию на защиту от [ответ 6].
3. РЕАКТОР ИДЕНТИЧНОСТИ: Раздражение на "[качество из ответа 7]" скрывает силу: "[сила из ответа 7]". Сейчас она заперта в теле.
4. МЕТА-МАЯК (Эталонная Идентичность): Твоя новая роль — [СИНТЕЗИРОВАННАЯ РОЛЬ]. В этом состоянии ты [описание из ответа 2].

🛠 МИНИ-ПРАКТИКУМ: РЕИНТЕГРАЦИЯ СИЛЫ
1. Детекция: Посмотри на образ "[ответ 4]". Заметь [ответ 5].
2. Авторство: Скажи: «Я сам создаю это напряжение. Это МОЯ энергия».
3. Реинтеграция: Представь, как сила из образа возвращается и присваивается телом. Образ растворяется.
4. Сдвиг: Почувствуй себя [СИНТЕЗИРОВАННАЯ РОЛЬ].

⚡️ КОД ПЕРЕПРОШИВКИ (МЕТАФОРМУЛА):
> «Я Автор. Я ПРИЗНАЮ, что сам создаю этот сигнал [ответ 5] — это мой ресурс. Я НАПРАВЛЯЮ его на активацию [СИНТЕЗИРОВАННАЯ РОЛЬ]».

(Произнеси это вслух).

[🎯 ДАЛЬНЕЙШАЯ ДИРЕКТИВА]:
Скачай Гайд и переходи к Практикуму для закрепления (окно 4 часа).
"""

# --- WEB TEMPLATE ---
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
        :root {{ --bg: #050505; --gold: #D4AF37; --cyan: #00f3ff; --text: #e5e5e5; }}
        body {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; }}
        .mono {{ font-family: 'Roboto Mono', monospace; }}
        .cyber-card {{ background: rgba(20,20,20,0.95); border: 1px solid #333; border-left: 4px solid var(--gold); padding: 24px; border-radius: 8px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
        .btn-gold {{ background: linear-gradient(to right, #b4932c, #D4AF37); color: #000; font-weight: bold; padding: 14px 28px; border-radius: 6px; text-transform: uppercase; transition: all 0.3s; display: inline-block; }}
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
                </p>
            </div>
        </div>

        <!-- Report Text -->
        <div class="cyber-card">
            <h2 class="text-xl font-bold text-white mb-4 border-b border-gray-800 pb-2 flex items-center">
                <span class="text-gold mr-2">⚡️</span> НЕЙРО-СИНТЕЗ ДАННЫХ
            </h2>
            <div class="mono whitespace-pre-wrap text-gray-300 text-sm leading-relaxed">
{report_text}
            </div>
        </div>

        <!-- CTA -->
        <div class="text-center py-8 space-y-6">
            <p class="text-gray-400 text-sm">Окно нейропластичности открыто (4 часа).<br>Закрепите результат действием.</p>
            <div class="flex flex-col md:flex-row gap-4 justify-center">
                <a href="{practicum_link}" class="btn-gold">🚀 ЗАПУСТИТЬ ПРАКТИКУМ</a>
                <a href="{protocol_link}" class="border border-gray-700 text-gray-400 hover:text-white py-3 px-8 rounded uppercase font-bold transition hover:bg-gray-800 flex items-center justify-center text-sm">
                    📥 Скачать Гайд
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

# --- HELPERS ---
def calculate_index(answers):
    text = " ".join(answers).lower()
    markers = ['не знаю', 'боюсь', 'страх', 'лень', 'тупик', 'тяжело', 'сжатие', 'ком', 'холод', 'тревога']
    count = sum(1 for m in markers if m in text)
    return min(95, max(50, 65 + (count * 3)))

def get_fallback_report(answers):
    idx = calculate_index(answers)
    safe = answers + ["..."] * (8 - len(answers))
    return f"""⬛️ [ТЕХНИЧЕСКОЕ ЗАКЛЮЧЕНИЕ] 📀

Статус: Обнаружено ограничение тока энергии.

📊 ИНДЕКС АВТОМАТИЗМА: {idx}%

🧠 ДИАГНОСТИКА:
1. УЗЕЛ СОПРОТИВЛЕНИЯ: Образ "{safe[3]}" вызывает сигнал "{safe[4]}".
2. ХОЛОСТОЙ ХОД: Мысли "{safe[2]}" — это Биологическое Алиби. Мозг защищает вас от "{safe[5]}".
3. РЕАКТОР ИДЕНТИЧНОСТИ: Сила скрыта за раздражением "{safe[6]}".
4. МЕТА-МАЯК: Твоя новая роль — {safe[1]}.

⚡️ МЕТАФОРМУЛА:
«Я Автор. Я ПРИЗНАЮ, что сам создаю этот сигнал [{safe[4]}] — это мой ресурс. Я НАПРАВЛЯЮ его на активацию [{safe[1]}]».
"""

async def get_ai_report(answers):
    if not ai_client: return get_fallback_report(answers)
    data = "\n".join([f"T{i+1}: {a}" for i, a in enumerate(answers)])
    try:
        resp = await ai_client.chat.completions.create(
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": data}],
            model="llama-3.3-70b", temperature=0.4, max_completion_tokens=2500
        )
        return resp.choices[0].message.content or get_fallback_report(answers)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return get_fallback_report(answers)

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

async def send_guide(message):
    try:
        await message.answer("📥 **Формирую ваш Технический Паспорт (Гайд)...**", parse_mode="Markdown")
        async with ClientSession() as s:
            async with s.get(PROTOCOL_URL) as r:
                if r.status == 200:
                    await message.answer_document(types.BufferedInputFile(await r.read(), filename="ПРОТОКОЛ_ДЕШИФРОВКИ.pdf"), caption="📘 Гайд готов. Изучи 'Ловушку Интеллекта'.")
                else: raise Exception()
    except: await message.answer(f"📥 Скачать Гайд: {PROTOCOL_URL}")

async def log_admin(user, report, answers):
    try: await bot.send_message(ADMIN_ID, f"🔔 **LOG v5.1**\n👤 {user.full_name}\n\n**Ответы:**\n" + "\n".join(answers) + f"\n\n{report[:2000]}")
    except: pass

def get_reply_kb():
    return ReplyKeyboardBuilder().button(text="≡ МЕНЮ").as_markup(resize_keyboard=True)

def kb_menu():
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🚀 Новый Аудит", callback_data="run"))
    kb.row(types.InlineKeyboardButton(text="📥 Скачать Гайд", callback_data="get_guide"))
    kb.row(types.InlineKeyboardButton(text="⚡️ Практикум", url=PRACTICUM_URL))
    kb.row(types.InlineKeyboardButton(text="💬 ПОДДЕРЖКА", url=SUPPORT_LINK))
    return kb.as_markup()

# --- HANDLERS ---
@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    is_sub = await check_sub(msg.from_user.id)
    # Показываем нижнюю клавиатуру сразу
    await msg.answer("Система загружается...", reply_markup=get_reply_kb())
    
    kb = InlineKeyboardBuilder()
    if not is_sub:
        kb.row(types.InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_LINK))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить", callback_data="check"))
        cap = "👋 **Лаборатория идентичности 'Метаформула жизни'**\n\nЯ — Мета-Навигатор. Я помогу тебе найти точки утечки энергии и перехватить управление у биологического автопилота.\n\nДля начала работы подпишись на наш канал:"
        await msg.answer_photo(LOGO_URL, caption=cap, reply_markup=kb.as_markup())
    else:
        kb.row(types.InlineKeyboardButton(text="🚀 НАЧАТЬ АУДИТ", callback_data="run"))
        cap = "🧠 **Коннектом синхронизирован.**\n\nСистема готова обнаружить скрытые стратегии. Готов занять место Автора?"
        await msg.answer_photo(LOGO_NAVIGATOR_URL, caption=cap, reply_markup=kb_menu())

@dp.message(F.text == "≡ МЕНЮ")
@dp.message(Command("menu"))
async def menu_handler(msg: types.Message):
    await msg.answer("📋 **Меню Identity Lab:**", reply_markup=kb_menu(), parse_mode="Markdown")

@dp.callback_query(F.data == "check")
async def check_cb(cb: types.CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        await cb.answer("Доступ открыт!")
        await start(cb.message, state)
    else: await cb.answer("❌ Нет подписки!", show_alert=True)

@dp.callback_query(F.data == "run")
async def run(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(step=0, answers=[])
    await cb.message.answer("🔬 **Инициализация протокола.**\nОтвечай честно. Твоё тело — самый точный прибор.")
    await asyncio.sleep(1)
    await cb.message.answer(QUESTIONS[0], parse_mode="Markdown")
    await state.set_state(AuditState.answering)

@dp.callback_query(F.data == "get_guide")
async def guide_cb(cb: types.CallbackQuery):
    if cb.from_user.id not in diagnostic_data:
        await cb.answer("🚫 Сначала пройдите Аудит!", show_alert=True)
        # Предлагаем пройти
        kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="🚀 Начать Аудит", callback_data="run"))
        await cb.message.answer("Гайд доступен только после диагностики.", reply_markup=kb.as_markup())
        return
    await cb.answer("Отправляю...")
    await send_guide(cb.message)

@dp.message(AuditState.answering)
async def ans(msg: types.Message, state: FSMContext):
    if not msg.text: return
    d = await state.get_data()
    step, ans = d['step'], d['answers']
    ans.append(msg.text.strip())
    
    if step + 1 < len(QUESTIONS):
        await state.update_data(step=step+1, answers=ans)
        await msg.answer(QUESTIONS[step+1], parse_mode="Markdown")
    else:
        await msg.answer("🧠 **Идет дешифровка Коннектома...**")
        rep = await get_ai_report(ans)
        idx = calculate_index(ans)
        
        diagnostic_data[msg.from_user.id] = {
            "name": msg.from_user.full_name,
            "report": rep.replace('```', '').replace('**', ''),
            "idx": idx, "inv_idx": 100-idx, "date": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        await msg.answer(rep.replace('```', '').replace('**', '*'))
        await send_guide(msg)
        
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="⚡️ ПЕРЕЙТИ К ПРАКТИКУМУ", url=PRACTICUM_URL))
        kb.row(types.InlineKeyboardButton(text="📊 ВЕБ-ОТЧЕТ", callback_data="web"))
        
        await asyncio.sleep(2)
        await msg.answer("🎯 **Аудит завершен.**\nЧтобы закрепить Сдвиг на уровне тела — переходи к видео-инсталляции:", reply_markup=kb.as_markup())
        await log_admin(msg.from_user, rep, ans)
        await state.clear()

@dp.callback_query(F.data == "web")
async def web_cb(cb: types.CallbackQuery):
    host = os.environ.get("RENDER_EXTERNAL_URL", f"https://{os.environ.get('RENDER_SERVICE_NAME', 'meta-navigator-bot')}.onrender.com")
    url = f"{host}/report/{cb.from_user.id}"
    await cb.message.answer(f"🔗 **Твоя карта дешифровки:**\n{url}", parse_mode="Markdown")
    await cb.answer()

# --- SERVER ---
async def h_home(r): return web.Response(text="Identity Lab v5.1 Active")
async def h_rep(r):
    try:
        uid = int(r.match_info['user_id'])
        if uid in diagnostic_data:
            d = diagnostic_data[uid]
            html = HTML_TEMPLATE.format(
                user_name=d['name'], user_id=d['id'], date=d['date'],
                report_text=d['report'], idx=d['idx'], inv_idx=d['inv_idx'],
                practicum_link=PRACTICUM_URL, protocol_link=PROTOCOL_URL
            )
            return web.Response(text=html, content_type='text/html')
        return web.Response(text="Отчет не найден.", status=404)
    except: return web.Response(text="Error", status=500)

async def on_startup(bot: Bot):
    if RENDER_URL:
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

def main():
    app = web.Application()
    app.router.add_get('/', h_home)
    app.router.add_get('/health', h_home)
    app.router.add_get('/report/{user_id}', h_rep)
    
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
