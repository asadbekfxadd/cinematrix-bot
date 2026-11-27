"""Настройки FILMIX. Всё секретное берётся из переменных окружения (Railway → Variables)."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
VIDEO_CHANNEL_ID = os.getenv("VIDEO_CHANNEL_ID")  # канал-хранилище видео, например -1001234567890

# Модель Claude можно поменять без правки кода: Railway → Variables → AI_MODEL
AI_MODEL = os.getenv("AI_MODEL", "claude-haiku-4-5-20251001")

# 1 = видео из бота нельзя переслать/сохранить (защита контента)
PROTECT_CONTENT = os.getenv("PROTECT_CONTENT", "0") == "1"

TMDB_URL = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://voluble-croissant-d09014.netlify.app")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Filmix_bot")

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "6250747288,862911155").split(",") if x.strip()]

# Утренняя рассылка «фильм дня» — окно по времени Ташкента (с 8:00 до 10:59)
MORNING_FROM_HOUR = int(os.getenv("MORNING_FROM_HOUR", "8"))
MORNING_TO_HOUR = int(os.getenv("MORNING_TO_HOUR", "10"))

TZ = ZoneInfo("Asia/Tashkent")
DT_FMT = "%Y-%m-%d %H:%M"


def now_local() -> datetime:
    """Текущее время по Ташкенту (без tzinfo — так совместимо со старыми строками в БД)."""
    return datetime.now(TZ).replace(tzinfo=None)


def now_str() -> str:
    return now_local().strftime(DT_FMT)
