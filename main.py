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
TMDB_URL = "https://api.themoviedb.org/3"

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
        "Отправь мне ID фильма — например: `572802`\n"
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
    else:
        await message.answer("Введи ID фильма числом. Например: `572802`", parse_mode="Markdown")

async def show_film(message, movie_id):
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
            InlineKeyboardButton(text="🎥 Filmix", url=f"https://filmix.ac/search/{q}"),
            InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.best/?do=search&subaction=search&story={q}")
        ]
    ])

    text = f"🎬 *{title}* ({year})\n\n⭐ Рейтинг: {rating}/10\n\n📝 {overview}"

    if poster:
        await message.answer_photo(
            f"https://image.tmdb.org/t/p/w500{poster}",
            caption=text,
            parse_mode="Markdown",
            reply_markup=kb
        )
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)

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
        async with session.get(
            f"{TMDB_URL}/movie/{movie_id}/similar",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}
        ) as r:
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
        async with session.get(
            f"{TMDB_URL}/movie/{movie_id}/credits",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"}
        ) as r:
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