import asyncio
import aiohttp
import urllib.parse
import sqlite3
import os
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TMDB_URL = "https://api.themoviedb.org/3"
MINI_APP_URL = "https://voluble-croissant-d09014.netlify.app"
ADMIN_IDS = [6250747288, 862911155]
BOT_USERNAME = "Filmix_bot"
VIDEO_CHANNEL_ID = os.getenv("VIDEO_CHANNEL_ID")  # ID канала с видео, например -1001234567890

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== ТЕКСТЫ =====
TEXTS = {
    "ru": {
        "welcome": (
            "🎬 Добро пожаловать в *FILMIX*!\n\n"
            "📌 Как пользоваться:\n"
            "🔢 *ID фильма* — например: `572802`\n"
            "🔤 *Название* — например: `Интерстеллар`\n"
            "🎭 *Актёр* — например: `Tom Hanks`\n"
            "🤖 *Опиши сцену* — например: `фильм где человек застрял на острове`\n"
            "🎯 *Попроси совет* — например: `посоветуй фильм про зомби`\n\n"
            "Используй кнопки внизу 👇"
        ),
        "choose_section": "Выбери раздел:",
        "subscribe": "📢 Подпишись на канал и нажми кнопку!",
        "check_sub": "✅ Проверить подписку",
        "not_subscribed": "❌ Ты ещё не подписался!",
        "ai_searching": "🤖 AI ищет фильм по описанию...",
        "ai_recommending": "🎯 AI подбирает фильмы для тебя...",
        "ai_found": "🤖 AI думает это *{}*!",
        "ai_not_found": "❌ AI не смог определить. Попробуй подробнее!",
        "ai_no_result": "🤖 AI думает это *{}*, но не найдено.",
        "not_found": "❌ Ничего не найдено.\n\nПопробуй:\n• ID: `572802`\n• Название: `Интерстеллар`\n• Актёр: `Tom Hanks`\n• `посоветуй фильм про зомби`",
        "film_not_found": "❌ Фильм не найден. Проверь ID.",
        "rating": "⭐ Рейтинг: {}/10",
        "similar": "🎬 Похожие",
        "actors": "👥 Актёры",
        "actors_title": "👥 *Актёры:*\n\n",
        "actor_movies": "🎭 *{}*\n\nЛистай карточки 👇",
        "no_similar": "Похожих не найдено",
        "no_actors": "Актёры не найдены",
        "top": "🔥 Топ фильмов",
        "new": "🆕 Новинки",
        "upcoming": "🎬 Скоро в кино",
        "uzbek": "🇺🇿 Узбек кино",
        "tv_shows": "📺 Сериалы",
        "favorites": "❤️ Избранное",
        "quiz": "🎮 Квиз",
        "invite": "👥 Пригласить",
        "recommend": "🎯 Подобрать",
        "no_favorites": "❤️ У тебя пока нет избранных.\n\nНажми ❤️ под любым фильмом!",
        "added_fav": "❤️ Добавлено в избранное!",
        "removed_fav": "💔 Убрано из избранного",
        "fav_btn": "❤️ В избранное",
        "unfav_btn": "💔 Убрать",
        "open_film": "✅ Открыть",
        "invite_text": "👥 *Реферальная система*\n\nТвоя ссылка:\n`{}`\n\n📊 Ты пригласил: *{}* человек\n\n🎁 За каждого приглашённого — 24 часа без подписки!",
        "new_user": "🎉 По твоей ссылке пришёл новый пользователь!\n👥 Всего приглашено: *{}*\n🎁 Тебе выдан бонус — 24 часа без подписки!",
        "quiz_title": "🎮 *Угадай фильм!*\n\n📝 {}\n\nВыбери правильный ответ:",
        "quiz_correct": "✅ Правильно!",
        "quiz_wrong": "❌ Неправильно! Правильный ответ: {}",
        "quiz_expired": "Квиз истёк!",
        "stats": "📊 *Статистика FILMIX*\n\n👥 Всего: *{}*\n🔥 Сегодня: *{}*\n🔍 Запросов: *{}*\n🔗 Рефералов: *{}*\n\n👤 Твои приглашения: *{}*",
        "no_access": "❌ Нет доступа.",
        "posting": "📤 Постим...",
        "posted": "✅ *{}* запостен!",
        "post_error": "❌ Фильм не найден.",
        "broadcast_usage": "❌ Используй: `/broadcast Привет всем!`",
        "broadcast_done": "✅ Рассылка завершена!\n📨 Отправлено: *{}*\n❌ Ошибок: *{}*",
        "broadcast_sending": "📢 Отправляю {} пользователям...",
        "no_desc": "Описание отсутствует",
        "choose_lang": "Выбери язык / Tilni tanlang:",
        "session_expired": "Сессия истекла, повтори поиск",
        "morning_msg": "🌅 *Доброе утро!*\n\n🎬 Фильм дня:\n\n*{}* ({})\n⭐ Рейтинг: {}/10\n\n📝 {}\n\n🆔 Код: `{}`\n\nОткрой бота и введи код 👆",
        "resubscribe": "📢 Привет! Ты отписался от канала.\n\nЧтобы продолжить — подпишись снова:",
        "recommend_prompt": "🎯 *Что посоветовать?*\n\nНапиши что хочешь посмотреть:\n\n• `фильмы про зомби`\n• `комедии для семьи`\n• `триллеры как Джокер`\n• `мультики для детей`\n• `боевики с Ван Даммом`",
        "ai_recommend_result": "🎯 *AI подобрал для тебя:*\n\nЛистай карточки 👇",
        "uzbek_films": "🇺🇿 *Узбекское кино:*\n\nЛистай карточки 👇",
        "tv_top": "📺 *Топ сериалов:*\n\nЛистай карточки 👇",
        "pick_prompt": "🔎 Под кодом `{}` найдено два варианта.\n\nВы искали фильм или сериал?",
    },
    "uz": {
        "welcome": (
            "🎬 *FILMIX* ga xush kelibsiz!\n\n"
            "📌 Qanday foydalanish:\n"
            "🔢 *Film ID* — masalan: `572802`\n"
            "🔤 *Nomi* — masalan: `Interstellar`\n"
            "🎭 *Aktyor* — masalan: `Tom Hanks`\n"
            "🤖 *Sahnani tasvirla* — masalan: `orol ustida qolgan odam haqida film`\n"
            "🎯 *Maslahat so'ra* — masalan: `zombi haqida film tavsiya qil`\n\n"
            "Pastdagi tugmalardan foydalaning 👇"
        ),
        "choose_section": "Bo'limni tanlang:",
        "subscribe": "📢 Kanalga obuna bo'ling va tugmani bosing!",
        "check_sub": "✅ Obunani tekshirish",
        "not_subscribed": "❌ Siz hali obuna bo'lmagansiz!",
        "ai_searching": "🤖 AI filmni tavsif bo'yicha qidirmoqda...",
        "ai_recommending": "🎯 AI siz uchun filmlar tanlamoqda...",
        "ai_found": "🤖 AI bu *{}* deb o'ylaydi!",
        "ai_not_found": "❌ AI filmni aniqlay olmadi. Batafsil tasvirlang!",
        "ai_no_result": "🤖 AI bu *{}* deb o'ylaydi, lekin topilmadi.",
        "not_found": "❌ Hech narsa topilmadi.\n\nUrinib ko'ring:\n• ID: `572802`\n• Nomi: `Interstellar`\n• Aktyor: `Tom Hanks`\n• `zombi haqida film tavsiya qil`",
        "film_not_found": "❌ Film topilmadi. ID ni tekshiring.",
        "rating": "⭐ Reyting: {}/10",
        "similar": "🎬 O'xshash",
        "actors": "👥 Aktyorlar",
        "actors_title": "👥 *Aktyorlar:*\n\n",
        "actor_movies": "🎭 *{}*\n\nKartochkalarni aylantiring 👇",
        "no_similar": "O'xshash film topilmadi",
        "no_actors": "Aktyorlar topilmadi",
        "top": "🔥 Top filmlar",
        "new": "🆕 Yangiliklar",
        "upcoming": "🎬 Tez chiqadi",
        "uzbek": "🇺🇿 O'zbek kino",
        "tv_shows": "📺 Seriallar",
        "favorites": "❤️ Sevimlilar",
        "quiz": "🎮 Viktorina",
        "invite": "👥 Taklif qilish",
        "recommend": "🎯 Tavsiya",
        "no_favorites": "❤️ Hali sevimli filmlaringiz yo'q.\n\nIstalgan film ostidagi ❤️ ni bosing!",
        "added_fav": "❤️ Sevimlilarga qo'shildi!",
        "removed_fav": "💔 Sevimlilardan olib tashlandi",
        "fav_btn": "❤️ Sevimlilarga",
        "unfav_btn": "💔 O'chirish",
        "open_film": "✅ Ochish",
        "invite_text": "👥 *Referal tizimi*\n\nSizning havolangiz:\n`{}`\n\n📊 Siz taklif qildingiz: *{}* kishi\n\n🎁 Har bir taklif qilingan uchun — 24 soat obunasiz!",
        "new_user": "🎉 Sizning havolangiz orqali yangi foydalanuvchi keldi!\n👥 Jami: *{}*\n🎁 Sizga bonus — 24 soat obunasiz!",
        "quiz_title": "🎮 *Filmni toping!*\n\n📝 {}\n\nTo'g'ri javobni tanlang:",
        "quiz_correct": "✅ To'g'ri!",
        "quiz_wrong": "❌ Noto'g'ri! To'g'ri javob: {}",
        "quiz_expired": "Viktorina muddati tugadi!",
        "stats": "📊 *FILMIX statistikasi*\n\n👥 Jami: *{}*\n🔥 Bugun: *{}*\n🔍 So'rovlar: *{}*\n🔗 Referallar: *{}*\n\n👤 Sizning takliflaringiz: *{}*",
        "no_access": "❌ Ruxsat yo'q.",
        "posting": "📤 Joylashtirilmoqda...",
        "posted": "✅ *{}* joylashtirildi!",
        "post_error": "❌ Film topilmadi.",
        "broadcast_usage": "❌ Foydalaning: `/broadcast Hammaga salom!`",
        "broadcast_done": "✅ Yuborish tugadi!\n📨 Yuborildi: *{}*\n❌ Xatolar: *{}*",
        "broadcast_sending": "📢 {} foydalanuvchiga yuborilmoqda...",
        "no_desc": "Tavsif mavjud emas",
        "choose_lang": "Tilni tanlang / Выбери язык:",
        "session_expired": "Sessiya tugadi, qaytadan qidiring",
        "morning_msg": "🌅 *Xayrli tong!*\n\n🎬 Kunning filmi:\n\n*{}* ({})\n⭐ Reyting: {}/10\n\n📝 {}\n\n🆔 Kod: `{}`\n\nBotni oching va kodni kiriting 👆",
        "resubscribe": "📢 Salom! Kanaldan obunani bekor qildingiz.\n\nDavom ettirish uchun qayta obuna bo'ling:",
        "recommend_prompt": "🎯 *Nima tavsiya qilay?*\n\nNimani ko'rmoqchi ekanligingizni yozing:\n\n• `zombi haqida filmlar`\n• `oilaviy komediyalar`\n• `Joker kabi trillerlar`\n• `bolalar uchun multfilmlar`",
        "ai_recommend_result": "🎯 *AI siz uchun tanladi:*\n\nKartochkalarni aylantiring 👇",
        "uzbek_films": "🇺🇿 *O'zbek kinolari:*\n\nKartochkalarni aylantiring 👇",
        "tv_top": "📺 *Top seriallar:*\n\nKartochkalarni aylantiring 👇",
        "pick_prompt": "🔎 `{}` kodi ostida ikkita variant topildi.\n\nSiz film yoki serial qidiryapsizmi?",
    }
}

