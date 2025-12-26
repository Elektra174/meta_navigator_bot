import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cerebras.cloud.sdk import Cerebras
from aiohttp import web

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8576599798:AAGzDKKbuyd46h9qZ_U57JC4R_nRbQodv2M"
CEREBRAS_API_KEY = "csk-fmk4e6tm5e2vpkxcec3fn498jnk9nhf849hehjrpnd2jvwrn"
CHANNEL_ID = "@metaformula_life"
# Прямая ссылка на ваш логотип для Telegram
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png.png"

client = Cerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class AuditState(StatesGroup):
    answering_questions = State()

QUESTIONS = [
    "1. Если бы вы на мгновение представили, что являетесь на 100% Автором своей реальности, что бы вы изменили первым делом? (Или пока кажется, что жизнь просто «случается» с вами?)",
    "2. Могли бы вы описать то состояние повторения, которое иногда называют «днем сурка»? Какие мысли крутятся в голове в те моменты, когда вы не заняты делом? (Это ваш «режим заставки» мозга).",
    "3. Какая ситуация сейчас больше всего «вытягивает» из вас силы? Если бы эта проблема была физическим объектом, на что бы она была похожа?",
    "4. Когда вы думаете об этом объекте, что вы замечаете в теле? Это может быть сжатие, холод, тяжесть или иное ощущение?",
    "5. Какое качество в других людях вас раздражает больше всего? Попробуйте увидеть: какую силу или свободу проявляет этот человек, которую вы сейчас себе запрещаете?",
    "6. Как вам кажется, сколько еще времени вы готовы нарезать круги по этой «петле» старого маршрута, пока ваш внутренний ресурс не иссякнет?",
    "7. Готовы ли вы прямо сейчас попробовать перехватить управление у «Автопилота» и проложить свой собственный маршрут?"
]

SYSTEM_PROMPT = """
Ты — «Мета-Навигатор», интеллектуальный ИИ-агент Александра Лазаренко. Ты Проводник. 
ТВОЯ ЗАДАЧА: Проанализировать ответы пользователя и выдать глубокий психологический аудит.

ПРИНЦИПЫ:
1. Используй только Markdown. Никаких двойных звездочек (** **) в тексте. Используй # и ## для заголовков.
2. Тон: Мудрый, бережный. Если используешь термины 'Застойная доминанта' или 'Режим заставки', кратко поясни их (как заевшую пластинку или холостой ход мозга).
3. МПТ: Возвращай авторство. Подсвети, как человек сам блокирует свою энергию.

СТРУКТУРА ОТВЕТА:
# Результаты Аудита
## Индекс Автопилота: [Значение]%
## Анализ системы: [Описание сбоя]
## Метаформула решения: [Короткая фраза-код]
## Слово Проводника: [Напутствие]
"""

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_subscribed(message.from_user.id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="Присоединиться к проекту", url="https://t.me/metaformula_life"))
        builder.row(types.InlineKeyboardButton(text="Я в канале! Начать путь", callback_data="check_sub"))
        await message.answer("Добро пожаловать в Метаформулу Жизни.\n\nЯ — ваш Мета-Навигатор. Помогу увидеть программы вашего Автопилота и проложить путь к себе настоящему.\n\nЧтобы начать, пожалуйста, подпишитесь на наш канал:", reply_markup=builder.as_markup())
    else:
        await start_audit(message, state)

@dp.callback_query(F.data == "check_sub")
async def check_btn(callback: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(callback.from_user.id):
        await callback.message.answer("Доступ подтвержден.")
        await start_audit(callback.message, state)
    else:
        await callback.answer("Вы еще не подписаны!", show_alert=True)

async def start_audit(message: types.Message, state: FSMContext):
    await state.update_data(current_q=0, answers=)
    # Отправляем фото-обложку
    try:
        await message.answer_photo(
            photo=LOGO_URL,
            caption="Ваш Авторский Маршрут начинается здесь.\n\nЯ задам 7 вопросов, чтобы протереть линзы вашего внутреннего навигатора. Отвечайте из глубины, доверяя первым пришедшим образам."
        )
    except:
        await message.answer("Ваш Авторский Маршрут начинается здесь.\n\nЯ задам 7 вопросов...")
    
    await asyncio.sleep(1)
    await message.answer(QUESTIONS)
    await state.set_state(AuditState.answering_questions)

@dp.message(AuditState.answering_questions)
async def handle_questions(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_idx, answers = data.get('current_q', 0), data.get('answers',)
    answers.append(f"Q{q_idx+1}: {message.text}")
    new_idx = q_idx + 1
    
    if new_idx < len(QUESTIONS):
        await state.update_data(current_q=new_idx, answers=answers)
        await message.answer(QUESTIONS[new_idx])
    else:
        await message.answer("Данные получены. Навигатор вычисляет вашу Метаформулу... 🌀")
        report = await generate_ai_report(answers)
        await message.answer(report)
        await message.answer("Ваша Метаформула активирована. Будьте на связи в канале!")
        await state.clear()

async def generate_ai_report(answers):
    user_input = "\n".join(answers)
    try:
        response = client.chat.completions.create(
            messages=,
            model="llama-3.3-70b",
            temperature=0.5,
            top_p=0.9
        )
        return response.choices.message.content
    except Exception as e: return f"Система временно недоступна: {e}"

async def handle_health(request): return web.Response(text="active")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
