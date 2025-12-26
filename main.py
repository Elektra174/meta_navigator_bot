import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cerebras.cloud.sdk import Cerebras
from aiohttp import web

# --- ЧТЕНИЕ ПЕРЕМЕННЫХ ИЗ RENDER ---
# В Render вы создали ключи AI_API_KEY и BOT_TOKEN. Код берет их оттуда автоматически.
TOKEN = os.getenv("BOT_TOKEN")
CEREBRAS_API_KEY = os.getenv("AI_API_KEY")
CHANNEL_ID = "@metaformula_life"

# Инициализация
client = Cerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class AuditState(StatesGroup):
    answering_questions = State()

QUESTIONS = [
    "1. Если бы ты был на 100% автором своей жизни, что бы ты изменил прямо сейчас? (Или ты пока просто наблюдатель?)",
    "2. Опиши свой 'день сурка' тремя словами. Какие мысли крутятся в голове фоном, когда ты ничем не занят? (Твой режим заставки)",
    "3. Какая ситуация высасывает энергию больше всего? На какой физический объект она похожа?",
    "4. Где в теле ты чувствуешь зажим или холод, когда думаешь об этом? (Или ты 'только в голове'?)",
    "5. Какое качество в людях тебя бесит или раздражает? Какая свобода в нем спрятана?",
    "6. Сколько еще лет ты готов нарезать круги в этой петле, прежде чем твой внутренний двигатель перегорит?",
    "7. Ты готов забрать управление у автопилота или тебе привычнее роль пассажира в чужом кино?"
]

SYSTEM_PROMPT = "Ты — Мета-Навигатор Александра Лазаренко. Твоя задача — проанализировать 7 ответов и выдать глубокий психологический аудит автопилота пользователя, используя принципы МПТ и нейрофизиологии."

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_subscribed(message.from_user.id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="Подписаться на канал", url="https://t.me/metaformula_life"))
        builder.row(types.InlineKeyboardButton(text="Я подписался!", callback_data="check_sub"))
        await message.answer("Привет! Я — Мета-Навигатор. Подпишись на канал проекта, чтобы начать аудит:", reply_markup=builder.as_markup())
    else:
        await start_audit(message, state)

@dp.callback_query(F.data == "check_sub")
async def check_btn(callback: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(callback.from_user.id):
        await callback.message.answer("Доступ открыт. Начинаем аудит.")
        await start_audit(callback.message, state)
    else:
        await callback.answer("Подписка не найдена!", show_alert=True)

async def start_audit(message: types.Message, state: FSMContext):
    # ИСПРАВЛЕНО: Теперь пустой список инициализируется корректно
    await state.update_data(current_q=0, answers=) 
    await message.answer("Я задам 7 вопросов. Отвечай честно.\n\n" + QUESTIONS)
    await state.set_state(AuditState.answering_questions)

@dp.message(AuditState.answering_questions)
async def handle_questions(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_idx = data.get('current_q', 0)
    answers = data.get('answers',)
    
    answers.append(f"Q{q_idx+1}: {message.text}")
    new_idx = q_idx + 1
    
    if new_idx < len(QUESTIONS):
        await state.update_data(current_q=new_idx, answers=answers)
        await message.answer(QUESTIONS[new_idx])
    else:
        await message.answer("Вычисляю твою Метаформулу... 🌀")
        report = await generate_ai_report(answers)
        await message.answer(report)
        await state.clear()

async def generate_ai_report(answers):
    try:
        response = client.chat.completions.create(
            messages=,
            model="llama-3.3-70b",
            temperature=0.4
        )
        return response.choices.message.content
    except Exception as e:
        return f"Ошибка ИИ: {e}"

# Сервер для Render (чтобы не засыпал и порт работал)
async def handle(request):
    return web.Response(text="Bot is alive")

async def run_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    asyncio.create_task(run_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
