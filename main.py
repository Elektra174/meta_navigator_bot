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

client = Cerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class AuditState(StatesGroup):
    answering_questions = State()

# Мягкие формулировки в стиле МПТ 
QUESTIONS = [
    "1. Если бы вы на мгновение представили, что являетесь на 100% Автором своей реальности, что бы вы изменили первым делом? (Или пока кажется, что жизнь просто «случается» с вами?)",
    "2. Могли бы вы описать то состояние повторения, которое иногда называют «днем сурка»? Какие мысли крутятся в голове в те моменты, когда вы не заняты делом? (Это ваш «режим заставки» мозга).",
    "3. Какая ситуация сейчас больше всего «вытягивает» из вас силы? Если бы эта проблема была физическим объектом, на что бы она была похожа?",
    "4. Когда вы думаете об этом объекте, что вы замечаете в теле? Это может быть сжатие, холод, тяжесть или какое-то иное ощущение?",
    "5. Какое качество в других людях вас раздражает больше всего? Попробуйте увидеть: какую силу или свободу проявляет этот человек, которую вы сейчас себе запрещаете?",
    "6. Как вам кажется, сколько еще времени вы готовы нарезать круги по этому старому маршруту, пока ваш внутренний ресурс не иссякнет?",
    "7. Готовы ли вы прямо сейчас попробовать перехватить управление у «Автопилота» и проложить свой собственный маршрут?"
]

SYSTEM_PROMPT = """
Ты — «Мета-Навигатор», интеллектуальный ИИ-агент Александра Лазаренко. Ты Проводник. 
ТВОЯ ЗАДАЧА: Проанализировать ответы и выдать глубокий психологический отчет.

ПРИНЦИПЫ СТИЛЯ:
1. Используй только Markdown для форматирования. Никаких двойных звездочек (** **) в тексте ответа. Используй жирный шрифт только для заголовков через # или ##.
2. Тон: Бережный, мудрый, экспертный. Без «воды».
3. Разъяснение терминов: Если используешь понятия 'Застойная доминанта' или 'Режим заставки', кратко поясни их. 
   - Застойная доминанта: как магнит в мозгу, который стягивает на себя всё внимание.
   - Режим заставки (ДСМ): когда мозг работает вхолостую, пережевывая старые мысли.
4. МПТ: Всегда возвращай авторство. Подсвети, как человек сам блокирует свою энергию.

СТРУКТУРА ОТЧЕТА:
# Результаты Аудита
## Индекс Автопилота: [Значение]%
## Анализ системы: [Описание сбоя и застойной доминанты]
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
    sub = await is_subscribed(message.from_user.id)
    if not sub:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="Присоединиться к проекту", url="https://t.me/metaformula_life"))
        builder.row(types.InlineKeyboardButton(text="Я в канале! Начать аудит", callback_data="check_sub"))
        
        await message.answer(
            "Добро пожаловать в Метаформулу Жизни.\n\n"
            "Я — ваш Мета-Навигатор. Помогу увидеть программы вашего Автопилота и проложить путь к себе настоящему.\n\n"
            "Чтобы мы начали сверку координат, пожалуйста, подпишитесь на наш канал:",
            reply_markup=builder.as_markup()
        )
    else:
        await start_audit(message, state)

@dp.callback_query(F.data == "check_sub")
async def check_btn(callback: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(callback.from_user.id):
        await callback.message.answer("Доступ подтвержден. Мы начинаем путь.")
        await start_audit(callback.message, state)
    else:
        await callback.answer("Вы еще не в канале проекта!", show_alert=True)

async def start_audit(message: types.Message, state: FSMContext):
    await state.update_data(current_q=0, answers=)
    await message.answer(
        "Я задам 7 вопросов. Они помогут нам протереть линзы вашего внутреннего навигатора.\n"
        "Отвечайте из глубины, доверяя первым пришедшим образам."
    )
    await asyncio.sleep(1)
    await message.answer(QUESTIONS)
    await state.set_state(AuditState.answering_questions)

@dp.message(AuditState.answering_questions)
async def handle_questions(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_idx, answers = data['current_q'], data['answers']
    answers.append(f"Q{q_idx+1}: {message.text}")
    new_idx = q_idx + 1
    
    if new_idx < len(QUESTIONS):
        await state.update_data(current_q=new_idx, answers=answers)
        await message.answer(QUESTIONS[new_idx])
    else:
        await message.answer("Все данные получены. Навигатор вычисляет вашу Метаформулу... 🌀")
        report = await generate_ai_report(answers)
        await message.answer(report)
        await message.answer("Ваш Авторский Маршрут начинается прямо здесь, в этой точке осознания. Будьте на связи в канале!")
        await state.clear()

async def generate_ai_report(answers):
    try:
        response = client.chat.completions.create(
            messages=,
            model="llama-3.3-70b",
            temperature=0.5,
            top_p=0.9
        )
        return response.choices.message.content
    except Exception as e: return f"Система временно недоступна: {e}"

# Health check для Render
async def handle_health(request): return web.Response(text="Navigator is active")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