def tr(user_id, key, *args):
    lang = get_lang(user_id)
    text = TEXTS[lang].get(key, TEXTS["ru"].get(key, key))
    if args:
        try:
            return text.format(*args)
        except:
            return text
    return text

def get_menu(user_id):
    lang = get_lang(user_id)
    tx = TEXTS[lang]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tx["top"]), KeyboardButton(text=tx["new"]), KeyboardButton(text=tx["upcoming"])],
            [KeyboardButton(text=tx["uzbek"]), KeyboardButton(text=tx["tv_shows"]), KeyboardButton(text=tx["favorites"])],
            [KeyboardButton(text=tx["quiz"]), KeyboardButton(text=tx["recommend"]), KeyboardButton(text=tx["invite"])],
            [KeyboardButton(text="🎬 FILMIX App", web_app=types.WebAppInfo(url=MINI_APP_URL))]
        ],
        resize_keyboard=True,
        persistent=True
    )

search_cache = {}

# ===== БД =====
def init_db():
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        joined_at TEXT, last_active TEXT, requests_count INTEGER DEFAULT 0,
        invited_by INTEGER, bonus_until TEXT, lang TEXT DEFAULT 'ru')""")
    c.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, movie_id INTEGER, title TEXT,
        year TEXT, rating REAL, poster TEXT, added_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inviter_id INTEGER, invited_id INTEGER, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, name TEXT, url TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS custom_films (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE, title TEXT, year TEXT,
        description TEXT, poster TEXT,
        watch_url TEXT, added_at TEXT)""")
    # Миграция: колонка для видео из канала
    try:
        c.execute("ALTER TABLE custom_films ADD COLUMN channel_message_id INTEGER")
    except sqlite3.OperationalError:
        pass  # колонка уже есть
    # Дефолтный канал
    if c.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 0:
        c.execute("INSERT OR IGNORE INTO channels (username, name, url) VALUES (?, ?, ?)",
                  ("-1001199192573", "FILMIX", "https://t.me/+-BKXmo8rQr8xMjgy"))
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, invited_by=None):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not existing:
        c.execute("INSERT INTO users (user_id, username, first_name, joined_at, last_active, invited_by, lang) VALUES (?, ?, ?, ?, ?, ?, 'ru')",
                  (user_id, username, first_name, now, now, invited_by))
        if invited_by:
            c.execute("INSERT INTO referrals (inviter_id, invited_id, created_at) VALUES (?, ?, ?)", (invited_by, user_id, now))
            bonus = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
            c.execute("UPDATE users SET bonus_until=? WHERE user_id=?", (bonus, invited_by))
    else:
        c.execute("UPDATE users SET last_active=?, requests_count=requests_count+1 WHERE user_id=?", (now, user_id))
    conn.commit()
    conn.close()

