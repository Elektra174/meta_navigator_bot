import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cerebras.cloud.sdk import Cerebras
from aiohttp import web

# --- КОНФИГУРАЦИЯ (Ключи берем из переменных Render) ---
TOKEN = os.getenv("BOT_TOKEN")
CEREBRAS_API_KEY = os.getenv("AI_API_KEY")
CHANNEL_ID = "@metaformula_life"
LOGO_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png.png"
GUIDE_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/revizia_guide.pdf"

# Инициализация
client = Cerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class AuditState(StatesGroup):
    answering_questions = State()

# Мягкие формулировки в стиле МПТ
QUESTIONS = [
    "1. Если бы Вы на мгновение представили, что являетесь на 100% Автором своей реальности, что бы Вы изменили первым делом? (Или пока кажется, что события просто случаются с Вами?)",
    "2. Замечаете ли Вы моменты, когда мысли крутятся по кругу сами по себе, когда Вы ничем не заняты? Как бы Вы описали этот «фоновый шум» Вашего ума? (Ваш «режим заставки» мозга).",
    "3. Какая ситуация сейчас больше всего «вытягивает» из Вас силы? Если бы у Вас был образ или метафора этой ситуации — на что бы они могли быть похожи?",
    "4. Когда Вы направляете внимание на этот образ, что Вы замечаете в теле? Это может быть сжатие, тяжесть, холод или иное ощущение?",
    "5. Какое качество в других людях Вас раздражает больше всего? Попробуйте увидеть: какую силу или свободу проявляет этот человек, которую Вы сейчас себе запрещаете?",
    "6. Как Вам кажется, сколько еще времени Вы готовы двигаться по этому повторяющемуся кругу (этой «петле»), пока внутренний ресурс не иссякнет?",
    "7. Готовы ли Вы прямо сейчас попробовать перехватить управление у своего «Автопилота» и проложить путь из точки ясности?"
]

SYSTEM_PROMPT = """
Ты — «Мета-Навигатор», интеллектуальный агент Александра Лазаренко. Ты Проводник. 
ЗАДАЧА: Проанализировать ответы пользователя и выдать глубокий психологический аудит.

ПРИНЦИПЫ СТИЛЯ:
1. Обращение строго на «Вы». Русский язык.
2. Используй Markdown для заголовков (# и ##). НИКАКИХ двойных звездочек (** **) в тексте.
3. Разъясняй термины:
   - Застойная доминанта: внутренний магнит, стягивающий Вашу энергию.
   - Дефолт-система мозга (ДСМ): режим «заставки», когда мозг пережевывает старые сценарии вхолостую.
4. МПТ: Возвращай авторство. Подсвети, как человек сам блокирует свою силу.
5. Давай намеки на конкретные шаги в скобках.
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
        await message.answer("Добро пожаловать в «Метаформулу Жизни».\n\nМеня зовут Александр Лазаренко. Я — автор и проводник проекта. Помогу Вам увидеть программы Вашего Автопилота и проложить путь к себе настоящему.\n\nЧтобы начать, пожалуйста, подпишитесь на наш канал:", reply_markup=builder.as_markup())
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
    # ИСПРАВЛЕНО: добавлено значение []
    await state.update_data(current_q=0, answers=[])
    
    try:
        await message.answer_photo(
            photo=LOGO_URL, 
            caption="Ваш Авторский Маршрут начинается здесь.\n\nБольшинство людей живут «на автопилоте» — в режиме экономии энергии мозга. Я задам 7 вопросов, чтобы помочь Вам увидеть эти программы со стороны.\n\nОтвечайте искренне, доверяя первому отклику."
        )
    except Exception as e:
        print(f"Ошибка при отправке фото: {e}")
        await message.answer("Ваш Авторский Маршрут начинается здесь...")
    
    await asyncio.sleep(1)
    # ИСПРАВЛЕНО: отправляем ПЕРВЫЙ вопрос
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
        await message.answer("Данные получены. Навигатор вычисляет Вашу Метаформулу... 🌀")
        report = await generate_ai_report(answers)
        await message.answer(report, parse_mode="Markdown")
        
        # ЛОГИКА ВЫДАЧИ ГАЙДА И ТЕКСТ ПРО АКТИВАЦИЮ 
        try:
            await message.answer_document(
                document=GUIDE_URL,
                # ИСПРАВЛЕНО: кавычки
                caption="Вы получили Вашу Метаформулу. Активация — в Ваших руках.\n\n"
                        "Но знание формулы — это лишь код доступа. Чтобы она реально «прописалась» в Вашем мозге, изучите гайд «Ревизия маршрута». \n\n"
                        "Он поможет Вам сделать первый шаг из состояния Автора прямо сейчас."
            )
        except Exception as e:
            print(f"Ошибка при отправке гайда: {e}")
            await message.answer("Вы получили Вашу Метаформулу. Активация — в Ваших руках. Гайд доступен в закрепе канала!")
        
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
