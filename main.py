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
CHANNEL = "@thebobodjonov"
ADMIN_ID = 6250747288
BOT_USERNAME = "CINEMATR1X_BOT"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

CHANNELS = [
    {"name": "Бободжонов", "username": "@thebobodjonov", "url": "https://t.me/thebobodjonov"},
]

TEXTS = {
    "ru": {
        "welcome": "🎬 Добро пожаловать в CINEMATRIX!\n\n📌 Как пользоваться:\n🔢 *ID фильма* — например: `572802`\n🔤 *Название* — например: `Интерстеллар`\n🎭 *Актёр* — например: `Tom Hanks`\n🤖 *Опиши сцену* — например: `фильм где человек застрял на острове`\n🎯 *Попроси совет* — например: `посоветуй фильм про зомби`\n\nИспользуй кнопки внизу 👇",
        "choose_section": "Выбери раздел:",
        "subscribe": "📢 Подпишись на канал и нажми кнопку!",
        "check_sub": "✅ Проверить подписку",
        "not_subscribed": "❌ Ты ещё не подписался!",
        "ai_searching": "🤖 AI ищет фильм по описанию...",
        "ai_recommending": "🎯 AI подбирает фильмы для тебя...",
        "ai_found": "🤖 AI думает это *{}*!",
        "ai_not_found": "❌ AI не смог определить фильм. Попробуй подробнее!",
        "ai_no_result": "🤖 AI думает это *{}*, но не найдено.",
        "not_found": "❌ Ничего не найдено.\n\nПопробуй:\n• ID: `572802`\n• Название: `Интерстеллар`\n• Актёр: `Tom Hanks`\n• Описание сцены\n• `посоветуй фильм про зомби`",
        "film_not_found": "❌ Фильм не найден. Проверь ID.",
        "rating": "⭐ Рейтинг: {}/10",
        "similar": "🎬 Похожие",
        "actors": "👥 Актёры",
        "actors_title": "👥 *Актёры — нажми чтобы открыть фильмы:*\n\n",
        "actor_movies": "🎭 *{}*\n\nЛистай карточки 👇",
        "no_similar": "Похожих не найдено",
        "no_actors": "Актёры не найдены",
        "top": "🔥 Топ фильмов",
        "new": "🆕 Новинки",
        "upcoming": "🎬 Скоро в кино",
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
        "stats": "📊 *Статистика CINEMATRIX*\n\n👥 Всего: *{}*\n🔥 Сегодня: *{}*\n🔍 Запросов: *{}*\n🔗 Рефералов: *{}*\n\n👤 Твои приглашения: *{}*",
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
    },
    "uz": {
        "welcome": "🎬 CINEMATRIX ga xush kelibsiz!\n\n📌 Qanday foydalanish:\n🔢 *Film ID* — masalan: `572802`\n🔤 *Nomi* — masalan: `Interstellar`\n🎭 *Aktyor* — masalan: `Tom Hanks`\n🤖 *Sahnani tasvirla* — masalan: `orol ustida qolgan odam haqida film`\n🎯 *Maslahat so'ra* — masalan: `zombi haqida film tavsiya qil`\n\nPastdagi tugmalardan foydalaning 👇",
        "choose_section": "Bo'limni tanlang:",
        "subscribe": "📢 Kanalga obuna bo'ling va tugmani bosing!",
        "check_sub": "✅ Obunani tekshirish",
        "not_subscribed": "❌ Siz hali obuna bo'lmagansiz!",
        "ai_searching": "🤖 AI filmni tavsif bo'yicha qidirmoqda...",
        "ai_recommending": "🎯 AI siz uchun filmlar tanlamoqda...",
        "ai_found": "🤖 AI bu *{}* deb o'ylaydi!",
        "ai_not_found": "❌ AI filmni aniqlay olmadi. Batafsil tasvirlang!",
        "ai_no_result": "🤖 AI bu *{}* deb o'ylaydi, lekin topilmadi.",
        "not_found": "❌ Hech narsa topilmadi.\n\nUrinib ko'ring:\n• ID: `572802`\n• Nomi: `Interstellar`\n• Aktyor: `Tom Hanks`\n• Sahna tavsifi\n• `zombi haqida film tavsiya qil`",
        "film_not_found": "❌ Film topilmadi. ID ni tekshiring.",
        "rating": "⭐ Reyting: {}/10",
        "similar": "🎬 O'xshash",
        "actors": "👥 Aktyorlar",
        "actors_title": "👥 *Aktyorlar — filmlarni ochish uchun bosing:*\n\n",
        "actor_movies": "🎭 *{}*\n\nKartochkalarni aylantiring 👇",
        "no_similar": "O'xshash film topilmadi",
        "no_actors": "Aktyorlar topilmadi",
        "top": "🔥 Top filmlar",
        "new": "🆕 Yangiliklar",
        "upcoming": "🎬 Tez chiqadi",
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
        "new_user": "🎉 Sizning havolangiz orqali yangi foydalanuvchi keldi!\n👥 Jami taklif qilingan: *{}*\n🎁 Sizga bonus berildi — 24 soat obunasiz!",
        "quiz_title": "🎮 *Filmni toping!*\n\n📝 {}\n\nTo'g'ri javobni tanlang:",
        "quiz_correct": "✅ To'g'ri!",
        "quiz_wrong": "❌ Noto'g'ri! To'g'ri javob: {}",
        "quiz_expired": "Viktorina muddati tugadi!",
        "stats": "📊 *CINEMATRIX statistikasi*\n\n👥 Jami: *{}*\n🔥 Bugun: *{}*\n🔍 So'rovlar: *{}*\n🔗 Referallar: *{}*\n\n👤 Sizning takliflaringiz: *{}*",
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
        "resubscribe": "📢 Salom! Siz kanaldan obunani bekor qildingiz.\n\nBotdan foydalanishni davom ettirish uchun qayta obuna bo'ling:",
        "recommend_prompt": "🎯 *Nima tavsiya qilay?*\n\nNimani ko'rmoqchi ekanligingizni yozing:\n\n• `zombi haqida filmlar`\n• `oilaviy komediyalar`\n• `Joker kabi trillerlar`\n• `bolalar uchun multfilmlar`\n• `Van Damm bilan boyeviklar`",
        "ai_recommend_result": "🎯 *AI siz uchun tanladi:*\n\nKartochkalarni aylantiring 👇",
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
        keyboard=[[
            KeyboardButton(text=tx["top"]),
            KeyboardButton(text=tx["new"]),
            KeyboardButton(text=tx["upcoming"])
        ], [
            KeyboardButton(text=tx["favorites"]),
            KeyboardButton(text=tx["quiz"]),
            KeyboardButton(text=tx["recommend"])
        ], [
            KeyboardButton(text=tx["invite"])
        ]],
        resize_keyboard=True,
        persistent=True
    )

search_cache = {}

def init_db():
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        joined_at TEXT, last_active TEXT, requests_count INTEGER DEFAULT 0,
        invited_by INTEGER, bonus_until TEXT, lang TEXT DEFAULT 'ru')""")
    c.execute("""CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        query TEXT, result TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, movie_id INTEGER, title TEXT,
        year TEXT, rating REAL, poster TEXT, added_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inviter_id INTEGER, invited_id INTEGER, created_at TEXT)""")
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, invited_by=None):
    conn = sqlite3.connect("cinematrix.db")
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
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    c.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()

def get_lang(user_id):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    row = c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else "ru"

def get_stats():
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_active = c.execute("SELECT COUNT(*) FROM users WHERE last_active LIKE ?", (f"{today}%",)).fetchone()[0]
    total_requests = c.execute("SELECT SUM(requests_count) FROM users").fetchone()[0] or 0
    total_referrals = c.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
    conn.close()
    return total, today_active, total_requests, total_referrals

def has_bonus(user_id):
    conn = sqlite3.connect("cinematrix.db")
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
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (user_id,)).fetchone()[0]
    conn.close()
    return count

def is_favorited(user_id, movie_id):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    row = c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id)).fetchone()
    conn.close()
    return row is not None

def add_favorite(user_id, movie_id, title, year, rating, poster):
    conn = sqlite3.connect("cinematrix.db")
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
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    c.execute("DELETE FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id))
    conn.commit()
    conn.close()

def get_favorites(user_id):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    rows = c.execute("SELECT movie_id, title, year, rating, poster FROM favorites WHERE user_id=? ORDER BY added_at DESC", (user_id,)).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "release_date": r[2], "vote_average": r[3], "poster_path": r[4]} for r in rows]

def get_all_users():
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    rows = c.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]

async def check_sub(user_id):
    if has_bonus(user_id) or user_id == ADMIN_ID:
        return []
    not_subbed = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(ch["username"], user_id)
            if member.status in ["left", "kicked", "banned"]:
                not_subbed.append(ch)
        except:
            not_subbed.append(ch)
    return not_subbed

async def translate_to_uz(text):
    if not text or len(text) < 10:
        return text
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 500,
                      "messages": [{"role": "user", "content": f"Translate this movie description to Uzbek language. Reply ONLY with the translation, nothing else:\n\n{text}"}]},
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
                      "messages": [{"role": "user", "content": f"What movie is this describing? Description: {description}. Reply with ONLY the English movie title. If not sure, give 2-3 most likely titles separated by commas. If unknown, reply: unknown"}]},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                if "content" in data:
                    return data["content"][0]["text"].strip().strip('"')
                return "unknown"
    except Exception as e:
        print(f"AI error: {e}")
        return "unknown"

async def ai_recommend(query):
    """AI возвращает список названий фильмов по запросу пользователя"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "messages": [{"role": "user", "content": f"User wants movie recommendations. Request: {query}\n\nReply with ONLY 5 English movie titles separated by commas. No explanations, no numbers, just titles. Example: The Dark Knight, Inception, Interstellar, Parasite, Joker"}]},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                if "content" in data:
                    result = data["content"][0]["text"].strip()
                    titles = [t.strip() for t in result.split(",")]
                    return [t for t in titles if t and len(t) > 1][:5]
                return []
    except Exception as e:
        print(f"AI recommend error: {e}")
        return []