def set_lang(user_id, lang):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    c.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()

def get_lang(user_id):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    row = c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else "ru"

def get_stats():
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_active = c.execute("SELECT COUNT(*) FROM users WHERE last_active LIKE ?", (f"{today}%",)).fetchone()[0]
    total_requests = c.execute("SELECT SUM(requests_count) FROM users").fetchone()[0] or 0
    total_referrals = c.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
    conn.close()
    return total, today_active, total_requests, total_referrals

def has_bonus(user_id):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    row = c.execute("SELECT bonus_until FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if row and row[0]:
        try:
            return datetime.now() < datetime.strptime(row[0], "%Y-%m-%d %H:%M")
        except:
            return False
    return False

def get_referral_count(user_id):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (user_id,)).fetchone()[0]
    conn.close()
    return count

def is_favorited(user_id, movie_id):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    row = c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id)).fetchone()
    conn.close()
    return row is not None

def add_favorite(user_id, movie_id, title, year, rating, poster):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    if c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id)).fetchone():
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO favorites (user_id, movie_id, title, year, rating, poster, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (user_id, movie_id, title, year, rating, poster, now))
    conn.commit()
    conn.close()
    return True

def remove_favorite(user_id, movie_id):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    c.execute("DELETE FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id))
    conn.commit()
    conn.close()

def get_favorites(user_id):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    rows = c.execute("SELECT movie_id, title, year, rating, poster FROM favorites WHERE user_id=? ORDER BY added_at DESC", (user_id,)).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "release_date": r[2], "vote_average": r[3], "poster_path": r[4]} for r in rows]

def get_all_users():
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    rows = c.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]

# ===== СВОЯ БАЗА ФИЛЬМОВ =====
def add_custom_film(code, title, year, description, poster, watch_url):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        c.execute("INSERT OR REPLACE INTO custom_films (code, title, year, description, poster, watch_url, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (str(code), title, year, description, poster, watch_url, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

def get_custom_film(code):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    row = c.execute("SELECT code, title, year, description, poster, watch_url, channel_message_id FROM custom_films WHERE code=?", (str(code),)).fetchone()
    conn.close()
    if row:
        return {"code": row[0], "title": row[1], "year": row[2], "description": row[3], "poster": row[4], "watch_url": row[5], "channel_message_id": row[6]}
    return None

def set_film_video(code, channel_message_id):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    c.execute("UPDATE custom_films SET channel_message_id=? WHERE code=?", (channel_message_id, str(code)))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def delete_custom_film(code):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    c.execute("DELETE FROM custom_films WHERE code=?", (str(code),))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_all_custom_films():
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    rows = c.execute("SELECT code, title, year, watch_url FROM custom_films ORDER BY added_at DESC").fetchall()
    conn.close()
    return rows

def search_custom_films(query):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    rows = c.execute("SELECT code, title, year, description, poster, watch_url FROM custom_films WHERE title LIKE ?",
                     (f"%{query}%",)).fetchall()
    conn.close()
    return [{"code": r[0], "title": r[1], "year": r[2], "description": r[3], "poster": r[4], "watch_url": r[5]} for r in rows]

# ===== КАНАЛЫ =====
def get_channels():
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    rows = c.execute("SELECT username, name, url FROM channels").fetchall()
    conn.close()
    return [{"username": r[0], "name": r[1], "url": r[2]} for r in rows]

def db_add_channel(username, name, url):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO channels (username, name, url) VALUES (?, ?, ?)", (username, name, url))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def db_remove_channel(username):
    conn = sqlite3.connect("filmix.db")
    c = conn.cursor()
    c.execute("DELETE FROM channels WHERE username=?", (username,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

async def check_sub(user_id):
    if has_bonus(user_id) or user_id in ADMIN_IDS:
        return []
    not_subbed = []
    channels = get_channels()
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["username"], user_id)
            if member.status in ["left", "kicked", "banned"]:
                not_subbed.append(ch)
        except:
            not_subbed.append(ch)
    return not_subbed

# ===== AI =====
async def translate_to_uz(text):
    if not text or len(text) < 10:
        return text
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 500,
                      "messages": [{"role": "user", "content": f"Translate to Uzbek. Reply ONLY with translation:\n\n{text}"}]},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
                if "content" in data:
                    return data["content"][0]["text"].strip()
                return text
    except:
        return text

async def ai_find_movie(description):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200,
                      "messages": [{"role": "user", "content": f"What movie/show is described? Description: {description}. Reply ONLY with English title. If multiple options, separate with commas. If unknown: unknown"}]},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                if "content" in data:
                    return data["content"][0]["text"].strip().strip('"')
                return "unknown"
    except:
        return "unknown"

async def ai_recommend(query):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200,
                      "messages": [{"role": "user", "content": f"Recommend 5 movies/shows for: {query}. Reply ONLY with English titles separated by commas."}]},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                if "content" in data:
                    result = data["content"][0]["text"].strip()
                    return [t.strip() for t in result.split(",") if t.strip()][:5]
                return []
    except:
        return []

async def search_by_title(title):
    results = []
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": title, "language": "ru-RU"}) as r:
            data = await r.json()
        results.extend(data.get("results", [])[:2])
        async with session.get(f"{TMDB_URL}/search/tv",
            params={"api_key": TMDB_API_KEY, "query": title, "language": "ru-RU"}) as r:
            data = await r.json()
        for item in data.get("results", [])[:1]:
            item["title"] = item.get("name", "—")
            item["release_date"] = item.get("first_air_date", "")
            item["is_tv"] = True
        results.extend(data.get("results", [])[:1])
    return results

