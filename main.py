import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cerebras.cloud.sdk import Cerebras
from aiohttp import web

# --- НАСТРОЙКИ ---
TOKEN = "8576599798:AAGzDKKbuyd46h9qZ_U57JC4R_nRbQodv2M"
CEREBRAS_API_KEY = "csk-fmk4e6tm5e2vpkxcec3fn498jnk9nhf849hehjrpnd2jvwrn"
CHANNEL_ID = "@metaformula_life"

# Инициализация ИИ и бота
client = Cerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ЛОГИКА СОСТОЯНИЙ (FSM) ---
class AuditState(StatesGroup):
    answering_questions = State()

QUESTIONS = [
    "1. Если бы ты был на 100% автором своей жизни, что бы ты изменил прямо сейчас? (Или ты пока просто наблюдатель?)",
    "2. Опиши свой 'день сурка' тремя словами. Какие мысли крутятся в голове фоном, когда ты не занят делом? (Твой режим заставки)",
    "3. Какая ситуация высасывает энергию больше всего? На какой физический объект она похожа?",
    "4. Где в теле ты чувствуешь зажим или холод, когда думаешь об этом? (Или ты 'только в голове'?)",
    "5. Какое качество в людях тебя бесит или раздражает? Какая свобода в нем спрятана?",
    "6. Сколько еще лет ты готов нарезать круги в этой петле, прежде чем твой внутренний двигатель перегорит?",
    "7. Ты готов забрать управление у автопилота или тебе привычнее роль пассажира в чужом кино?"
]

SYSTEM_PROMPT = """
Ты — «Мета-Навигатор», ИИ-агент Александра Лазаренко. Ты Проводник. 
ТВОЯ ЗАДАЧА: Проанализировать ответы пользователя и выдать «Аудит Автопилота».

ПРИНЦИПЫ:
1. МПТ: Возвращай авторство. Если человек ноет, подсвечивай, как он сам создает этот тупик. 
2. Нейрофизиология: Используй понятия 'застойная доминанта' и 'режим заставки'. 
3. Тон: Простой, честный, глубокий. Говори на языке 'прошивок', 'сбоев' и 'маршрутов'. Никакой эзотерики.

СТРУКТУРА ТВОЕГО ОТВЕТА (ОТЧЕТА):
- Индекс автопилота (в %).
- Главный 'сбой' системы (суть застревания).
- Твоя Метаформула решения (короткая фраза-код для переключения состояния).
- Напутствие Проводника.
"""

# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    sub = await is_subscribed(message.from_user.id)
    if not sub:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="Подписаться на канал", url="https://t.me/metaformula_life"))
        builder.row(types.InlineKeyboardButton(text="Я подписался!", callback_data="check_sub"))
        await message.answer("Привет! Я — Мета-Навигатор. Прежде чем мы начнем поиск сбоев в твоем автопилоте, подпишись на канал проекта:", reply_markup=builder.as_markup())
    else:
        await start_audit(message, state)

@dp.callback_query(F.data == "check_sub")
async def check_btn(callback: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(callback.from_user.id):
        await callback.message.answer("Доступ открыт. Начинаем аудит.")
        await start_audit(callback.message, state)
    else:
        await callback.answer("Подписка не найдена! Вступи в канал.", show_alert=True)

async def start_audit(message: types.Message, state: FSMContext):
    # ИСПРАВЛЕНО: answers= теперь инициализируется корректно
    await state.update_data(current_q=0, answers=[])
    await message.answer("Я задам 7 вопросов, чтобы увидеть твой автопилот. Отвечай честно, из глубины.")
    await asyncio.sleep(1)
    await message.answer(QUESTIONS[0])
    await state.set_state(AuditState.answering_questions)

@dp.message(AuditState.answering_questions)
async def handle_questions(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_idx = data.get('current_q', 0)
    answers = data.get('answers', [])
    
    answers.append(f"Вопрос {q_idx+1}: {message.text}")
    new_idx = q_idx + 1
    
    if new_idx < len(QUESTIONS):
        await state.update_data(current_q=new_idx, answers=answers)
        await message.answer(QUESTIONS[new_idx])
    else:
        await message.answer("Данные получены. Навигатор вычисляет твою Метаформулу... 🌀")
        report = await generate_ai_report(answers)
        await message.answer(report)
        await message.answer("Твой Авторский Маршрут начинается здесь. Будь на связи в канале!")
        await state.clear()

async def generate_ai_report(answers):
    user_input = "\n".join(answers)
    try:
        # ИСПРАВЛЕНО: messages сформирован правильно
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            model="llama-3.3-70b",
            temperature=0.4,
            top_p=0.9,
            max_completion_tokens=2048
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Сбой в системе Навигатора: {e}. Попробуй позже."

# --- DUMMY SERVER ДЛЯ RENDER ---
async def handle(request):
    return web.Response(text="Бот работает")

async def run_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    asyncio.create_task(run_server()) # Запуск сервера в фоне
    print("Мета-Навигатор запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
