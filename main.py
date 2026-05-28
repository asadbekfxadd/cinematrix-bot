import asyncio
import aiohttp
import urllib.parse
import sqlite3
import os
from datetime import datetime
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

CHANNELS = [
    {"name": "Бободжонов", "username": "@thebobodjonov", "url": "https://t.me/thebobodjonov"},
]

# ===== МЕНЮ ВНИЗУ =====
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔥 Топ фильмов"), KeyboardButton(text="🆕 Новинки"), KeyboardButton(text="🎬 Скоро в кино")]
    ],
    resize_keyboard=True,
    persistent=True
)

def init_db():
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        joined_at TEXT, last_active TEXT, requests_count INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        query TEXT, result TEXT, created_at TEXT)""")
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, last_active) VALUES (?, ?, ?, ?, ?)",
              (user_id, username, first_name, now, now))
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
    conn.close()
    return total, today_active, total_requests

def log_search(user_id, query, result):
    conn = sqlite3.connect("cinematrix.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO searches (user_id, query, result, created_at) VALUES (?, ?, ?, ?)", (user_id, query, result, now))
    conn.commit()
    conn.close()

async def check_sub(user_id):
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

@dp.message(Command("start"))
async def start(message: types.Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎬 Открыть CINEMATRIX",
            web_app=types.WebAppInfo(url="https://voluble-croissant-d09014.netlify.app"))
    ]])
    await message.answer(
        "🎬 Добро пожаловать в CINEMATRIX!\n\n"
        "📌 Как пользоваться:\n"
        "🔢 *ID фильма* — например: `572802`\n"
        "🔤 *Название* — например: `Интерстеллар`\n"
        "🎭 *Имя актёра* — например: `Tom Hanks`\n"
        "🤖 *Опиши сцену* — например: `фильм где человек застрял на острове`\n"
        "📊 /stats — статистика\n"
        "👑 /admin — админ панель\n\n"
        "Используй кнопки внизу 👇",
        reply_markup=main_menu, parse_mode="Markdown"
    )
    await message.answer("Выбери раздел:", reply_markup=kb)

@dp.message(Command("stats"))
async def stats(message: types.Message):
    total, today_active, total_requests = get_stats()
    await message.answer(
        f"📊 *Статистика CINEMATRIX*\n\n"
        f"👥 Всего: *{total}*\n🔥 Сегодня: *{today_active}*\n🔍 Запросов: *{total_requests}*",
        parse_mode="Markdown"
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return
    total, today_active, total_requests = get_stats()
    await message.answer(
        f"👑 *Админ панель*\n\n"
        f"👥 Пользователей: *{total}*\n🔥 Сегодня: *{today_active}*\n🔍 Запросов: *{total_requests}*\n\n"
        f"📤 Постинг в канал:\n`/post ID` — например: `/post 872585`",
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
    await message.answer("📤 Постим в канал...")
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
    await message.answer(f"✅ Фильм *{title}* запостен в канал!", parse_mode="Markdown")

@dp.message()
async def handle(message: types.Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = message.text.strip()

    # Кнопки меню
    if text == "🔥 Топ фильмов":
        await show_top(message)
        return
    elif text == "🆕 Новинки":
        await show_new(message)
        return
    elif text == "🎬 Скоро в кино":
        await show_upcoming(message)
        return

    if text.isdigit():
        not_subbed = await check_sub(message.from_user.id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check:{text}")]])
            await message.answer("📢 Подпишись на канал и нажми кнопку!", reply_markup=kb)
        else:
            log_search(message.from_user.id, text, "movie_id")
            await show_film(message, int(text))

    elif len(text) > 20:
        thinking = await message.answer("🤖 AI ищет фильм по описанию...")
        movie_title = await ai_find_movie(text)
        if movie_title.lower() == "unknown":
            await thinking.edit_text("❌ AI не смог определить фильм. Попробуй подробнее!")
            return
        movies = await search_movies_by_title(movie_title)
        if not movies:
            await thinking.edit_text(f"🤖 AI думает это *{movie_title}*, но не найдено.", parse_mode="Markdown")
            return
        await thinking.edit_text(f"🤖 AI думает это *{movie_title}*! Вот варианты:", parse_mode="Markdown")
        await show_search_results(message, movies)

    else:
        # Сначала ищем фильм по названию
        movies = await search_movies_by_title(text)
        if movies:
            await show_search_results(message, movies)
        else:
            # Если не нашли — ищем актёра
            await search_person(message, text)

async def show_search_results(message, movies):
    text = "🔍 *Результаты поиска — нажми чтобы открыть:*\n\n"
    buttons = []
    for m in movies:
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        rating = round(m.get("vote_average", 0), 1)
        movie_id = m.get("id")
        text += f"• *{title}* ({year}) — ⭐{rating}/10\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {title} ({year})", callback_data=f"film:{movie_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def show_top(message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/popular",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    text = "🔥 *Топ популярных фильмов:*\n\n"
    buttons = []
    for i, m in enumerate(movies, 1):
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        rating = round(m.get("vote_average", 0), 1)
        movie_id = m.get("id")
        text += f"{i}. *{title}* ({year}) — ⭐{rating}/10\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {title}", callback_data=f"film:{movie_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def show_new(message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/now_playing",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    text = "🆕 *Новинки в кино:*\n\n"
    buttons = []
    for i, m in enumerate(movies, 1):
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        rating = round(m.get("vote_average", 0), 1)
        movie_id = m.get("id")
        text += f"{i}. *{title}* ({year}) — ⭐{rating}/10\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {title}", callback_data=f"film:{movie_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def show_upcoming(message):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/upcoming",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    movies = data.get("results", [])[:10]
    text = "🎬 *Скоро в кино:*\n\n"
    buttons = []
    for i, m in enumerate(movies, 1):
        title = m.get("title", "—")
        date = m.get("release_date", "—")
        rating = round(m.get("vote_average", 0), 1)
        movie_id = m.get("id")
        text += f"{i}. *{title}* — 📅 {date}\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {title}", callback_data=f"film:{movie_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def search_person(message, query):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/search/person",
            params={"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU"}) as r:
            data = await r.json()
    results = data.get("results", [])
    if not results:
        await message.answer(
            "❌ Ничего не найдено.\n\nПопробуй:\n• ID: `572802`\n• Название: `Интерстеллар`\n• Актёр: `Tom Hanks`\n• Описание сцены",
            parse_mode="Markdown"
        )
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
    text = f"🎭 *{name}*\n📌 {known_for}\n\n🎬 *Нажми на фильм:*\n\n"
    buttons = []
    for m in movies:
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        movie_id = m.get("id")
        rating = round(m.get("vote_average", 0), 1)
        text += f"• *{title}* ({year}) — ⭐{rating}/10\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {title} ({year})", callback_data=f"film:{movie_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def post_to_channel(movie_id, title, year, rating, overview, poster, q):
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Получить в боте", url=f"https://t.me/CINEMATR1X_BOT?start={movie_id}")],
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Похожие", callback_data=f"sim:{movie_id}"),
            InlineKeyboardButton(text="👥 Актёры", callback_data=f"cast:{movie_id}")
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
    text = "🎬 *Похожие фильмы:*\n\n"
    buttons = []
    for m in results:
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        rating = round(m.get("vote_average", 0), 1)
        movie_id = m.get("id")
        text += f"• *{title}* ({year}) — ⭐{rating}/10\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {title}", callback_data=f"film:{movie_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
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
    text = f"🎭 *{name}*\n\n🎬 *Фильмы:*\n\n"
    buttons = []
    for m in movies:
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        movie_id = m.get("id")
        rating = round(m.get("vote_average", 0), 1)
        text += f"• *{title}* ({year}) — ⭐{rating}/10\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {title} ({year})", callback_data=f"film:{movie_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())