# ===== КАРТОЧКИ =====
def movie_card_text(m, index, total, user_id):
    title = m.get("title", "—")
    year = (m.get("release_date", "") or "")[:4]
    rating = round(m.get("vote_average", 0) or 0, 1)
    overview = (m.get("overview", "") or tr(user_id, "no_desc"))[:200]
    movie_id = m.get("id")
    media_type = "📺" if m.get("is_tv") else "🎬"
    return (
        f"{media_type} *{title}* ({year})\n"
        f"{tr(user_id, 'rating', rating)}\n"
        f"🆔 `{movie_id}`\n\n"
        f"📝 {overview}...\n\n"
        f"_{index}/{total}_"
    )

def movie_card_keyboard(movies, index, source, user_id):
    m = movies[index]
    movie_id = m.get("id")
    total = len(movies)
    q = urllib.parse.quote(m.get("title", ""))
    fav = is_favorited(user_id, movie_id)
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"card:{source}:{index-1}"))
    nav.append(InlineKeyboardButton(text=f"{index+1}/{total}", callback_data="noop"))
    if index < total - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"card:{source}:{index+1}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [
            InlineKeyboardButton(text=tr(user_id, "open_film"), callback_data=f"film:{movie_id}"),
            InlineKeyboardButton(text=tr(user_id, "unfav_btn" if fav else "fav_btn"), callback_data=f"fav:{movie_id}")
        ],
        [
            InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
            InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}")
        ]
    ])

async def send_card(message, movies, index, source, edit=False, user_id=None):
    m = movies[index]
    poster = m.get("poster_path", "")
    text = movie_card_text(m, index + 1, len(movies), user_id)
    kb = movie_card_keyboard(movies, index, source, user_id)
    if poster:
        url = f"https://image.tmdb.org/t/p/w500{poster}"
        if edit:
            try:
                await message.edit_media(types.InputMediaPhoto(media=url, caption=text, parse_mode="Markdown"), reply_markup=kb)
            except:
                await message.answer_photo(url, caption=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await message.answer_photo(url, caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        if edit:
            await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await message.answer(text, parse_mode="Markdown", reply_markup=kb)

# ===== УТРЕННЯЯ РАССЫЛКА =====
async def morning_broadcast():
    while True:
        now = datetime.now()
        # Случайное время в диапазоне 4:00–10:00 каждый день
        rand_hour = random.randint(4, 9)
        rand_minute = random.randint(0, 59)
        next_run = now.replace(hour=rand_hour, minute=rand_minute, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
            rand_hour = random.randint(4, 9)
            rand_minute = random.randint(0, 59)
            next_run = next_run.replace(hour=rand_hour, minute=rand_minute)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TMDB_URL}/movie/popular",
                    params={"api_key": TMDB_API_KEY, "language": "ru-RU", "page": random.randint(1,5)}) as r:
                    data = await r.json()
            movies = data.get("results", [])
            if not movies:
                continue
            movie = random.choice(movies)
            title = movie.get("title", "—")
            year = (movie.get("release_date", "") or "")[:4]
            rating = round(movie.get("vote_average", 0) or 0, 1)
            overview = (movie.get("overview", "") or "")[:200]
            movie_id = movie.get("id")
            poster = movie.get("poster_path", "")
            for uid in get_all_users():
                try:
                    msg = tr(uid, "morning_msg", title, year, rating, overview, movie_id)
                    kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text=tr(uid, "open_film"), callback_data=f"film:{movie_id}")
                    ]])
                    if poster:
                        await bot.send_photo(uid, f"https://image.tmdb.org/t/p/w500{poster}", caption=msg, parse_mode="Markdown", reply_markup=kb)
                    else:
                        await bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=kb)
                    await asyncio.sleep(0.05)
                except:
                    pass
        except Exception as e:
            print(f"Morning broadcast error: {e}")

# ===== КОМАНДЫ =====
@dp.message(Command("start"))
async def start(message: types.Message):
    args = message.text.split()
    invited_by = None
    if len(args) > 1 and args[1].isdigit():
        invited_by = int(args[1])
        if invited_by == message.from_user.id:
            invited_by = None
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name, invited_by)
    if invited_by:
        try:
            await bot.send_message(invited_by, tr(invited_by, "new_user", get_referral_count(invited_by)), parse_mode="Markdown")
        except:
            pass
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz")
    ]])
    await message.answer(tr(message.from_user.id, "choose_lang"), reply_markup=kb)

@dp.message(Command("lang"))
async def lang_cmd(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz")
    ]])
    await message.answer(tr(message.from_user.id, "choose_lang"), reply_markup=kb)