async def search_movies_by_title(title, user_id=None):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": title, "language": "ru-RU"}) as r:
            data = await r.json()
    return data.get("results", [])[:2]

def movie_card_text(m, index, total, user_id):
    title = m.get("title", "—")
    year = (m.get("release_date", "") or "")[:4]
    rating = round(m.get("vote_average", 0) or 0, 1)
    overview = (m.get("overview", "") or tr(user_id, "no_desc"))[:200]
    movie_id = m.get("id")
    return (
        f"🎬 *{title}* ({year})\n"
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

async def send_movie_card(message, movies, index, source, edit=False, user_id=None):
    m = movies[index]
    poster = m.get("poster_path", "")
    text = movie_card_text(m, index + 1, len(movies), user_id)
    kb = movie_card_keyboard(movies, index, source, user_id)
    if poster:
        photo_url = f"https://image.tmdb.org/t/p/w500{poster}"
        if edit:
            try:
                await message.edit_media(types.InputMediaPhoto(media=photo_url, caption=text, parse_mode="Markdown"), reply_markup=kb)
            except:
                await message.answer_photo(photo_url, caption=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await message.answer_photo(photo_url, caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        if edit:
            await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def morning_broadcast():
    while True:
        now = datetime.now()
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TMDB_URL}/movie/popular",
                    params={"api_key": TMDB_API_KEY, "language": "ru-RU", "page": random.randint(1, 5)}) as r:
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
            users = get_all_users()
            for uid in users:
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
        ref_count = get_referral_count(invited_by)
        try:
            await bot.send_message(invited_by, tr(invited_by, "new_user", ref_count), parse_mode="Markdown")
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
    total, today_active, total_requests, total_referrals = get_stats()
    ref_count = get_referral_count(message.from_user.id)
    await message.answer(tr(message.from_user.id, "stats", total, today_active, total_requests, total_referrals, ref_count), parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(tr(message.from_user.id, "no_access"))
        return
    total, today_active, total_requests, total_referrals = get_stats()
    await message.answer(
        f"👑 *Админ панель*\n\n👥 Пользователей: *{total}*\n🔥 Сегодня: *{today_active}*\n"
        f"🔍 Запросов: *{total_requests}*\n🔗 Рефералов: *{total_referrals}*\n\n"
        f"📤 `/post 872585`\n📢 `/broadcast текст`",
        parse_mode="Markdown"
    )

@dp.message(Command("post"))
async def post_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(tr(message.from_user.id, "no_access"))
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❌ Используй: `/post 872585`", parse_mode="Markdown")
        return
    movie_id = int(args[1])
    await message.answer(tr(message.from_user.id, "posting"))
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            m = await r.json()
    if not m.get("title"):
        await message.answer(tr(message.from_user.id, "post_error"))
        return
    title = m.get("title", "—")
    year = (m.get("release_date", "") or "")[:4]
    rating = round(m.get("vote_average", 0) or 0, 1)
    overview = m.get("overview", "") or ""
    poster = m.get("poster_path", "")
    q = urllib.parse.quote(title)
    await post_to_channel(movie_id, title, year, rating, overview, poster, q)
    await message.answer(tr(message.from_user.id, "posted", title), parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(tr(message.from_user.id, "no_access"))
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer(tr(message.from_user.id, "broadcast_usage"), parse_mode="Markdown")
        return
    users = get_all_users()
    sent = 0
    failed = 0
    status = await message.answer(tr(message.from_user.id, "broadcast_sending", len(users)))
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 *CINEMATRIX:*\n\n{text}", parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await status.edit_text(tr(message.from_user.id, "broadcast_done", sent, failed), parse_mode="Markdown")

# Ключевые слова для определения запроса на рекомендацию
RECOMMEND_KEYWORDS_RU = ["посоветуй", "порекомендуй", "что посмотреть", "хочу посмотреть", "посоветовать", "рекомендуй", "подбери", "подскажи фильм", "какой фильм"]
RECOMMEND_KEYWORDS_UZ = ["tavsiya", "maslahat", "ko'rmoqchi", "qanday film", "film tavsiya", "tavsiya qil", "koʻrmoqchi"]

def is_recommend_request(text, lang):
    text_lower = text.lower()
    keywords = RECOMMEND_KEYWORDS_RU if lang == "ru" else RECOMMEND_KEYWORDS_UZ
    return any(kw in text_lower for kw in keywords)

@dp.message()
async def handle(message: types.Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = message.text.strip()
    user_id = message.from_user.id
    lang = get_lang(user_id)
    tx = TEXTS[lang]

    if text in ["🔥 Топ фильмов", "🔥 Top filmlar", tx["top"]]:
        await show_top(message)
        return
    elif text in ["🆕 Новинки", "🆕 Yangiliklar", tx["new"]]:
        await show_new(message)
        return
    elif text in ["🎬 Скоро в кино", "🎬 Tez chiqadi", tx["upcoming"]]:
        await show_upcoming(message)
        return
    elif text in ["❤️ Избранное", "❤️ Sevimlilar", tx["favorites"]]:
        await show_favorites(message)
        return
    elif text in ["🎮 Квиз", "🎮 Viktorina", tx["quiz"]]:
        await start_quiz(message)
        return
    elif text in ["🎯 Подобрать", "🎯 Tavsiya", tx["recommend"]]:
        await message.answer(tr(user_id, "recommend_prompt"), parse_mode="Markdown")
        return
    elif text in ["👥 Пригласить", "👥 Taklif qilish", tx["invite"]]:
        await show_invite(message)
        return

    not_subbed = await check_sub(user_id)
    if not_subbed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
        ] + [[InlineKeyboardButton(text=tr(user_id, "check_sub"), callback_data=f"check_only:{user_id}")]])
        await message.answer(tr(user_id, "resubscribe"), reply_markup=kb, parse_mode="Markdown")
        return

    if text.isdigit():
        await show_film(message, int(text))

    elif is_recommend_request(text, lang):
        # Запрос на рекомендацию
        thinking = await message.answer(tr(user_id, "ai_recommending"))
        titles = await ai_recommend(text)
        if not titles:
            await thinking.edit_text(tr(user_id, "ai_not_found"))
            return
        all_movies = []
        for title_opt in titles:
            movies = await search_movies_by_title(title_opt, user_id)
            all_movies.extend(movies)
        seen = set()
        unique = []
        for m in all_movies:
            if m["id"] not in seen:
                seen.add(m["id"])
                unique.append(m)
        if not unique:
            await thinking.edit_text(tr(user_id, "ai_not_found"))
            return
        await thinking.edit_text(tr(user_id, "ai_recommend_result"), parse_mode="Markdown")
        search_cache[f"{user_id}_rec"] = unique[:5]
        await send_movie_card(message, unique[:5], 0, f"{user_id}_rec", user_id=user_id)

    elif len(text) > 20:
        thinking = await message.answer(tr(user_id, "ai_searching"))
        movie_title = await ai_find_movie(text)
        if movie_title.lower() == "unknown":
            await thinking.edit_text(tr(user_id, "ai_not_found"))
            return
        titles = [t.strip() for t in movie_title.split(",")]
        all_movies = []
        for title_opt in titles[:3]:
            movies = await search_movies_by_title(title_opt, user_id)
            all_movies.extend(movies)
        seen = set()
        unique = []
        for m in all_movies:
            if m["id"] not in seen:
                seen.add(m["id"])
                unique.append(m)
        if not unique:
            await thinking.edit_text(tr(user_id, "ai_no_result", movie_title), parse_mode="Markdown")
            return
        await thinking.edit_text(tr(user_id, "ai_found", titles[0]), parse_mode="Markdown")
        search_cache[f"{user_id}_search"] = unique[:5]
        await send_movie_card(message, unique[:5], 0, f"{user_id}_search", user_id=user_id)

    else:
        movies = await search_movies_by_title(text, user_id)
        if movies:
            search_cache[f"{user_id}_search"] = movies
            await send_movie_card(message, movies, 0, f"{user_id}_search", user_id=user_id)
        else:
            await search_person(message, text)

async def show_invite(message):
    user_id = message.from_user.id
    ref_count = get_referral_count(user_id)
    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    await message.answer(tr(user_id, "invite_text", link, ref_count), parse_mode="Markdown")

async def show_favorites(message):
    user_id = message.from_user.id
    favs = get_favorites(user_id)
    if not favs:
        await message.answer(tr(user_id, "no_favorites"))
        return
    search_cache[f"{user_id}_fav"] = favs
    await send_movie_card(message, favs, 0, f"{user_id}_fav", user_id=user_id)

async def start_quiz(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/popular",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = [m for m in data.get("results", []) if m.get("overview")]
    if not movies:
        return
    movie = random.choice(movies)
    title = movie.get("title", "—")
    overview = (movie.get("overview", "") or "")[:300]
    movie_id = movie.get("id")
    if lang == "uz" and overview:
        overview = await translate_to_uz(overview)
    wrong_titles = [m.get("title") for m in movies if m.get("title") != title]
    wrong = random.sample(wrong_titles, min(3, len(wrong_titles)))
    options = wrong + [title]
    random.shuffle(options)
    search_cache[f"quiz_{user_id}"] = {"answer": title, "movie_id": movie_id}
    buttons = [[InlineKeyboardButton(text=opt, callback_data=f"quiz:{opt}")] for opt in options]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(tr(user_id, "quiz_title", overview), parse_mode="Markdown", reply_markup=kb)

async def show_top(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/popular", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    search_cache[f"{user_id}_top"] = movies
    await send_movie_card(message, movies, 0, f"{user_id}_top", user_id=user_id)

async def show_new(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/now_playing", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    search_cache[f"{user_id}_new"] = movies
    await send_movie_card(message, movies, 0, f"{user_id}_new", user_id=user_id)

async def show_upcoming(message):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/upcoming", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    search_cache[f"{user_id}_upcoming"] = movies
    await send_movie_card(message, movies, 0, f"{user_id}_upcoming", user_id=user_id)

async def search_person(message, query):
    user_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/search/person", params={"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU"}) as r:
            data = await r.json()
    results = data.get("results", [])
    if not results:
        await message.answer(tr(user_id, "not_found"), parse_mode="Markdown")
        return
    person = results[0]
    person_id = person["id"]
    name = person.get("name", "—")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/person/{person_id}/movie_credits", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            credits = await r.json()
    movies = sorted(credits.get("cast", []), key=lambda x: x.get("popularity", 0), reverse=True)[:8]
    search_cache[f"{user_id}_person"] = movies
    await message.answer(tr(user_id, "actor_movies", name), parse_mode="Markdown")
    await send_movie_card(message, movies, 0, f"{user_id}_person", user_id=user_id)

async def post_to_channel(movie_id, title, year, rating, overview, poster, q):
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Получить в боте", url=f"https://t.me/{BOT_USERNAME}?start={movie_id}")],
            [
                InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
                InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}")
            ]
        ])
        text = f"🎬 *{title}* ({year})\n\n⭐ Рейтинг: {rating}/10\n\n📝 {overview}\n\n🆔 Код: `{movie_id}`"
        if poster:
            await bot.send_photo(CHANNEL, f"https://image.tmdb.org/t/p/w500{poster}", caption=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await bot.send_message(CHANNEL, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        print(f"Ошибка постинга: {e}")

async def show_film(message, movie_id, post_channel=False):
    user_id = message.from_user.id if hasattr(message, 'from_user') and message.from_user else ADMIN_ID
    lang = get_lang(user_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            m = await r.json()
    if not m.get("title"):
        await message.answer(tr(user_id, "film_not_found"))
        return
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
    text = f"🎬 *{title}* ({year})\n\n{tr(user_id, 'rating', rating)}\n\n📝 {overview}"
    if poster:
        await message.answer_photo(f"https://image.tmdb.org/t/p/w500{poster}", caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)
    if post_channel:
        await post_to_channel(movie_id, title, year, rating, overview, poster, q)

@dp.callback_query(lambda c: c.data.startswith("lang:"))
async def lang_callback(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    set_lang(user_id, lang)
    try:
        await callback.message.delete()
    except:
        pass
    kb_mini = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎬 " + ("Открыть CINEMATRIX" if lang == "ru" else "CINEMATRIX ni ochish"),
            web_app=types.WebAppInfo(url="https://voluble-croissant-d09014.netlify.app"))
    ]])
    await callback.message.answer(tr(user_id, "welcome"), reply_markup=get_menu(user_id), parse_mode="Markdown")
    await callback.message.answer(tr(user_id, "choose_section"), reply_markup=kb_mini)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check_only:"))
async def check_only_callback(callback: types.CallbackQuery):
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
        await callback.answer(tr(user_id, "quiz_expired"), show_alert=True)
        return
    correct = quiz_data["answer"]
    if answer == correct:
        await callback.answer(tr(user_id, "quiz_correct"), show_alert=True)
        await callback.message.edit_reply_markup()
        movie_id = quiz_data["movie_id"]
        not_subbed = await check_sub(user_id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text=tr(user_id, "check_sub"), callback_data=f"check:{movie_id}")]])
            await callback.message.answer(tr(user_id, "subscribe"), reply_markup=kb)
        else:
            await show_film(callback.message, movie_id)
    else:
        await callback.answer(tr(user_id, "quiz_wrong", correct), show_alert=True)

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
        add_favorite(user_id, movie_id, m.get("title","—"), (m.get("release_date","") or "")[:4], round(m.get("vote_average",0) or 0,1), m.get("poster_path",""))
        await callback.answer(tr(user_id, "added_fav"))

@dp.callback_query(lambda c: c.data.startswith("card:"))
async def card_nav(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    index = int(parts[2])
    movies = search_cache.get(source)
    if not movies:
        await callback.answer(tr(callback.from_user.id, "session_expired"), show_alert=True)
        return
    await send_movie_card(callback.message, movies, index, source, edit=True, user_id=callback.from_user.id)
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
        await callback.answer(tr(user_id, "no_similar"), show_alert=True)
        return
    search_cache[f"{user_id}_sim"] = results
    await send_movie_card(callback.message, results, 0, f"{user_id}_sim", user_id=user_id)
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
        await callback.answer(tr(user_id, "no_actors"), show_alert=True)
        return
    text = tr(user_id, "actors_title")
    buttons = []
    for a in actors:
        name = a.get("name", "—")
        character = a.get("character", "—")
        person_id = a.get("id")
        text += f"• *{name}* — {character}\n"
        buttons.append([InlineKeyboardButton(text=f"🎭 {name}", callback_data=f"person:{person_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
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
    await send_movie_card(callback.message, movies, 0, f"{user_id}_person", user_id=user_id)
    await callback.answer()

async def main():
    init_db()
    asyncio.create_task(morning_broadcast())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
