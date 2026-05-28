import asyncio
import aiohttp
import urllib.parse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TMDB_URL = "https://api.themoviedb.org/3"
CHANNEL = "@thebobodjonov"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

CHANNELS = [
    {"name": "Бободжонов", "username": "@thebobodjonov", "url": "https://t.me/thebobodjonov"},
]

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
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 200,
                "messages": [{
                    "role": "user",
                    "content": f"""Пользователь описывает фильм. Определи название фильма.
Описание: {description}

Ответь ТОЛЬКО названием фильма на английском языке, ничего больше. Например: "Inception" или "The Dark Knight". Если не знаешь — напиши "unknown"."""
                }]
            }
        ) as r:
            data = await r.json()
            return data["content"][0]["text"].strip().strip('"')

async def search_movie_by_title(title):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{TMDB_URL}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": title, "language": "ru-RU"}
        ) as r:
            data = await r.json()
    results = data.get("results", [])
    return results[0] if results else None

@dp.message(Command("start"))
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎬 Открыть CINEMATRIX",
            web_app=types.WebAppInfo(url="https://voluble-croissant-d09014.netlify.app")
        )
    ]])
    await message.answer(
        "🎬 Добро пожаловать в CINEMATRIX!\n\n"
        "📌 Как пользоваться:\n"
        "🔢 *ID фильма* — например: `572802`\n"
        "🎭 *Имя актёра* — например: `Tom Hanks`\n"
        "🤖 *Опиши сцену* — например: `фильм где человек застрял на острове один`\n\n"
        "Или нажми кнопку 👇",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message()
async def handle(message: types.Message):
    text = message.text.strip()

    if text.isdigit():
        not_subbed = await check_sub(message.from_user.id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check:{text}")]])
            await message.answer("📢 Подпишись на канал и нажми кнопку!", reply_markup=kb)
        else:
            await show_film(message, int(text))

    elif len(text) > 15:
        # Длинный текст — AI поиск по описанию
        thinking = await message.answer("🤖 AI ищет фильм по описанию...")
        movie_title = await ai_find_movie(text)

        if movie_title == "unknown":
            await thinking.edit_text("❌ AI не смог определить фильм. Попробуй описать подробнее!")
            return

        movie = await search_movie_by_title(movie_title)
        if not movie:
            await thinking.edit_text(f"🤖 AI думает это *{movie_title}*, но фильм не найден в базе.", parse_mode="Markdown")
            return

        await thinking.edit_text(f"🤖 AI думает это *{movie_title}*!", parse_mode="Markdown")

        not_subbed = await check_sub(message.from_user.id)
        if not_subbed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed
            ] + [[InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check:{movie['id']}")]])
            await message.answer("📢 Подпишись на канал чтобы увидеть фильм!", reply_markup=kb)
        else:
            await show_film(message, movie["id"])

    else:
        # Короткий текст — поиск актёра
        await search_person(message, text)

async def search_person(message, query):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{TMDB_URL}/search/person",
            params={"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU"}
        ) as r:
            data = await r.json()

    results = data.get("results", [])
    if not results:
        await message.answer(
            "❌ Актёр не найден.\n\nПопробуй:\n• Написать имя на английском: `Tom Hanks`\n• Или описать фильм подробнее (больше 15 символов)",
            parse_mode="Markdown"
        )
        return

    person = results[0]
    person_id = person["id"]
    name = person.get("name", "—")
    known_for = person.get("known_for_department", "—")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{TMDB_URL}/person/{person_id}/movie_credits",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}
        ) as r:
            credits = await r.json()

    movies = sorted(credits.get("cast", []), key=lambda x: x.get("popularity", 0), reverse=True)[:8]

    text = f"🎭 *{name}*\n📌 {known_for}\n\n🎬 *Известные фильмы:*\n\n"
    for m in movies:
        title = m.get("title", "—")
        year = m.get("release_date", "")[:4]
        movie_id = m.get("id")
        rating = round(m.get("vote_average", 0), 1)
        text += f"• *{title}* ({year}) — ⭐{rating}/10\n🆔 `{movie_id}`\n\n"

    await message.answer(text, parse_mode="Markdown")

async def post_to_channel(movie_id, title, year, rating, overview, poster, q):
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Получить в боте", url=f"https://t.me/CINEMATR1X_BOT?start={movie_id}")],
            [
                InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
                InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}")
            ]
        ])
        text = (
            f"🎬 *{title}* ({year})\n\n"
            f"⭐ Рейтинг: {rating}/10\n\n"
            f"📝 {overview}\n\n"
            f"🆔 Код фильма: `{movie_id}`"
        )
        if poster:
            await bot.send_photo(CHANNEL, f"https://image.tmdb.org/t/p/w500{poster}", caption=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await bot.send_message(CHANNEL, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        print(f"Ошибка постинга: {e}")

async def show_film(message, movie_id, post_channel=True):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{TMDB_URL}/movie/{movie_id}",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}
        ) as r:
            m = await r.json()

    if not m.get("title"):
        await message.answer("❌ Фильм не найден. Проверь ID.")
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
        async with session.get(f"{TMDB_URL}/movie/{movie_id}/similar", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    results = data.get("results", [])[:5]
    if not results:
        await callback.answer("Похожих не найдено", show_alert=True)
        return
    text = "🎬 *Похожие фильмы:*\n\n"
    for m in results:
        text += f"• *{m['title']}* ({m.get('release_date','')[:4]}) — ⭐{m.get('vote_average',0)}/10\n🆔 `{m['id']}`\n\n"
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cast:"))
async def cast(callback: types.CallbackQuery):
    movie_id = callback.data.split(":")[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_URL}/movie/{movie_id}/credits", params={"api_key": TMDB_API_KEY, "language": "ru-RU"}) as r:
            data = await r.json()
    actors = data.get("cast", [])[:5]
    if not actors:
        await callback.answer("Актёры не найдены", show_alert=True)
        return
    text = "👥 *Актёры:*\n\n"
    for a in actors:
        text += f"• *{a['name']}* — {a.get('character', '')}\n"
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())