@dp.message(Command("stats"))
async def stats(message: types.Message):
    total, today, requests, referrals = get_stats()
    ref = get_referral_count(message.from_user.id)
    await message.answer(tr(message.from_user.id, "stats", total, today, requests, referrals, ref), parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(tr(message.from_user.id, "no_access")); return
    total, today, requests, referrals = get_stats()
    await message.answer(
        f"👑 *Админ панель FILMIX*\n\n"
        f"👥 Пользователей: *{total}*\n🔥 Сегодня: *{today}*\n"
        f"🔍 Запросов: *{requests}*\n🔗 Рефералов: *{referrals}*\n\n"
        f"📤 `/post ID` — постинг в канал\n"
        f"📢 `/broadcast текст` — рассылка\n\n"
        f"🎬 *Своя база фильмов:*\n"
        f"➕ `/addfilm КОД | Название | Год | Описание | Постер | Ссылка`\n"
        f"➖ `/deletefilm КОД` — удалить фильм\n"
        f"🎥 `/addvideo КОД MESSAGE_ID` — привязать видео из канала\n"
        f"📋 `/myfilms` — список фильмов\n\n"
        f"📋 `/channels` — каналы\n"
        f"➕ `/addchannel @ch Название`\n"
        f"➖ `/removechannel @ch`",
        parse_mode="Markdown"
    )

@dp.message(Command("channels"))
async def list_channels(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(tr(message.from_user.id, "no_access")); return
    channels = get_channels()
    if not channels:
        await message.answer("📋 Каналов нет."); return
    text = "📋 *Каналы для проверки подписки:*\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. *{ch['name']}*\n`{ch['username']}`\n\n"
    text += "➕ `/addchannel @username Название`\n➖ `/removechannel @username`"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("addchannel"))
async def add_channel_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(tr(message.from_user.id, "no_access")); return
    args = message.text.replace("/addchannel", "").strip().split()
    if len(args) < 2:
        await message.answer("❌ Используй:\n`/addchannel @username Название`", parse_mode="Markdown"); return
    username = args[0]
    name = " ".join(args[1:])
    url = f"https://t.me/{username[1:]}" if username.startswith("@") else f"https://t.me/joinchat/{username}"
    if db_add_channel(username, name, url):
        await message.answer(f"✅ Канал *{name}* добавлен!", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Канал `{username}` уже существует.", parse_mode="Markdown")

@dp.message(Command("removechannel"))
async def remove_channel_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(tr(message.from_user.id, "no_access")); return
    username = message.text.replace("/removechannel", "").strip()
    if not username:
        await message.answer("❌ Используй: `/removechannel @username`", parse_mode="Markdown"); return
    if db_remove_channel(username):
        await message.answer(f"✅ Канал `{username}` удалён!", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Канал `{username}` не найден.", parse_mode="Markdown")

@dp.message(Command("addfilm"))
async def addfilm_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Нет доступа."); return
    # Формат: /addfilm КОД | Название | Год | Описание | Постер URL | Ссылка
    text = message.text.replace("/addfilm", "").strip()
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 4:
        await message.answer(
            "❌ Формат:\n`/addfilm КОД | Название | Год | Описание | Постер_URL | Ссылка`\n\n"
            "Пример:\n`/addfilm 12345 | Оппенгеймер | 2023 | Описание | https://poster.jpg | https://rezka.ag/...`\n\n"
            "Постер и ссылка необязательны.",
            parse_mode="Markdown"
        ); return
    code = parts[0]
    title = parts[1]
    year = parts[2] if len(parts) > 2 else ""
    description = parts[3] if len(parts) > 3 else ""
    poster = parts[4] if len(parts) > 4 else ""
    watch_url = parts[5] if len(parts) > 5 else ""
    if add_custom_film(code, title, year, description, poster, watch_url):
        text = f"✅ Фильм добавлен!\n\n🎬 *{title}* ({year})\n🆔 Код: `{code}`"
        if watch_url:
            text += f"\n🔗 Ссылка: {watch_url}"
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer(f"❌ Ошибка добавления.")

@dp.message(Command("deletefilm"))
async def deletefilm_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Нет доступа."); return
    code = message.text.replace("/deletefilm", "").strip()
    if not code:
        await message.answer("❌ Используй: `/deletefilm КОД`", parse_mode="Markdown"); return
    if delete_custom_film(code):
        await message.answer(f"✅ Фильм с кодом `{code}` удалён!", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Фильм с кодом `{code}` не найден.", parse_mode="Markdown")

@dp.message(Command("addvideo"))
async def addvideo_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Нет доступа."); return
    args = message.text.split()
    if len(args) != 3 or not args[2].lstrip("-").isdigit():
        await message.answer(
            "❌ Используй: `/addvideo КОД MESSAGE_ID`\n\n"
            "Чтобы узнать MESSAGE_ID, перешли видео из канала прямо боту — "
            "он подскажет команду сам.",
            parse_mode="Markdown"
        ); return
    code, msg_id = args[1], int(args[2])
    if set_film_video(code, msg_id):
        await message.answer(f"✅ Видео привязано к коду `{code}`!", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Фильм с кодом `{code}` не найден. Сначала добавь через /addfilm.")

@dp.message(lambda m: m.video is not None and (m.forward_origin is not None or m.forward_from_chat is not None))
async def forwarded_video_handler(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    msg_id = None
    if message.forward_origin and hasattr(message.forward_origin, "message_id"):
        msg_id = message.forward_origin.message_id
    elif message.forward_from_message_id:
        msg_id = message.forward_from_message_id
    if not msg_id:
        await message.answer("❌ Не удалось определить message_id. Узнай его вручную (пересланное сообщение → ссылка на пост).")
        return
    await message.answer(
        f"📹 message_id этого видео: `{msg_id}`\n\n"
        f"Привяжи к коду: `/addvideo КОД {msg_id}`",
        parse_mode="Markdown"
    )

@dp.message(Command("myfilms"))
async def myfilms_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Нет доступа."); return
    films = get_all_custom_films()
    if not films:
        await message.answer("📋 Своих фильмов нет.\n\nДобавь через `/addfilm`", parse_mode="Markdown"); return
    text = f"📋 *Своя база фильмов ({len(films)} шт):*\n\n"
    for code, title, year, url in films[:20]:
        text += f"• `{code}` — *{title}* ({year})\n"
    if len(films) > 20:
        text += f"\n_...и ещё {len(films)-20} фильмов_"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("post"))
async def post_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(tr(message.from_user.id, "no_access")); return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❌ Используй: `/post 872585`", parse_mode="Markdown"); return
    movie_id = int(args[1])
    await message.answer(tr(message.from_user.id, "posting"))
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            m = await r.json()
    if not m.get("title"):
        await message.answer(tr(message.from_user.id, "post_error")); return
    title = m.get("title", "—")
    year = (m.get("release_date", "") or "")[:4]
    rating = round(m.get("vote_average", 0) or 0, 1)
    overview = m.get("overview", "") or ""
    poster = m.get("poster_path", "")
    await post_to_channels(movie_id, title, year, rating, overview, poster)
    await message.answer(tr(message.from_user.id, "posted", title), parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(tr(message.from_user.id, "no_access")); return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer(tr(message.from_user.id, "broadcast_usage"), parse_mode="Markdown"); return
    users = get_all_users()
    sent = 0
    failed = 0
    status = await message.answer(tr(message.from_user.id, "broadcast_sending", len(users)))
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 *FILMIX:*\n\n{text}", parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await status.edit_text(tr(message.from_user.id, "broadcast_done", sent, failed), parse_mode="Markdown")

# ===== KEYWORDS =====
RECOMMEND_KW = ["посоветуй", "порекомендуй", "что посмотреть", "хочу посмотреть", "рекомендуй", "подбери", "подскажи", "tavsiya", "maslahat", "ko'rmoqchi", "tavsiya qil"]

def is_recommend(text):
    return any(kw in text.lower() for kw in RECOMMEND_KW)

# ===== ГЛАВНЫЙ ОБРАБОТЧИК =====
@dp.message()
async def handle(message: types.Message):
    if not message.text:
        return
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = message.text.strip()
    user_id = message.from_user.id
    lang = get_lang(user_id)
    tx = TEXTS[lang]

    # Меню кнопки
    if text in [tx["top"], "🔥 Топ фильмов", "🔥 Top filmlar"]:
        await show_top(message); return
    if text in [tx["new"], "🆕 Новинки", "🆕 Yangiliklar"]:
        await show_new(message); return
    if text in [tx["upcoming"], "🎬 Скоро в кино", "🎬 Tez chiqadi"]:
        await show_upcoming(message); return
    if text in [tx["uzbek"], "🇺🇿 Узбек кино", "🇺🇿 O'zbek kino"]:
        await show_uzbek(message); return
    if text in [tx["tv_shows"], "📺 Сериалы", "📺 Seriallar"]:
        await show_tv(message); return
    if text in [tx["favorites"], "❤️ Избранное", "❤️ Sevimlilar"]:
        await show_favorites(message); return
    if text in [tx["quiz"], "🎮 Квиз", "🎮 Viktorina"]:
        await start_quiz(message); return
    if text in [tx["recommend"], "🎯 Подобрать", "🎯 Tavsiya"]:
        await message.answer(tr(user_id, "recommend_prompt"), parse_mode="Markdown"); return
    if text in [tx["invite"], "👥 Пригласить", "👥 Taklif qilish"]:
        await show_invite(message); return

    # Проверка подписки
    not_subbed = await check_sub(user_id)
    if not_subbed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
        ] + [[InlineKeyboardButton(text=tr(user_id, "check_sub"), callback_data=f"check_only:{user_id}")]])
        await message.answer(tr(user_id, "resubscribe"), reply_markup=kb, parse_mode="Markdown")
        return

    # Сначала проверяем свою базу
    if text.isdigit() or (len(text) < 20 and not text.startswith("/")):
        custom = get_custom_film(text)
        if custom:
            await show_custom_film(message, custom)
            return

    # ID фильма из TMDb
    if text.isdigit():
        await show_film(message, int(text))
        return

    # Рекомендации AI
    if is_recommend(text):
        thinking = await message.answer(tr(user_id, "ai_recommending"))
        titles = await ai_recommend(text)
        if not titles:
            await thinking.edit_text(tr(user_id, "ai_not_found")); return
        all_movies = []
        for t in titles:
            all_movies.extend(await search_by_title(t))
        seen = set()
        unique = [m for m in all_movies if not (m["id"] in seen or seen.add(m["id"]))]
        if not unique:
            await thinking.edit_text(tr(user_id, "ai_not_found")); return
        await thinking.edit_text(tr(user_id, "ai_recommend_result"), parse_mode="Markdown")
        search_cache[f"{user_id}_rec"] = unique[:5]
        await send_card(message, unique[:5], 0, f"{user_id}_rec", user_id=user_id)
        return

    # AI поиск по описанию (длинный текст)
    if len(text) > 20:
        thinking = await message.answer(tr(user_id, "ai_searching"))
        movie_title = await ai_find_movie(text)
        if movie_title.lower() == "unknown":
            await thinking.edit_text(tr(user_id, "ai_not_found")); return
        titles = [t.strip() for t in movie_title.split(",")]
        all_movies = []
        for t in titles[:3]:
            all_movies.extend(await search_by_title(t))
        seen = set()
        unique = [m for m in all_movies if not (m["id"] in seen or seen.add(m["id"]))]
        if not unique:
            await thinking.edit_text(tr(user_id, "ai_no_result", titles[0]), parse_mode="Markdown"); return
        await thinking.edit_text(tr(user_id, "ai_found", titles[0]), parse_mode="Markdown")
        search_cache[f"{user_id}_search"] = unique[:5]
        await send_card(message, unique[:5], 0, f"{user_id}_search", user_id=user_id)
        return

    # Поиск в своей базе по названию
    custom_results = search_custom_films(text)
    if custom_results:
        await show_custom_film(message, custom_results[0])
        return

    # Поиск по названию или актёру в TMDb
    movies = await search_by_title(text)
    if movies:
        search_cache[f"{user_id}_search"] = movies
        await send_card(message, movies, 0, f"{user_id}_search", user_id=user_id)
    else:
        await search_person(message, text)

# ===== WEB APP =====
@dp.message(lambda m: m.web_app_data is not None)
async def web_app_handler(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.first_name)
    data = message.web_app_data.data.strip()

    custom = get_custom_film(data)
    if custom:
        await show_custom_film(message, custom)
        return

    if data.isdigit():
        not_subbed = await check_sub(user_id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text=tr(user_id, "check_sub"), callback_data=f"check:{data}")]])
            await message.answer(tr(user_id, "subscribe"), reply_markup=kb)
        else:
            await show_film(message, int(data))

# ===== РАЗДЕЛЫ =====
async def show_top(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/popular", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    search_cache[f"{user_id}_top"] = movies
    await send_card(message, movies, 0, f"{user_id}_top", user_id=user_id)

async def show_new(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/now_playing", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    search_cache[f"{user_id}_new"] = movies
    await send_card(message, movies, 0, f"{user_id}_new", user_id=user_id)

async def show_upcoming(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/upcoming", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    search_cache[f"{user_id}_upcoming"] = movies
    await send_card(message, movies, 0, f"{user_id}_upcoming", user_id=user_id)

async def show_uzbek(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/discover/movie",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU", "with_origin_country": "UZ", "sort_by": "popularity.desc"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    if not movies:
        movies = (await search_by_title("uzbek film"))[:10]
    search_cache[f"{user_id}_uzbek"] = movies
    await message.answer(tr(user_id, "uzbek_films"), parse_mode="Markdown")
    if movies:
        await send_card(message, movies, 0, f"{user_id}_uzbek", user_id=user_id)

async def show_tv(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/tv/popular", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    shows = data.get("results", [])[:10]
    for s in shows:
        s["title"] = s.get("name", "—")
        s["release_date"] = s.get("first_air_date", "")
        s["is_tv"] = True
    search_cache[f"{user_id}_tv"] = shows
    await message.answer(tr(user_id, "tv_top"), parse_mode="Markdown")
    await send_card(message, shows, 0, f"{user_id}_tv", user_id=user_id)

async def show_favorites(message):
    user_id = message.from_user.id
    favs = get_favorites(user_id)
    if not favs:
        await message.answer(tr(user_id, "no_favorites")); return
    search_cache[f"{user_id}_fav"] = favs
    await send_card(message, favs, 0, f"{user_id}_fav", user_id=user_id)

async def show_invite(message):
    user_id = message.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    await message.answer(tr(user_id, "invite_text", link, get_referral_count(user_id)), parse_mode="Markdown")

async def start_quiz(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/popular", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = [m for m in data.get("results", []) if m.get("overview")]
    if not movies: return
    movie = random.choice(movies)
    title = movie.get("title", "—")
    overview = (movie.get("overview", "") or "")[:300]
    movie_id = movie.get("id")
    if lang == "uz":
        overview = await translate_to_uz(overview)
    wrong = random.sample([m.get("title") for m in movies if m.get("title") != title], min(3, len(movies)-1))
    options = wrong + [title]
    random.shuffle(options)
    search_cache[f"quiz_{user_id}"] = {"answer": title, "movie_id": movie_id}
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=opt, callback_data=f"quiz:{opt}")] for opt in options])
    await message.answer(tr(user_id, "quiz_title", overview), parse_mode="Markdown", reply_markup=kb)

async def search_person(message, query):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/search/person", params={"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU"}) as r:
            data = await r.json()
    results = data.get("results", [])
    if not results:
        await message.answer(tr(user_id, "not_found"), parse_mode="Markdown"); return
    person = results[0]
    person_id = person["id"]
    name = person.get("name", "—")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/person/{person_id}/movie_credits", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            credits = await r.json()
    movies = sorted(credits.get("cast", []), key=lambda x: x.get("popularity", 0), reverse=True)[:8]
    search_cache[f"{user_id}_person"] = movies
    await message.answer(tr(user_id, "actor_movies", name), parse_mode="Markdown")
    if movies:
        await send_card(message, movies, 0, f"{user_id}_person", user_id=user_id)

async def post_to_channels(movie_id, title, year, rating, overview, poster):
    channels = get_channels()
    q = urllib.parse.quote(title)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Получить в боте", url=f"https://t.me/{BOT_USERNAME}?start={movie_id}")],
        [
            InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
            InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}")
        ]
    ])
    text = f"🎬 *{title}* ({year})\n\n⭐ Рейтинг: {rating}/10\n\n📝 {overview}\n\n🆔 Код: `{movie_id}`"
    for ch in channels:
        try:
            if poster:
                await bot.send_photo(ch["username"], f"https://image.tmdb.org/t/p/w500{poster}", caption=text, parse_mode="Markdown", reply_markup=kb)
            else:
                await bot.send_message(ch["username"], text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            print(f"Post error to {ch['username']}: {e}")

async def show_custom_film(message, film):
    user_id = message.from_user.id if hasattr(message, "from_user") and message.from_user else ADMIN_IDS[0]
    code = film["code"]
    title = film["title"]
    year = film["year"]
    description = film["description"] or tr(user_id, "no_desc")
    poster = film["poster"]
    watch_url = film["watch_url"]
    channel_message_id = film.get("channel_message_id")

    fav = is_favorited(user_id, int(code) if code.isdigit() else 0)
    buttons = []
    if channel_message_id:
        buttons.append([InlineKeyboardButton(text="▶️ Смотреть видео", callback_data=f"getvideo:{code}")])
    elif watch_url:
        buttons.append([InlineKeyboardButton(text="▶️ Смотреть", url=watch_url)])
    buttons.append([
        InlineKeyboardButton(text=tr(user_id, "unfav_btn" if fav else "fav_btn"),
                             callback_data=f"fav:{code}")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = f"🎬 *{title}* ({year})\n\n📝 {description}\n\n🆔 Код: `{code}`"

    if poster:
        try:
            await message.answer_photo(poster, caption=text, parse_mode="Markdown", reply_markup=kb)
            return
        except:
            pass
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

# ===== ПОКАЗ КАРТОЧКИ ФИЛЬМА/СЕРИАЛА =====
async def render_film_card(message, m, movie_id, is_tv):
    """Рисует карточку одного найденного фильма/сериала (когда тип уже определён)."""
    user_id = message.from_user.id if hasattr(message, 'from_user') and message.from_user else ADMIN_IDS[0]
    lang = get_lang(user_id)
    title = m.get("title", "—")
    year = (m.get("release_date", "") or "")[:4]
    rating = round(m.get("vote_average", 0) or 0, 1)
    overview = m.get("overview", "") or ""
    poster = m.get("poster_path", "")
    q = urllib.parse.quote(title)

    if lang == "uz" and overview:
        overview = await translate_to_uz(overview)
    if not overview:
        overview = tr(user_id, "no_desc")

    media_type = "📺 Сериал" if is_tv else "🎬 Фильм"
    fav = is_favorited(user_id, movie_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=tr(user_id, "similar"), callback_data=f"sim:{movie_id}"),
            InlineKeyboardButton(text=tr(user_id, "actors"), callback_data=f"cast:{movie_id}")
        ],
        [InlineKeyboardButton(text=tr(user_id, "unfav_btn" if fav else "fav_btn"), callback_data=f"fav:{movie_id}")],
        [
            InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
            InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}")
        ]
    ])
    text = f"{media_type}\n🎬 *{title}* ({year})\n\n{tr(user_id, 'rating', rating)}\n\n📝 {overview}"
    if poster:
        await message.answer_photo(f"https://image.tmdb.org/t/p/w500{poster}", caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def show_film(message, movie_id):
    """
    Проверяет ОДНОВРЕМЕННО movie и tv с этим ID.
    Если найдено и там, и там — предлагает пользователю выбрать нужный вариант.
    Если найден только один вариант — сразу показывает его.
    """
    user_id = message.from_user.id if hasattr(message, 'from_user') and message.from_user else ADMIN_IDS[0]

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            movie_data = await r.json()
        async with session.get(f"{TMDB_URL}/tv/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            tv_data = await r.json()

    has_movie = bool(movie_data.get("title"))
    has_tv = bool(tv_data.get("name"))

    if has_movie and has_tv:
        movie_title = movie_data.get("title", "—")
        movie_year = (movie_data.get("release_date", "") or "")[:4]
        tv_title = tv_data.get("name", "—")
        tv_year = (tv_data.get("first_air_date", "") or "")[:4]
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"🎬 {movie_title} ({movie_year})", callback_data=f"pick:movie:{movie_id}"),
            InlineKeyboardButton(text=f"📺 {tv_title} ({tv_year})", callback_data=f"pick:tv:{movie_id}")
        ]])
        await message.answer(
            tr(user_id, "pick_prompt", movie_id),
            parse_mode="Markdown", reply_markup=kb
        )
        return

    if has_movie:
        await render_film_card(message, movie_data, movie_id, is_tv=False)
    elif has_tv:
        tv_data["title"] = tv_data.get("name", "—")
        tv_data["release_date"] = tv_data.get("first_air_date", "")
        await render_film_card(message, tv_data, movie_id, is_tv=True)
    else:
        await message.answer(tr(user_id, "film_not_found"))

