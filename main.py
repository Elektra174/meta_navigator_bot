import os
import asyncio
import traceback
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cerebras.cloud.sdk import AsyncCerebras
from aiohttp import web

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
CEREBRAS_API_KEY = os.getenv("AI_API_KEY")
CHANNEL_ID = "@metaformula_life"
ADMIN_ID = 7830322013

# Прямые ссылки на изображения
LOGO_START_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo11.png"
LOGO_AUDIT_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/logo.png.png"
GUIDE_URL = "https://raw.githubusercontent.com/Elektra174/meta_navigator_bot/main/revizia_guide.pdf"

# Инициализируем асинхронный клиент Cerebras
client = AsyncCerebras(api_key=CEREBRAS_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Счетчики для мониторинга - инициализация
error_counter = 0
last_error_time = None
api_failures = 0

class AuditState(StatesGroup):
    answering_questions = State()

# Мягкие формулировки в стиле МПТ
QUESTIONS = [
    "1. Если бы Вы на мгновение представили, что являетесь на 100% Автором своей реальности, что бы Вы изменили первым делом?",
    "2. Замечаете ли Вы моменты, когда мысли крутятся по кругу сами по себе, когда Вы ничем не заняты? Как бы Вы описали этот «фоновый шум» Вашего ума? (Ваш «режим заставки» мозга).",
    "3. Какая ситуация сейчас больше всего «вытягивает» из Вас силы? Если бы у Вас был образ или метафора этой ситуации — на что бы они могли быть похожи?",
    "4. Когда Вы направляете внимание на этот образ, что Вы замечаете в теле? (Сжатие, тяжесть, холод или иное ощущение?)",
    "5. Какое качество в другом человеке Вас раздражает больше всего? Какую силу или свободу проявляет этот человек, которую Вы себе сейчас запрещаете?",
    "6. Как Вам кажется, сколько еще времени Вы готовы двигаться по этому повторяющемуся кругу (этой «петле»), пока внутренний ресурс не иссякнет полностью?",
    "7. Готовы ли Вы прямо сейчас попробовать перехватить управление у своего «Автопилота» и проложить путь из состояния ясности?"
]

SYSTEM_PROMPT = """
Ты — «Мета-Навигатор», интеллектуальный агент Александра Лазаренко. Ты Проводник. 
ЗАДАЧА: Проанализировать ответы пользователя и выдать глубокий отчет «Аудит Автопилота».

ПРИНЦИПЫ СТИЛЯ:
1. Обращение строго на «Вы». Только РУССКИЙ язык. Без слов 'возможно', 'наверное'.
2. Используй Markdown для заголовков (# и ##). НИКАКИХ двойных звездочек (** **) в тексте.
3. Разъясняй термины:
   - Застойная доминанта: внутренний магнит в мозгу, который стягивает Вашу энергию.
   - Дефолт-система мозга: режим «заставки», когда мозг пережевывает старые сценарии вхолостую.
4. МПТ: Возвращай авторство. Подсвети, как человек сам блокирует свою силу.
5. Давай намеки на конкретные шаги в скобках.

СТРУКТУРА ОТВЕТА (ОТЧЕТА):
# Результаты Аудита Автопилота
## Ваш Индекс Автоматизма: [Значение]%

---
## 🔍 Застойная доминанта
[Анализ ситуации и ощущений на 'Вы']

---
## 🌀 Дефолт-система мозга
[Анализ руминации и фонового шума]

---
## 👑 Ваша Позиция Автора
[Анализ силы и свободы. Намек на шаги в скобках]

---
## 🧠 Ваша Метаформула:  
### **[Короткая фраза-код]**

---
## 📖 Расшифровка Метаформулы
[Объяснение на 2-3 предложения, что это значит для клиента и как формула поможет выехать из 'гаража' автопилота].
"""

async def send_admin_alert(alert_type: str, details: str, traceback_info: str = ""):
    """Отправка оповещения администратору о проблемах"""
    global error_counter, api_failures  # Объявляем глобальные переменные
    
    try:
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        alert_messages = {
            "api_failure": "🚨 *СБОЙ API CEREBRAS*\n\n",
            "connection_error": "🔌 *ПРОБЛЕМА СВЯЗИ*\n\n",
            "bot_crash": "💥 *КРИТИЧЕСКАЯ ОШИБКА БОТА*\n\n",
            "rate_limit": "⏱️ *ИСЧЕРПАН ЛИМИТ API*\n\n",
            "warning": "⚠️ *ПРЕДУПРЕЖДЕНИЕ*\n\n"
        }
        
        message = alert_messages.get(alert_type, "⚠️ *ПРОБЛЕМА С БОТОМ*\n\n")
        message += f"🕒 *Время:* {timestamp}\n"
        message += f"📊 *Тип проблемы:* {alert_type}\n\n"
        message += f"📝 *Детали:*\n{details}\n"
        
        if traceback_info:
            message += f"\n🔧 *Traceback:*\n```\n{traceback_info[:1500]}\n```"
        
        # Добавляем счетчики ошибок
        message += f"\n📈 *Статистика:*\n• Всего ошибок за сессию: {error_counter}\n• Сбоев API: {api_failures}"
        
        await bot.send_message(chat_id=ADMIN_ID, text=message, parse_mode="Markdown")
        return True
    except Exception as e:
        print(f"Не удалось отправить алерт администратору: {e}")
        return False

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        # Логируем ошибку проверки подписки
        await send_admin_alert(
            "warning", 
            f"Ошибка проверки подписки для пользователя {user_id}", 
            str(e)
        )
        return False

async def send_report_to_admin(user_info: types.User, answers: list, report: str):
    """Отправка полного отчета администратору"""
    try:
        user_details = (
            "🔔 *НОВЫЙ ОТЧЕТ АУДИТА*\n\n"
            f"👤 *Пользователь:*\n"
            f"• ID: `{user_info.id}`\n"
            f"• Имя: {user_info.first_name or 'Не указано'}\n"
            f"• Username: @{user_info.username or 'Нет'}\n"
            f"• Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            "📝 *Оригинальные ответы:*\n"
        )
        for answer in answers:
            user_details += f"• {answer}\n"
        user_details += f"\n📊 *Отчет AI:*\n\n{report}"
        
        await bot.send_message(chat_id=ADMIN_ID, text=user_details[:4000], parse_mode="Markdown")
        return True
    except Exception as e:
        await send_admin_alert(
            "connection_error",
            f"Ошибка отправки отчета администратору. Пользователь: {user_info.id}",
            str(e)
        )
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    global error_counter  # Объявляем глобальную переменную
    
    try:
        await state.clear()
        if not await is_subscribed(message.from_user.id):
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(text="Присоединиться к проекту", url="https://t.me/metaformula_life"))
            builder.row(types.InlineKeyboardButton(text="Я в канале! Начать путь", callback_data="check_sub"))
            try:
                await message.answer_photo(
                    photo=LOGO_START_URL,
                    caption="Добро пожаловать в «Метаформулу Жизни».\n\n"
                            "Меня зовут Александр Лазаренко. Я — автор и проводник проекта. Помогу Вам увидеть программы Вашего Автопилота и проложить маршрут к себе настоящему.\n\n"
                            "Чтобы начать, пожалуйста, подпишитесь на наш канал:",
                    reply_markup=builder.as_markup()
                )
            except:
                await message.answer("Добро пожаловать в «Метаформулу Жизни»...", reply_markup=builder.as_markup())
        else:
            await start_audit(message, state)
    except Exception as e:
        error_counter += 1
        await send_admin_alert(
            "bot_crash",
            f"Ошибка в команде /start от пользователя {message.from_user.id}",
            traceback.format_exc()
        )
        await message.answer("⚠️ Произошла техническая ошибка. Мы уже работаем над её устранением.")

