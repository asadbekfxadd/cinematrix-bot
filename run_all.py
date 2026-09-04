"""
Запускает ОДНОВРЕМЕННО бота (main.py) и веб-панель статистики (dashboard.py)
в одном процессе-контейнере на Railway.

Почему так: Railway запускает один процесс на сервис. Чтобы бот и дашборд
работали вместе и видели одну и ту же базу filmix.db, оба запускаются
как под-процессы отсюда.

Если один из них падает — скрипт сам перезапускает его через 5 секунд,
чтобы весь сервис не остановился из-за случайной ошибки в одной части.
"""

import subprocess
import sys
import time

PYTHON = sys.executable


def start(script_name):
    print(f"🚀 Запускаю {script_name} ...")
    return subprocess.Popen([PYTHON, script_name])


def main():
    bot_proc = start("main.py")
    dash_proc = start("dashboard.py")

    try:
        while True:
            time.sleep(5)
            if bot_proc.poll() is not None:
                print("⚠️ main.py остановился, перезапускаю...")
                bot_proc = start("main.py")
            if dash_proc.poll() is not None:
                print("⚠️ dashboard.py остановился, перезапускаю...")
                dash_proc = start("dashboard.py")
    except KeyboardInterrupt:
        bot_proc.terminate()
        dash_proc.terminate()


if __name__ == "__main__":
    main()