# ===== CALLBACKS =====
@dp.callback_query(lambda c: c.data.startswith("pick:"))
async def pick_callback(callback: types.CallbackQuery):
    _, kind, movie_id_str = callback.data.split(":")
    movie_id = int(movie_id_str)
    endpoint = "tv" if kind == "tv" else "movie"
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/{endpoint}/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            m = await r.json()
    is_tv = kind == "tv"
    if is_tv:
        m["title"] = m.get("name", "—")
        m["release_date"] = m.get("first_air_date", "")
    try:
        await callback.message.delete()
    except:
        pass
    await render_film_card(callback.message, m, movie_id, is_tv=is_tv)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("lang:"))
async def lang_callback(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    set_lang(user_id, lang)
    try:
        await callback.message.delete()
    except:
        pass
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎬 Открыть FILMIX App" if lang == "ru" else "🎬 FILMIX App ni ochish",
            web_app=types.WebAppInfo(url=MINI_APP_URL))
    ]])
    await callback.message.answer(tr(user_id, "welcome"), reply_markup=get_menu(user_id), parse_mode="Markdown")
    await callback.message.answer(tr(user_id, "choose_section"), reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check_only:"))
async def check_only(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    not_subbed = await check_sub(user_id)
    if not_subbed:
        await callback.answer(tr(user_id, "not_subscribed"), show_alert=True)
    else:
        await callback.message.delete()
        await callback.message.answer(tr(user_id, "welcome"), reply_markup=get_menu(user_id), parse_mode="Markdown")
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("quiz:"))
async def quiz_answer(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    answer = callback.data.replace("quiz:", "")
    quiz_data = search_cache.get(f"quiz_{user_id}")
    if not quiz_data:
        await callback.answer(tr(user_id, "quiz_expired"), show_alert=True); return
    correct = quiz_data["answer"]
    if answer == correct:
        await callback.answer(tr(user_id, "quiz_correct"), show_alert=True)
        await callback.message.edit_reply_markup()
        not_subbed = await check_sub(user_id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text=tr(user_id, "check_sub"), callback_data=f"check:{quiz_data['movie_id']}")]])
            await callback.message.answer(tr(user_id, "subscribe"), reply_markup=kb)
        else:
            await show_film(callback.message, quiz_data["movie_id"])
    else:
        await callback.answer(tr(user_id, "quiz_wrong", correct), show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("getvideo:"))
