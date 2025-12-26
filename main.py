import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cerebras.cloud.sdk import Cerebras
from aiohttp import web

# --- ЧТЕНИЕ КЛЮЧЕЙ ИЗ ПЕРЕМЕННЫХ RENDER ---
TOKEN = os.getenv("BOT_TOKEN")
CEREBRAS_API_KEY = os.getenv("AI_API_KEY")
CHANNEL_ID = "@metaformula_life"
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png.png"

# Инициализация
client = Cerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class AuditState(StatesGroup):
    answering_questions = State()

# Мягкие формулировки в стиле МПТ [1, 1]
QUESTIONS = [
    "1. Если бы вы на мгновение представили, что являетесь на 100% Автором своей реальности, что бы вы изменили первым делом? (Или пока кажется, что события просто случаются с вами?)",
    "2. Замечаете ли вы моменты, когда мысли крутятся по кругу сами по себе, когда вы ничем не заняты? Как бы вы описали этот «фоновый шум» вашего ума?",
    "3. Какая ситуация сейчас больше всего забирает у вас силы? Если бы вы могли представить это препятствие как физический объект, на что бы оно было похоже?",
    "4. Когда вы направляете внимание на этот образ, что вы чувствуете в теле? Это может быть сжатие, тяжесть, холод или какое-то иное ощущение?",
    "5. Какое качество в других людях вас сейчас особенно задевает или раздражает? Если бы в этом качестве была скрыта какая-то свобода, которой вам не хватает, то какая именно?",
    "6. Как вам кажется, сколько еще времени вы готовы двигаться по этому повторяющемуся кругу, пока внутренний ресурс не иссякнет полностью?",
    "7. Готовы ли вы прямо сейчас попробовать перехватить управление у своего «Автопилота» и проложить путь из точки ясности?"
]

SYSTEM_PROMPT = """
Ты — «Мета-Навигатор», интеллектуальный агент Александра Лазаренко. Ты Проводник. 
ЗАДАЧА: Проанализировать ответы и выдать глубокий психологический аудит.

ПРИНЦИПЫ СТИЛЯ:
1. Используй ТОЛЬКО Markdown. Никаких двойных звездочек (** **) в тексте. Используй # и ## для заголовков.
2. Тон: Бережный, мудрый. Если используешь термины 'Застойная доминанта' или 'Режим заставки', кратко поясни их:
   - Застойная доминанта: как внутренний магнит, который стягивает на себя всю вашу энергию.
   - Режим заставки (ДСМ): когда мозг работает вхолостую, пережевывая старые сценарии.
3. МПТ: Возвращай авторство. Подсвети, как человек сам блокирует свою силу.

СТРУКТУРА ОТЧЕТА:
# Результаты Аудита Автопилота
## Уровень автоматизма: [Значение]%
## Анализ системы: [Описание сбоя и доминанты простыми словами]
## Метаформула решения: [Короткая фраза-ключ]
## Слово Проводника: [Бережное напутствие]
"""

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
        builder.row(types.InlineKeyboardButton(text="Присоединиться к проекту", url="https://t.me/metaformula_life"))
        builder.row(types.InlineKeyboardButton(text="Я в канале! Начать путь", callback_data="check_sub"))
        await message.answer("Добро пожаловать в Метаформулу Жизни.\n\nЯ — ваш Мета-Навигатор. Помогу увидеть программы вашего Автопилота и проложить путь к себе настоящему.\n\nЧтобы начать, пожалуйста, подпишитесь на наш канал:", reply_markup=builder.as_markup())
    else:
        await start_audit(message, state)

@dp.callback_query(F.data == "check_sub")
async def check_btn(callback: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(callback.from_user.id):
        await callback.message.answer("Доступ подтвержден. Мы начинаем.")
        await start_audit(callback.message, state)
    else:
        await callback.answer("Вы еще не подписаны на канал!", show_alert=True)

async def start_audit(message: types.Message, state: FSMContext):
    # ИСПРАВЛЕНО: добавлен пустой список
    await state.update_data(current_q=0, answers=[])
    
    try:
        await message.answer_photo(
            photo=LOGO_URL,
            caption="Ваш Авторский Маршрут начинается с этого момента осознания.\n\n"
                    "Большинство людей живут «на автопилоте» — в режиме экономии энергии мозга, который часто ведет нас по старым, чужим картам. "
                    "Я задам 7 вопросов, чтобы помочь вам увидеть эти программы со стороны.\n\n"
                    "Отвечайте искренне, доверяя первому отклику."
        )
    except Exception as e:
        print(f"Ошибка при отправке фото: {e}")
        await message.answer("Ваш Авторский Маршрут начинается здесь...")
    
    await asyncio.sleep(1)
    # ИСПРАВЛЕНО: отправляем первый вопрос, а не весь список
    await message.answer(QUESTIONS[0])
    await state.set_state(AuditState.answering_questions)

@dp.message(AuditState.answering_questions)
async def handle_questions(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_idx = data.get('current_q', 0)
    # ИСПРАВЛЕНО: добавлено значение по умолчанию []
    answers = data.get('answers', [])
    
    answers.append(f"Q{q_idx+1}: {message.text}")
    new_idx = q_idx + 1
    
    if new_idx < len(QUESTIONS):
        await state.update_data(current_q=new_idx, answers=answers)
        await message.answer(QUESTIONS[new_idx])
    else:
        await message.answer("Данные получены. Навигатор вычисляет вашу Метаформулу... 🌀")
        report = await generate_ai_report(answers)
        await message.answer(report, parse_mode="Markdown")
        await message.answer("Ваша Метаформула активирована. Будьте на связи в канале, скоро я открою доступ к следующему этапу пути.")
        await state.clear()

async def generate_ai_report(answers):
    user_input = "\n".join(answers)
    try:
        # ИСПРАВЛЕНО: добавлена структура messages
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
        # ИСПРАВЛЕНО: правильный доступ к результату
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка при генерации отчета: {e}")
        return f"Система временно недоступна: {str(e)[:100]}"

async def handle_health(request):
    return web.Response(text="active")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print("Мета-Навигатор запущен успешно.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
