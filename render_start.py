# render_start.py
import os
import sys
import signal

# Для Render.com: игнорируем сигналы, которые вызывают ошибки
signal.signal(signal.SIGALRM, signal.SIG_IGN)
signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Отключаем debug режим asyncio
os.environ['PYTHONASYNCIODEBUG'] = '0'

# Запускаем основной модуль
if __name__ == "__main__":
    try:
        import asyncio
        from main import главная
        
        # Настраиваем asyncio для Render.com
        if sys.platform != 'win32':
            try:
                import uvloop
                uvloop.install()
            except ImportError:
                pass
        
        # Запускаем приложение
        asyncio.run(главная())
    except KeyboardInterrupt:
        print("Бот остановлен пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)