async def getvideo_callback(callback: types.CallbackQuery):
    code = callback.data.split(":", 1)[1]
    film = get_custom_film(code)
    if not film or not film.get("channel_message_id"):
        await callback.answer("❌ Видео не найдено.", show_alert=True)
        return
    if not VIDEO_CHANNEL_ID:
        await callback.answer("❌ VIDEO_CHANNEL_ID не настроен на сервере.", show_alert=True)
        return
    try:
        await bot.copy_message(
            chat_id=callback.from_user.id,
            from_chat_id=VIDEO_CHANNEL_ID,
            message_id=film["channel_message_id"]
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Не удалось отправить видео. Проверь права бота в канале.", show_alert=True)
        print(f"getvideo error: {e}")

@dp.callback_query(lambda c: c.data.startswith("fav:"))
async def fav_callback(callback: types.CallbackQuery):
    movie_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    if is_favorited(user_id, movie_id):
        remove_favorite(user_id, movie_id)
        await callback.answer(tr(user_id, "removed_fav"))
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TMDB_URL}/movie/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
                m = await r.json()
        if not m.get("title"):
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TMDB_URL}/tv/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
                    m = await r.json()
            m["title"] = m.get("name", "—")
            m["release_date"] = m.get("first_air_date", "")
        add_favorite(user_id, movie_id, m.get("title","—"), (m.get("release_date","") or "")[:4], round(m.get("vote_average",0) or 0,1), m.get("poster_path",""))
        await callback.answer(tr(user_id, "added_fav"))

