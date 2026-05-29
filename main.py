import asyncio
import aiohttp
import urllib.parse
import sqlite3
import os
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

main_menu = ReplyKeyboardMarkup(
    keyboard=[[
        KeyboardButton(text="🔥 Топ фильмов"),
        KeyboardButton(text="🆕 Новинки"),
        KeyboardButton(text="🎬 Скоро в кино")
    ], [
        KeyboardButton(text="❤️ Избранное"),
        KeyboardButton(text="🎮 Квиз"),
        KeyboardButton(text="👥 Пригласить")
    ]],
    resize_keyboard=True,
    persistent=True
)

search_cache = {}

# ===== БД =====
def init_db():
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        joined_at TEXT, last_active TEXT, requests_count INTEGER DEFAULT 0,
        invited_by INTEGER, bonus_until TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        query TEXT, result TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, movie_id INTEGER, title TEXT,
        year TEXT, rating REAL, poster TEXT,
        added_at TEXT)""")
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
        c.execute("INSERT INTO users (user_id, username, first_name, joined_at, last_active, invited_by) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, username, first_name, now, now, invited_by))
        if invited_by:
            c.execute("INSERT INTO referrals (inviter_id, invited_id, created_at) VALUES (?, ?, ?)",
                      (invited_by, user_id, now))
            # Даём бонус пригласившему на 24 часа
            bonus = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
            c.execute("UPDATE users SET bonus_until=? WHERE user_id=?", (bonus, invited_by))
    else:
        c.execute("UPDATE users SET last_active=?, requests_count=requests_count+1 WHERE user_id=?", (now, user_id))
    conn.commit()
    conn.close()

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
            bonus_until = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            return datetime.now() < bonus_until
        except:
            return False
    return False

def get_referral_count(user_id):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (user_id,)).fetchone()[0]
    conn.close()
    return count

def add_favorite(user_id, movie_id, title, year, rating, poster):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    existing = c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id)).fetchone()
    if existing:
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
    rows = c.execute("SELECT movie_id, title, year, rating, poster FROM favorites WHERE user_id=? ORDER BY added_at DESC",
                     (user_id,)).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "year": r[2], "rating": r[3], "poster_path": r[4]} for r in rows]

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
            if member.status in ["left", "kicked"]:
                not_subbed.append(ch)
        except:
            not_subbed.append(ch)
    return not_subbed

async def ai_find_movie(description):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 100,
                      "messages": [{"role": "user", "content": f"What movie is this describing? Description: {description}. Reply with ONLY the English movie title. If unknown, reply: unknown"}]},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                if "content" in data:
                    return data["content"][0]["text"].strip().strip('"')
                return "unknown"
    except Exception as e:
        print(f"AI error: {e}")
        return "unknown"

async def search_movies_by_title(title):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": title, "language": "ru-RU"}) as r:
            data = await r.json()
    return data.get("results", [])[:5]

def is_favorited(user_id, movie_id):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    row = c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id)).fetchone()
    conn.close()
    return row is not None

def movie_card_text(m, index, total):
    title = m.get("title", "—")
    year = m.get("release_date", "")[:4]
    rating = round(m.get("vote_average", 0), 1)
    overview = m.get("overview", "Описание отсутствует")[:200]
    movie_id = m.get("id")
    return (
        f"🎬 *{title}* ({year})\n"
        f"⭐ Рейтинг: {rating}/10\n"
        f"🆔 Код: `{movie_id}`\n\n"
        f"📝 {overview}...\n\n"
        f"_{index}/{total}_"
    )

def movie_card_keyboard(movies, index, source, user_id=None):
    m = movies[index]
    movie_id = m.get("id")
    total = len(movies)
    q = urllib.parse.quote(m.get("title", ""))
    fav = is_favorited(user_id, movie_id) if user_id else False
    fav_text = "💔 Убрать" if fav else "❤️ В избранное"

    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"card:{source}:{index-1}"))
    nav.append(InlineKeyboardButton(text=f"{index+1}/{total}", callback_data="noop"))
    if index < total - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"card:{source}:{index+1}"))

    return InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [
            InlineKeyboardButton(text="✅ Открыть", callback_data=f"film:{movie_id}"),
            InlineKeyboardButton(text=fav_text, callback_data=f"fav:{movie_id}")
        ],
        [
            InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
            InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}")
        ]
    ])

async def send_movie_card(message, movies, index, source, edit=False, user_id=None):
    m = movies[index]
    poster = m.get("poster_path", "")
    text = movie_card_text(m, index + 1, len(movies))
    kb = movie_card_keyboard(movies, index, source, user_id)

    if poster:
        photo_url = f"https://image.tmdb.org/t/p/w500{poster}"
        if edit:
            try:
                await message.edit_media(
                    types.InputMediaPhoto(media=photo_url, caption=text, parse_mode="Markdown"),
                    reply_markup=kb
                )
            except:
                await message.answer_photo(photo_url, caption=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await message.answer_photo(photo_url, caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        if edit:
            await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await message.answer(text, parse_mode="Markdown", reply_markup=kb)

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
        ref_count = get_referral_count(invited_by)
        try:
            await bot.send_message(invited_by,
                f"🎉 По твоей ссылке пришёл новый пользователь!\n"
                f"👥 Всего приглашено: *{ref_count}*\n"
                f"🎁 Тебе выдан бонус — 24 часа без подписки на канал!",
                parse_mode="Markdown"
            )
        except:
            pass

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎬 Открыть CINEMATRIX",
            web_app=types.WebAppInfo(url="https://voluble-croissant-d09014.netlify.app"))
    ]])
    await message.answer(
        "🎬 Добро пожаловать в CINEMATRIX!\n\n"
        "📌 Как пользоваться:\n"
        "🔢 *ID фильма* — например: `572802`\n"
        "🔤 *Название* — например: `Интерстеллар`\n"
        "🎭 *Актёр* — например: `Tom Hanks`\n"
        "🤖 *Опиши сцену* — например: `фильм где человек застрял на острове`\n\n"
        "Используй кнопки внизу 👇",
        reply_markup=main_menu, parse_mode="Markdown"
    )
    await message.answer("Выбери раздел:", reply_markup=kb)

@dp.message(Command("stats"))
async def stats(message: types.Message):
    total, today_active, total_requests, total_referrals = get_stats()
    ref_count = get_referral_count(message.from_user.id)
    await message.answer(
        f"📊 *Статистика CINEMATRIX*\n\n"
        f"👥 Всего: *{total}*\n"
        f"🔥 Сегодня: *{today_active}*\n"
        f"🔍 Запросов: *{total_requests}*\n"
        f"🔗 Приглашений всего: *{total_referrals}*\n\n"
        f"👤 Твои приглашения: *{ref_count}*",
        parse_mode="Markdown"
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return
    total, today_active, total_requests, total_referrals = get_stats()
    await message.answer(
        f"👑 *Админ панель*\n\n"
        f"👥 Пользователей: *{total}*\n"
        f"🔥 Сегодня: *{today_active}*\n"
        f"🔍 Запросов: *{total_requests}*\n"
        f"🔗 Рефералов: *{total_referrals}*\n\n"
        f"📤 `/post 872585` — постинг в канал\n"
        f"📢 `/broadcast текст` — рассылка всем",
        parse_mode="Markdown"
    )

@dp.message(Command("post"))
async def post_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❌ Используй: `/post 872585`", parse_mode="Markdown")
        return
    movie_id = int(args[1])
    await message.answer("📤 Постим...")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            m = await r.json()
    if not m.get("title"):
        await message.answer("❌ Фильм не найден.")
        return
    title = m.get("title", "—")
    year = m.get("release_date", "")[:4]
    rating = round(m.get("vote_average", 0), 1)
    overview = m.get("overview", "Описание отсутствует")
    poster = m.get("poster_path", "")
    q = urllib.parse.quote(title)
    await post_to_channel(movie_id, title, year, rating, overview, poster, q)
    await message.answer(f"✅ *{title}* запостен!", parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("❌ Используй: `/broadcast Привет всем!`", parse_mode="Markdown")
        return
    users = get_all_users()
    sent = 0
    failed = 0
    status = await message.answer(f"📢 Отправляю {len(users)} пользователям...")
    for user_id in users:
        try:
            await bot.send_message(user_id, f"📢 *Сообщение от CINEMATRIX:*\n\n{text}", parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await status.edit_text(f"✅ Рассылка завершена!\n📨 Отправлено: *{sent}*\n❌ Ошибок: *{failed}*", parse_mode="Markdown")

@dp.message()
async def handle(message: types.Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = message.text.strip()
    user_id = message.from_user.id

    if text == "🔥 Топ фильмов":
        await show_top(message)
        return
    elif text == "🆕 Новинки":
        await show_new(message)
        return
    elif text == "🎬 Скоро в кино":
        await show_upcoming(message)
        return
    elif text == "❤️ Избранное":
        await show_favorites(message)
        return
    elif text == "🎮 Квиз":
        await start_quiz(message)
        return
    elif text == "👥 Пригласить":
        await show_invite(message)
        return

    if text.isdigit():
        not_subbed = await check_sub(user_id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check:{text}")]])
            await message.answer("📢 Подпишись на канал!", reply_markup=kb)
        else:
            await show_film(message, int(text))

    elif len(text) > 20:
        thinking = await message.answer("🤖 AI ищет фильм по описанию...")
        movie_title = await ai_find_movie(text)
        if movie_title.lower() == "unknown":
            await thinking.edit_text("❌ AI не смог определить. Попробуй подробнее!")
            return
        movies = await search_movies_by_title(movie_title)
        if not movies:
            await thinking.edit_text(f"🤖 AI думает это *{movie_title}*, но не найдено.", parse_mode="Markdown")
            return
        await thinking.edit_text(f"🤖 AI думает это *{movie_title}*!", parse_mode="Markdown")
        search_cache[f"{user_id}_search"] = movies
        await send_movie_card(message, movies, 0, f"{user_id}_search", user_id=user_id)

    else:
        movies = await search_movies_by_title(text)
        if movies:
            search_cache[f"{user_id}_search"] = movies
            await send_movie_card(message, movies, 0, f"{user_id}_search", user_id=user_id)
        else:
            await search_person(message, text)

async def show_invite(message):
    user_id = message.from_user.id
    ref_count = get_referral_count(user_id)
    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    await message.answer(
        f"👥 *Реферальная система*\n\n"
        f"Твоя ссылка:\n`{link}`\n\n"
        f"📊 Ты пригласил: *{ref_count}* человек\n\n"
        f"🎁 *Бонус:* за каждого приглашённого получаешь 24 часа без подписки на канал!",
        parse_mode="Markdown"
    )

async def show_favorites(message):
    user_id = message.from_user.id
    favs = get_favorites(user_id)
    if not favs:
        await message.answer("❤️ У тебя пока нет избранных фильмов.\n\nНажми ❤️ под любым фильмом чтобы добавить!")
        return
    search_cache[f"{user_id}_fav"] = favs
    await send_movie_card(message, favs, 0, f"{user_id}_fav", user_id=user_id)

async def start_quiz(message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/popular",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    import random
    movies = data.get("results", [])
    if not movies:
        await message.answer("❌ Не удалось загрузить квиз.")
        return
    movie = random.choice(movies)
    title = movie.get("title", "—")
    overview = movie.get("overview", "")[:300]
    movie_id = movie.get("id")

    wrong = random.sample([m.get("title") for m in movies if m.get("title") != title], 3)
    options = wrong + [title]
    random.shuffle(options)

    search_cache[f"quiz_{message.from_user.id}"] = {"answer": title, "movie_id": movie_id}

    buttons = [[InlineKeyboardButton(text=opt, callback_data=f"quiz:{opt}")] for opt in options]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"🎮 *Угадай фильм!*\n\n"
        f"📝 {overview}\n\n"
        f"Выбери правильный ответ:",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def show_top(message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/popular",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    user_id = message.from_user.id
    search_cache[f"{user_id}_top"] = movies
    await send_movie_card(message, movies, 0, f"{user_id}_top", user_id=user_id)

async def show_new(message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/now_playing",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    user_id = message.from_user.id
    search_cache[f"{user_id}_new"] = movies
    await send_movie_card(message, movies, 0, f"{user_id}_new", user_id=user_id)

async def show_upcoming(message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/upcoming",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    user_id = message.from_user.id
    search_cache[f"{user_id}_upcoming"] = movies
    await send_movie_card(message, movies, 0, f"{user_id}_upcoming", user_id=user_id)

async def search_person(message, query):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/search/person",
            params={"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU"}) as r:
            data = await r.json()
    results = data.get("results", [])
    if not results:
        await message.answer("❌ Ничего не найдено.\n\nПопробуй:\n• ID: `572802`\n• Название: `Интерстеллар`\n• Актёр: `Tom Hanks`\n• Описание сцены", parse_mode="Markdown")
        return
    person = results[0]
    person_id = person["id"]
    name = person.get("name", "—")
    known_for = person.get("known_for_department", "—")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/person/{person_id}/movie_credits",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            credits = await r.json()
    movies = sorted(credits.get("cast", []), key=lambda x: x.get("popularity", 0), reverse=True)[:8]
    user_id = message.from_user.id
    search_cache[f"{user_id}_person"] = movies
    await message.answer(f"🎭 *{name}* — {known_for}\n\nЛистай карточки 👇", parse_mode="Markdown")
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
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            m = await r.json()
    if not m.get("title"):
        await message.answer("❌ Фильм не найден.")
        return
    title = m.get("title", "—")
    year = m.get("release_date", "")[:4]
    rating = round(m.get("vote_average", 0), 1)
    overview = m.get("overview", "Описание отсутствует")
    poster = m.get("poster_path", "")
    q = urllib.parse.quote(title)
    user_id = message.from_user.id if hasattr(message, 'from_user') and message.from_user else None
    fav = is_favorited(user_id, movie_id) if user_id else False
    fav_text = "💔 Убрать" if fav else "❤️ В избранное"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Похожие", callback_data=f"sim:{movie_id}"),
            InlineKeyboardButton(text="👥 Актёры", callback_data=f"cast:{movie_id}")
        ],
        [
            InlineKeyboardButton(text=fav_text, callback_data=f"fav:{movie_id}")
        ],
        [
            InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
            InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}")
        ]
    ])
    text = f"🎬 *{title}* ({year})\n\n⭐ Рейтинг: {rating}/10\n\n📝 {overview}"
    if poster:
        await message.answer_photo(f"https://image.tmdb.org/t/p/w500{poster}", caption=text, parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)
    if post_channel:
        await post_to_channel(movie_id, title, year, rating, overview, poster, q)

# ===== CALLBACKS =====
@dp.callback_query(lambda c: c.data.startswith("quiz:"))
async def quiz_answer(callback: types.CallbackQuery):
    answer = callback.data.replace("quiz:", "")
    quiz_data = search_cache.get(f"quiz_{callback.from_user.id}")
    if not quiz_data:
        await callback.answer("Квиз истёк!", show_alert=True)
        return
    correct = quiz_data["answer"]
    if answer == correct:
        await callback.answer("✅ Правильно!", show_alert=True)
        await callback.message.edit_reply_markup()
        movie_id = quiz_data["movie_id"]
        not_subbed = await check_sub(callback.from_user.id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check:{movie_id}")]])
            await callback.message.answer("📢 Подпишись чтобы открыть фильм!", reply_markup=kb)
        else:
            await show_film(callback.message, movie_id)
    else:
        await callback.answer(f"❌ Неправильно! Правильный ответ: {correct}", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("fav:"))
async def fav_callback(callback: types.CallbackQuery):
    movie_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    existing = c.execute("SELECT id FROM favorites WHERE user_id=? AND movie_id=?", (user_id, movie_id)).fetchone()
    conn.close()
    if existing:
        remove_favorite(user_id, movie_id)
        await callback.answer("💔 Убрано из избранного", show_alert=False)
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TMDB_URL}/movie/{movie_id}",
                params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
                m = await r.json()
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        rating = round(m.get("vote_average", 0), 1)
        poster = m.get("poster_path", "")
        add_favorite(user_id, movie_id, title, year, rating, poster)
        await callback.answer("❤️ Добавлено в избранное!", show_alert=False)

@dp.callback_query(lambda c: c.data.startswith("card:"))
async def card_nav(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    index = int(parts[2])
    movies = search_cache.get(source)
    if not movies:
        await callback.answer("Сессия истекла, повтори поиск", show_alert=True)
        return
    await send_movie_card(callback.message, movies, index, source, edit=True, user_id=callback.from_user.id)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("film:"))
async def film_callback(callback: types.CallbackQuery):
    movie_id = int(callback.data.split(":")[1])
    not_subbed = await check_sub(callback.from_user.id)
    if not_subbed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
        ] + [[InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check:{movie_id}")]])
        await callback.message.answer("📢 Подпишись на канал!", reply_markup=kb)
    else:
        await show_film(callback.message, movie_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check:"))
async def check_callback(callback: types.CallbackQuery):
    movie_id = callback.data.split(":")[1]
    not_subbed = await check_sub(callback.from_user.id)
    if not_subbed:
        await callback.answer("❌ Ты ещё не подписался!", show_alert=True)
    else:
        await callback.message.delete()
        await show_film(callback.message, int(movie_id))
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("sim:"))
async def similar(callback: types.CallbackQuery):
    movie_id = callback.data.split(":")[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}/similar",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    results = data.get("results", [])[:5]
    if not results:
        await callback.answer("Похожих не найдено", show_alert=True)
        return
    user_id = callback.from_user.id
    search_cache[f"{user_id}_sim"] = results
    await send_movie_card(callback.message, results, 0, f"{user_id}_sim", user_id=user_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cast:"))
async def cast(callback: types.CallbackQuery):
    movie_id = callback.data.split(":")[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}/credits",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    actors = data.get("cast", [])[:6]
    if not actors:
        await callback.answer("Актёры не найдены", show_alert=True)
        return
    text = "👥 *Актёры — нажми чтобы открыть фильмы:*\n\n"
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
    person_id = callback.data.split(":")[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/person/{person_id}/movie_credits",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            credits = await r.json()
        async with session.get(f"{TMDB_URL}/person/{person_id}",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            person = await r.json()
    name = person.get("name", "—")
    movies = sorted(credits.get("cast", []), key=lambda x: x.get("popularity", 0), reverse=True)[:8]
    user_id = callback.from_user.id
    search_cache[f"{user_id}_person"] = movies
    await callback.message.answer(f"🎭 *{name}*\n\nЛистай карточки 👇", parse_mode="Markdown")
    await send_movie_card(callback.message, movies, 0, f"{user_id}_person", user_id=user_id)
    await callback.answer()

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())