@dp.callback_query(F.data == "check_sub")
async def check_btn(callback: types.CallbackQuery, state: FSMContext):
    global error_counter  # Объявляем глобальную переменную
    
    try:
        if await is_subscribed(callback.from_user.id):
            await callback.message.answer("Доступ подтвержден.")
            await start_audit(callback.message, state)
        else:
            await callback.answer("Вы еще не подписаны!", show_alert=True)
    except Exception as e:
        error_counter += 1
        await send_admin_alert(
            "bot_crash",
            f"Ошибка в обработке callback от пользователя {callback.from_user.id}",
            traceback.format_exc()
        )

async def start_audit(message: types.Message, state: FSMContext):
    try:
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
    except Exception as e:
        global error_counter  # Объявляем глобальную переменную
        error_counter += 1
        await send_admin_alert(
            "bot_crash",
            f"Ошибка при запуске аудита пользователем {message.from_user.id}",
            traceback.format_exc()
        )

@dp.message(AuditState.answering_questions)
async def handle_questions(message: types.Message, state: FSMContext):
    global error_counter  # Объявляем глобальную переменную
    
    try:
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
            user_info = message.from_user
            final_answers = answers.copy()
            report = await generate_ai_report(answers)
            
            await message.answer(report, parse_mode="Markdown")
            await send_report_to_admin(user_info, final_answers, report)
            
            try:
                await message.answer_document(
                    document=GUIDE_URL,
                    caption="Вы получили Вашу Метаформулу. Активация — в Ваших руках.\n\n"
                            "Но знание формулы — это лишь ключ. Чтобы он реально повернулся в замке и Ваша машина жизни выехала из гаража «автопилота», изучите гайд «Ревизия маршрута».\n\n"
                            "Это Ваш первый шап к реальным переменам. Будьте на связи в канале!"
                )
            except:
                await message.answer("Ваша Метаформула получена. Активация — в Ваших руках. Гайд по активации ждет Вас в закрепе канала!")
            await state.clear()
    except Exception as e:
        error_counter += 1
        await send_admin_alert(
            "bot_crash",
            f"Ошибка обработки ответов пользователя {message.from_user.id}",
            traceback.format_exc()
        )
        await message.answer("⚠️ Произошла ошибка при обработке ваших ответов. Попробуйте начать заново с команды /start")

