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

# Прямые ссылки на изображения
LOGO_START_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo11.png"
LOGO_AUDIT_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png.png"
GUIDE_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/revizia_guide.pdf"

client = Cerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class AuditState(StatesGroup):
    answering_questions = State()

# Мягкие формулировки в стиле МПТ 
QUESTIONS = [
    "1. Если бы Вы на мгновение представили, что являетесь на 100% Автором своей реальности, что бы Вы изменили первым делом?",
    "2. Замечаете ли Вы моменты, когда мысли крутятся по кругу сами по себе, когда Вы ничем не заняты? Как бы Вы описали этот «фоновый шум» Вашего ума?",
    "3. Какая ситуация сейчас больше всего «вытягивает» из Вас силы? Если бы у Вас был образ или метафора этой ситуации — на что бы это могло быть похоже?",
    "4. Когда Вы направляете внимание на этот образ, что Вы замечаете в теле? (Сжатие, тяжесть, холод или иное ощущение?)",
    "5. Какое качество в другом человеке Вас раздражает больше всего? Какую силу или свободу проявляет этот человек, которую Вы себе сейчас запрещаете?",
    "6. Как Вам кажется, сколько еще времени Вы готовы двигаться по этому повторяющемуся кругу (этой «петле»), пока внутренний ресурс не иссякнет полностью?",
    "7. Готовы ли Вы прямо сейчас попробовать перехватить управление у своего «Автопилота» и проложить путь из состояния ясности?"
]

SYSTEM_PROMPT = """
Ты — «Мета-Навигатор», интеллектуальный агент Александра Лазаренко. Ты Проводник. 
ЗАДАЧА: Проанализировать ответы и выдать глубокий отчет «Аудит Автопилота».

ПРИНЦИПЫ СТИЛЯ:
1. Обращение строго на «Вы». Только русский язык. Без слов 'возможно', 'наверное'.
2. Используй Markdown для заголовков (# и ##). НИКАКИХ двойных звездочек (** **) в тексте.
3. Разъясняй термины:
   - Застойная доминанта: как внутренний магнит, который стягивает Вашу энергию.
   - Дефолт-система мозга (ДСМ): режим «заставки», когда мозг пережевывает старые сценарии вхолостую.
4. МПТ: Возвращай авторство. Подсвети, как человек сам блокирует свою силу.
5. Давай намеки на конкретные шаги в скобках (например: начать замечать моменты 'жвачки' или делать микродвижения из нового состояния).

СТРУКТУРА ОТВЕТА (ОБЯЗАТЕЛЬНО В НАЧАЛЕ):
# Результаты Аудита Автопилота
## Индекс Автоматизма: [Вычисленное значение]%

## Застойная доминанта
[Анализ образа из Вопроса №3 и ощущений из №4]

## Дефолт-система мозга (ДСМ)
[Анализ руминации из Вопроса №2]

## Ваше состояние Автора
[Анализ Вопроса №5 и №7. Намек на шаги в скобках]

## Ваша Метаформула: [Короткая фраза-код]
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
        
        try:
            await message.answer_photo(
                photo=LOGO_START_URL,
                caption="Добро пожаловать в «Метаформулу Жизни».\n\n"
                        "Меня зовут Александр Лазаренко. Я помогу Вам увидеть программы Вашего Автопилота и проложить маршрут к себе настоящему.\n\n"
                        "Чтобы начать, пожалуйста, подпишитесь на наш канал:",
                reply_markup=builder.as_markup()
            )
        except:
            await message.answer("Добро пожаловать в «Метаформулу Жизни»...", reply_markup=builder.as_markup())
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
    await state.update_data(current_q=0, answers=[])
    try:
        await message.answer_photo(
            photo=LOGO_AUDIT_URL,
            caption="Ваш Авторский Маршрут начинается сейчас.\n\n"
                    "Я задам 7 вопросов, чтобы помочь Вам увидеть программы Автопилота со стороны.\n\n"
                    "Отвечайте искренне, доверяя первому отклику."
        )
    except:
        await message.answer("Ваш Авторский Маршрут начинается сейчас...")
    
    await asyncio.sleep(1)
    await message.answer(QUESTIONS[0])
    await state.set_state(AuditState.answering_questions)

@dp.message(AuditState.answering_questions)
async def handle_questions(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_idx = data.get('current_q', 0)
    answers = data.get('answers', [])
    
    answers.append(f"Вопрос №{q_idx+1}: {message.text}")
    new_idx = q_idx + 1
    
    if new_idx < len(QUESTIONS):
        await state.update_data(current_q=new_idx, answers=answers)
        await message.answer(QUESTIONS[new_idx])
    else:
        await message.answer("Данные получены. Навигатор вычисляет Вашу Метаформулу... 🌀")
        report = await generate_ai_report(answers)
        await message.answer(report, parse_mode="Markdown")
        
        try:
            await message.answer_document(
                document=GUIDE_URL,
                caption="Вы получили Вашу Метаформулу. Активация — в Ваших руках.\n\n"
                        "Но знание формулы — это лишь код доступа. Чтобы она реально «прописалась» в Вашем мозге, изучите гайд «Ревизия маршрута».\n\n"
                        "Будьте на связи в канале!"
            )
        except:
            await message.answer("Ваша Метаформула получена. Гайд доступен в закрепе канала!")
        await state.clear()

async def generate_ai_report(answers):
    user_input = "\n".join(answers)
    try:
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
        return f"Система временно недоступна: {str(e)[:100]}"

async def handle_health(request): 
    return web.Response(text="active")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start()
    print("Бот запущен успешно.")
    await dp.start_polling(bot)

if __name__ == "__main__": 
    asyncio.run(main())