@dp.callback_query(lambda c: c.data.startswith("card:"))
async def card_nav(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    index = int(parts[2])
    movies = search_cache.get(source)
    if not movies:
        await callback.answer(tr(callback.from_user.id, "session_expired"), show_alert=True); return
    await send_card(callback.message, movies, index, source, edit=True, user_id=callback.from_user.id)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("film:"))
async def film_callback(callback: types.CallbackQuery):
    movie_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    not_subbed = await check_sub(user_id)
    if not_subbed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
        ] + [[InlineKeyboardButton(text=tr(user_id, "check_sub"), callback_data=f"check:{movie_id}")]])
        await callback.message.answer(tr(user_id, "subscribe"), reply_markup=kb)
    else:
        await show_film(callback.message, movie_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check:"))
async def check_callback(callback: types.CallbackQuery):
    movie_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    not_subbed = await check_sub(user_id)
    if not_subbed:
        await callback.answer(tr(user_id, "not_subscribed"), show_alert=True)
    else:
        await callback.message.delete()
        await show_film(callback.message, int(movie_id))
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("sim:"))
async def similar(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    movie_id = callback.data.split(":")[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}/similar", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    results = data.get("results", [])[:5]
    if not results:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TMDB_URL}/tv/{movie_id}/similar", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
                data = await r.json()
        results = data.get("results", [])[:5]
        for r in results:
            r["title"] = r.get("name", "—")
            r["release_date"] = r.get("first_air_date", "")
            r["is_tv"] = True
    if not results:
        await callback.answer(tr(user_id, "no_similar"), show_alert=True); return
    search_cache[f"{user_id}_sim"] = results
    await send_card(callback.message, results, 0, f"{user_id}_sim", user_id=user_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cast:"))
async def cast(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    movie_id = callback.data.split(":")[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}/credits", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    actors = data.get("cast", [])[:6]
    if not actors:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TMDB_URL}/tv/{movie_id}/credits", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
                data = await r.json()
        actors = data.get("cast", [])[:6]
    if not actors:
        await callback.answer(tr(user_id, "no_actors"), show_alert=True); return
    text = tr(user_id, "actors_title")
    buttons = []
    for a in actors:
        name = a.get("name", "—")
        character = a.get("character", "—")
        person_id = a.get("id")
        text += f"• *{name}* — {character}\n"
        buttons.append([InlineKeyboardButton(text=f"🎭 {name}", callback_data=f"person:{person_id}")])
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("person:"))
async def person_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    person_id = callback.data.split(":")[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/person/{person_id}/movie_credits", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            credits = await r.json()
        async with session.get(f"{TMDB_URL}/person/{person_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            person = await r.json()
    name = person.get("name", "—")
    movies = sorted(credits.get("cast", []), key=lambda x: x.get("popularity", 0), reverse=True)[:8]
    search_cache[f"{user_id}_person"] = movies
    await callback.message.answer(tr(user_id, "actor_movies", name), parse_mode="Markdown")
    if movies:
        await send_card(callback.message, movies, 0, f"{user_id}_person", user_id=user_id)
    await callback.answer()

async def main():
    init_db()
    asyncio.create_task(morning_broadcast())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