async def generate_ai_report(answers):
    global error_counter, api_failures, last_error_time  # Объявляем глобальные переменные
    
    user_input = "\n".join(answers)
    try:
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            model="llama-3.3-70b",
            temperature=0.4,
            top_p=0.9,
            max_completion_tokens=2048
        )
        
        # Сбрасываем счетчик ошибок API при успешном запросе
        api_failures = 0
        
        return response.choices[0].message.content
        
    except Exception as e: 
        error_counter += 1
        api_failures += 1
        last_error_time = datetime.now()
        
        error_message = str(e).lower()
        
        # Определяем тип ошибки
        if "rate limit" in error_message or "quota" in error_message or "limit" in error_message:
            alert_type = "rate_limit"
            details = "Исчерпан лимит запросов к Cerebras API. Требуется пополнение баланса или ожидание сброса лимита."
        elif "connection" in error_message or "timeout" in error_message or "network" in error_message:
            alert_type = "connection_error"
            details = "Проблема с подключением к Cerebras API. Проверьте интернет-соединение и доступность сервиса."
        elif "authentication" in error_message or "key" in error_message or "token" in error_message:
            alert_type = "api_failure"
            details = "Проблема с аутентификацией API ключа. Проверьте корректность CEREBRAS_API_KEY."
        elif "service unavailable" in error_message or "503" in error_message:
            alert_type = "api_failure"
            details = "Сервис Cerebras временно недоступен. Возможно, проводятся технические работы."
        else:
            alert_type = "api_failure"
            details = f"Неизвестная ошибка API: {error_message}"
        
        # Отправляем алерт администратору
        await send_admin_alert(
            alert_type,
            details,
            traceback.format_exc()
        )
        
        # Формируем сообщение для пользователя
        if alert_type == "rate_limit":
            user_message = """⏱️ *Превышен лимит запросов*

Наш AI-навигатор временно недоступен из-за превышения лимита запросов.

Администратор уже уведомлен и работает над решением проблемы.

Попробуйте позже или обратитесь в поддержку @metaformula_life"""
        elif alert_type == "connection_error":
            user_message = """🔌 *Проблема с подключением*

Не удалось соединиться с AI-навигатором.

Возможные причины:
• Проблемы с интернет-соединением
• Временная недоступность сервиса

Администратор уведомлен. Попробуйте через 5-10 минут."""
        else:
            user_message = f"""🚧 *Система временно недоступен*

Наш AI-навигатор сейчас перегружен или находится на техническом обслуживании. 

Администратор уже работает над решением проблемы.

Что вы можете сделать:
1. Попробуйте через 5-10 минут
2. Обратитесь в поддержку @metaformula_life

Техническая информация: {str(e)[:100]}"""
        
        return user_message

async def handle_health(request): 
    return web.Response(text="active")

async def send_startup_notification():
    """Отправка уведомления о запуске бота"""
    try:
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        message = (
            "✅ *МЕТА-НАВИГАТОР ЗАПУЩЕН*\n\n"
            f"🕒 *Время запуска:* {timestamp}\n"
            f"🤖 *Bot:* @{(await bot.get_me()).username}\n"
            f"🔑 *Cerebras API:* {'✅ Настроен' if CEREBRAS_API_KEY else '❌ НЕТ КЛЮЧА!'}\n"
            f"🌐 *Health check:* http://0.0.0.0:{os.environ.get('PORT', 8080)}/"
        )
        await bot.send_message(chat_id=ADMIN_ID, text=message, parse_mode="Markdown")
    except Exception as e:
        print(f"Не удалось отправить уведомление о запуске: {e}")

async def main():
    # Веб-сервер для health check
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    
    # Отправляем уведомление о запуске
    await send_startup_notification()
    
    print("✅ Мета-Навигатор запущен успешно.")
    print(f"🤖 Bot: @{(await bot.get_me()).username}")
    print(f"🔑 Cerebras API: {'Настроен' if CEREBRAS_API_KEY else 'НЕТ КЛЮЧА!'}")
    print(f"🌐 Health check: http://0.0.0.0:{os.environ.get('PORT', 8080)}/")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        # Критическая ошибка - бот упал полностью
        await send_admin_alert(
            "bot_crash",
            f"Бот полностью остановлен! Требуется немедленное вмешательство.",
            traceback.format_exc()
        )
        raise e

if __name__ == "__main__": 
    asyncio.run(main())
