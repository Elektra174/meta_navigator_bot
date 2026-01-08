# app.py - Минимальная версия для Render.com
import os
import asyncio
import signal
import sys

# Отключаем все обработчики сигналов ПЕРЕД импортом библиотек
signal.signal(signal.SIGALRM, signal.SIG_DFL)
signal.signal(signal.SIGCHLD, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGTERM, signal.SIG_DFL)
signal.signal(signal.SIGUSR1, signal.SIG_DFL)
signal.signal(signal.SIGUSR2, signal.SIG_DFL)

# Отключаем debug режим
os.environ['PYTHONASYNCIODEBUG'] = '0'

# Устанавливаем policy для asyncio
if sys.platform != 'win32':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

# Запускаем основной бот
from main import главная

if __name__ == "__main__":
    try:
        # Запускаем с обработкой KeyboardInterrupt
        asyncio.run(главная())
    except KeyboardInterrupt:
        print("Бот остановлен пользователем")
        sys.exit(0)
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)
