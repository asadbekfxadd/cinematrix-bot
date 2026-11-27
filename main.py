"""FILMIX bot v2 — aiogram 3 + asyncpg.

Модули:
  config.py   — настройки и переменные окружения
  texts.py    — тексты RU/UZ (HTML)
  db.py       — PostgreSQL (асинхронный пул)
  services.py — TMDb, Claude, кэши
  main.py     — хендлеры (этот файл)
"""

import asyncio
import html
import logging
import random
import re
import urllib.parse
from datetime import datetime, timedelta

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, CallbackQuery, ChatMemberUpdated, ErrorEvent, InlineKeyboardButton, InlineKeyboardMarkup,
                           InlineQuery, InlineQueryResultArticle, InputMediaPhoto, InputTextMessageContent,
                           KeyboardButton, LabeledPrice, LinkPreviewOptions, Message, PreCheckoutQuery,
                           ReplyKeyboardMarkup, WebAppInfo)
from cachetools import TTLCache

import db
import services as api
from config import (ADMIN_IDS, BOT_TOKEN, BOT_USERNAME, FREE_AI_PER_DAY, MINI_APP_URL, MORNING_FROM_HOUR,
                    MORNING_TO_HOUR, PREMIUM_MONTH_STARS, PREMIUM_WEEK_STARS,
                    OWN_CAPTION, PROTECT_CONTENT, SCAN_CHAT_ID, TMDB_IMG, TZ,
                    VIDEO_CHANNEL_ID, now_local)
from texts import TEXTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("filmix")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Кэши в памяти с автоочисткой (раньше search_cache рос бесконечно)
search_cache = TTLCache(maxsize=50_000, ttl=60 * 60)   # карточки поиска, квизы, отложенные deep-link
sub_ok_cache = TTLCache(maxsize=100_000, ttl=5 * 60)   # кто уже подписан — не проверяем 5 минут
channels_cache = TTLCache(maxsize=1, ttl=60)


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=False)


def tr(user_id, key, *args):
    """Текст на языке пользователя. Аргументы экранируются — названия фильмов больше не ломают сообщения."""
    lang = db.get_lang(user_id)
    text = TEXTS[lang].get(key, TEXTS["ru"].get(key, key))
    if args:
        try:
            return text.format(*[esc(a) for a in args])
        except (IndexError, KeyError):
            return text
    return text


def is_admin(user_id) -> bool:
    return user_id in ADMIN_IDS


def img(path) -> str:
    if not path:
        return ""
    return path if str(path).startswith("http") else f"{TMDB_IMG}{path}"


def year_of(m) -> str:
    return (m.get("release_date", "") or "")[:4]


def get_menu(user_id):
    tx = TEXTS[db.get_lang(user_id)]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tx["top"]), KeyboardButton(text=tx["new"]), KeyboardButton(text=tx["upcoming"])],
            [KeyboardButton(text=tx["uzbek"]), KeyboardButton(text=tx["tv_shows"]), KeyboardButton(text=tx["favorites"])],
            [KeyboardButton(text=tx["quiz"]), KeyboardButton(text=tx["recommend"]), KeyboardButton(text=tx["invite"])],
            [KeyboardButton(text="🎬 FILMIX App", web_app=WebAppInfo(url=MINI_APP_URL)),
             KeyboardButton(text=tx["premium"])],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# Кнопка меню на любом языке → действие
MENU_ACTIONS = {}
for _lang in TEXTS.values():
    for _key in ("top", "new", "upcoming", "uzbek", "tv_shows", "favorites", "quiz", "recommend", "invite", "premium"):
        MENU_ACTIONS[_lang[_key]] = _key

LANG_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
    InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
]])


# ===== MIDDLEWARE =====
class ThrottleMiddleware(BaseMiddleware):
    """Антифлуд: не больше одного сообщения в 0.6 сек от пользователя."""

    def __init__(self, rate: float = 0.6):
        self.seen = TTLCache(maxsize=100_000, ttl=rate)

    async def __call__(self, handler, event: Message, data):
        uid = event.from_user.id if event.from_user else None
        if uid and not is_admin(uid) and not event.successful_payment:
            if uid in self.seen:
                return None
            self.seen[uid] = True
        return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Обновляет пользователя в БД и подгружает его язык до хендлера."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            if isinstance(event, Message) and not (event.text or "").startswith("/start"):
                await db.upsert_user(user.id, user.username, user.first_name)
            else:
                await db.load_lang(user.id)
        return await handler(event, data)


dp.message.outer_middleware(ThrottleMiddleware())
dp.message.outer_middleware(UserMiddleware())
dp.callback_query.outer_middleware(UserMiddleware())
dp.inline_query.outer_middleware(UserMiddleware())


# ===== ПОДПИСКА =====
async def get_channels_cached():
    if "all" not in channels_cache:
        channels_cache["all"] = await db.get_channels()
    return channels_cache["all"]


async def check_sub(user_id):
    """Список каналов, на которые пользователь НЕ подписан (пусто = всё ок)."""
    if is_admin(user_id) or user_id in sub_ok_cache or await db.has_bonus(user_id) or await db.has_premium(user_id):
        return []
    not_subbed = []
    for ch in await get_channels_cached():
        try:
            member = await bot.get_chat_member(ch["username"], user_id)
            if member.status in ("left", "kicked"):
                not_subbed.append(ch)
        except Exception as e:
            log.warning("get_chat_member %s failed: %s", ch["username"], e)
            not_subbed.append(ch)
    if not not_subbed:
        sub_ok_cache[user_id] = True
    return not_subbed


def sub_keyboard(user_id, not_subbed, callback_data):
    rows = [[InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"])] for ch in not_subbed]
    rows.append([InlineKeyboardButton(text=tr(user_id, "check_sub"), callback_data=callback_data)])
    rows.append([InlineKeyboardButton(text=tr(user_id, "skip_sub_premium"), callback_data="premium")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def require_sub(message: Message, user_id, callback_data, text_key="subscribe") -> bool:
    """True — можно продолжать. False — показали кнопки подписки."""
    not_subbed = await check_sub(user_id)
    if not_subbed:
        await message.answer(tr(user_id, text_key), reply_markup=sub_keyboard(user_id, not_subbed, callback_data))
        return False
    return True


# ===== БЕЗОПАСНАЯ ОТПРАВКА (рассылки) =====
async def safe_send(user_id, coro_factory) -> bool:
    """Отправка с обработкой лимитов Telegram и пометкой заблокировавших бота."""
    for attempt in range(2):
        try:
            await coro_factory()
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            await db.mark_blocked(user_id)
            return False
        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower():
                await db.mark_blocked(user_id)
            return False
        except Exception as e:
            log.warning("send to %s failed: %s", user_id, e)
            return False
    return False


async def broadcast_all(make_coro):
    """make_coro(uid) -> корутина отправки. ~25 сообщений/сек, чтобы не ловить 429."""
    sent = failed = 0
    for uid in await db.get_active_users():
        if await safe_send(uid, lambda: make_coro(uid)):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.04)
    return sent, failed


async def answer_photo_or_text(message: Message, photo, text, kb):
    if photo:
        try:
            await message.answer_photo(photo, caption=text[:1024], reply_markup=kb)
            return
        except TelegramBadRequest as e:
            log.info("photo failed, fallback to text: %s", e)
    await message.answer(text, reply_markup=kb)


# ===== КАРТОЧКИ =====
def kind_of(m) -> str:
    return "tv" if m.get("is_tv") else "movie"


def movie_card_text(m, index, total, user_id):
    rating = round(m.get("vote_average", 0) or 0, 1)
    overview = (m.get("overview", "") or tr(user_id, "no_desc"))[:200]
    icon = "📺" if m.get("is_tv") else "🎬"
    return (f"{icon} <b>{esc(m.get('title', '—'))}</b> ({esc(year_of(m))})\n"
            f"{tr(user_id, 'rating', rating)}\n"
            f"🆔 <code>{esc(m.get('id'))}</code>\n\n"
            f"📝 {esc(overview)}...\n\n"
            f"<i>{index}/{total}</i>")


def watch_buttons(title):
    q = urllib.parse.quote(title or "")
    return [
        InlineKeyboardButton(text="▶️ Rezka", url=f"https://rezka.ag/search/?do=search&subaction=search&q={q}"),
        InlineKeyboardButton(text="📺 Kinogo", url=f"https://kinogo.is/?do=search&subaction=search&story={q}"),
    ]


async def movie_card_keyboard(movies, index, source, user_id):
    m = movies[index]
    movie_id, kind, total = m.get("id"), kind_of(m), len(movies)
    fav = await db.is_favorited(user_id, movie_id)
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"card:{source}:{index - 1}"))
    nav.append(InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"))
    if index < total - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"card:{source}:{index + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [InlineKeyboardButton(text=tr(user_id, "open_film"), callback_data=f"film:{kind}:{movie_id}"),
         InlineKeyboardButton(text=tr(user_id, "unfav_btn" if fav else "fav_btn"),
                              callback_data=f"fav:{kind}:{movie_id}")],
        watch_buttons(m.get("title", "")),
    ])


async def send_card(message: Message, movies, index, source, user_id, edit=False):
    m = movies[index]
    poster = img(m.get("poster_path"))
    text = movie_card_text(m, index + 1, len(movies), user_id)
    kb = await movie_card_keyboard(movies, index, source, user_id)
    if edit:
        try:
            if poster:
                await message.edit_media(InputMediaPhoto(media=poster, caption=text), reply_markup=kb)
            elif message.photo:
                await message.edit_caption(caption=text, reply_markup=kb)
            else:
                await message.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return
    await answer_photo_or_text(message, poster, text, kb)


async def show_list(message: Message, user_id, key, movies, title_key=None):
    if title_key:
        await message.answer(tr(user_id, title_key))
    if not movies:
        await message.answer(tr(user_id, "not_found"))
        return
    source = f"{user_id}_{key}"
    search_cache[source] = movies
    await send_card(message, movies, 0, source, user_id)


# ===== КАРТОЧКА ФИЛЬМА =====
async def render_film_card(message: Message, user_id, m, movie_id, is_tv):
    kind = "tv" if is_tv else "movie"
    title = m.get("title", "—")
    rating = round(m.get("vote_average", 0) or 0, 1)
    overview = m.get("overview", "") or ""
    if db.get_lang(user_id) == "uz" and overview:
        overview = await api.translate_to_uz(overview)
    overview = overview or tr(user_id, "no_desc")
    fav = await db.is_favorited(user_id, movie_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr(user_id, "similar"), callback_data=f"sim:{kind}:{movie_id}"),
         InlineKeyboardButton(text=tr(user_id, "actors"), callback_data=f"cast:{kind}:{movie_id}")],
        [InlineKeyboardButton(text=tr(user_id, "unfav_btn" if fav else "fav_btn"),
                              callback_data=f"fav:{kind}:{movie_id}"),
         InlineKeyboardButton(text=tr(user_id, "share"), switch_inline_query=title)],
        watch_buttons(title),
    ])
    text = (f"{tr(user_id, 'series' if is_tv else 'film')}\n🎬 <b>{esc(title)}</b> ({esc(year_of(m))})\n\n"
            f"{tr(user_id, 'rating', rating)}\n\n📝 {esc(overview)}")
    await answer_photo_or_text(message, img(m.get("poster_path")), text, kb)


async def fetch_title(kind, movie_id):
    m = await api.tmdb(f"/{kind}/{movie_id}")
    if kind == "tv" and m.get("name"):
        return api.normalize_tv(dict(m))
    return m if m.get("title") else None


async def show_film(message: Message, user_id, movie_id, kind=None):
    """kind известен → сразу карточка. Неизвестен (ввели число) → проверяем фильм и сериал."""
    if kind in ("movie", "tv"):
        m = await fetch_title(kind, movie_id)
        if m:
            await render_film_card(message, user_id, m, movie_id, kind == "tv")
        else:
            await message.answer(tr(user_id, "film_not_found"))
        return
    movie, tv = await asyncio.gather(fetch_title("movie", movie_id), fetch_title("tv", movie_id))
    if movie and tv:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"🎬 {movie['title']} ({year_of(movie)})", callback_data=f"pick:movie:{movie_id}"),
            InlineKeyboardButton(text=f"📺 {tv['title']} ({year_of(tv)})", callback_data=f"pick:tv:{movie_id}"),
        ]])
        await message.answer(tr(user_id, "pick_prompt", movie_id), reply_markup=kb)
    elif movie:
        await render_film_card(message, user_id, movie, movie_id, False)
    elif tv:
        await render_film_card(message, user_id, tv, movie_id, True)
    else:
        await message.answer(tr(user_id, "film_not_found"))


async def custom_film_buttons(user_id, film):
    code, row = film["code"], []
    if code.isdigit():
        fav = await db.is_favorited(user_id, int(code))
        row.append(InlineKeyboardButton(text=tr(user_id, "unfav_btn" if fav else "fav_btn"),
                                        callback_data=f"fav:movie:{code}"))
    row.append(InlineKeyboardButton(text=tr(user_id, "share"), switch_inline_query=film["title"] or code))
    return row


def film_caption(user_id, film) -> str:
    """Своя подпись под видео вместо подписи из канала (чужая реклама не уходит пользователю)."""
    parts = [f"🎬 <b>{esc(film['title'])}</b>" + (f" ({esc(film['year'])})" if film.get("year") else "")]
    if film.get("rating"):
        parts.append(tr(user_id, "rating", round(float(film["rating"]), 1)))
    if film.get("description"):
        parts.append(f"\n📝 {esc(film['description'][:400])}")
    parts.append(f"\n🆔 Код: <code>{esc(film['code'])}</code>\n🍿 @{BOT_USERNAME}")
    return "\n".join(parts)[:1024]


async def send_channel_video(user_id, film) -> bool:
    """Копирует видео из канала пользователю (без подписи «переслано из»)."""
    if not (film.get("channel_message_id") and VIDEO_CHANNEL_ID):
        return False
    try:
        await bot.copy_message(user_id, VIDEO_CHANNEL_ID, film["channel_message_id"],
                               caption=film_caption(user_id, film) if OWN_CAPTION else None,
                               protect_content=PROTECT_CONTENT,
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[await custom_film_buttons(user_id, film)]))
        return True
    except TelegramBadRequest as e:
        log.warning("copy video %s (msg %s) failed: %s", film["code"], film["channel_message_id"], e)
        return False


async def show_custom_film(message: Message, user_id, film):
    # Есть видео в канале → сразу отдаём само видео
    if await send_channel_video(user_id, film):
        return
    code = film["code"]
    buttons = []
    if film.get("channel_message_id"):
        buttons.append([InlineKeyboardButton(text=tr(user_id, "watch_video"), callback_data=f"getvideo:{code}")])
    elif film.get("watch_url"):
        buttons.append([InlineKeyboardButton(text=tr(user_id, "watch"), url=film["watch_url"])])
    buttons.append(await custom_film_buttons(user_id, film))
    text = (f"🎬 <b>{esc(film['title'])}</b> ({esc(film['year'])})\n\n"
            f"📝 {esc(film['description'] or tr(user_id, 'no_desc'))}\n\n🆔 Код: <code>{esc(code)}</code>")
    await answer_photo_or_text(message, film.get("poster"), text, InlineKeyboardMarkup(inline_keyboard=buttons))


async def open_target(message: Message, user_id, kind, value):
    """Открывает фильм из deep-link/кнопки после проверки подписки.
    kind: movie | tv | auto (число без типа) | custom (свой код)."""
    if not await require_sub(message, user_id, f"open:{kind}:{value}"):
        return
    if kind == "custom":
        film = await db.get_custom_film(value)
        if film:
            await show_custom_film(message, user_id, film)
        else:
            await message.answer(tr(user_id, "film_not_found"))
        return
    if kind == "auto":
        film = await db.get_custom_film(value)
        if film:
            await show_custom_film(message, user_id, film)
            return
    await show_film(message, user_id, int(value), None if kind == "auto" else kind)


# ===== УТРЕННЯЯ РАССЫЛКА =====
async def morning_broadcast():
    """Раз в день «фильм дня» в случайное время окна (по Ташкенту). Повторно после рестарта не шлёт."""
    def pick_time(day, earliest):
        start = day.replace(hour=MORNING_FROM_HOUR, minute=0, second=0, microsecond=0)
        end = day.replace(hour=MORNING_TO_HOUR, minute=59, second=0, microsecond=0)
        lo = max(start, earliest)
        return lo + timedelta(seconds=random.uniform(0, max((end - lo).total_seconds(), 0)))

    while True:
        try:
            now = now_local()
            window_end = now.replace(hour=MORNING_TO_HOUR, minute=59, second=0, microsecond=0)
            sent_today = await db.kv_get("morning_last") == now.strftime("%Y-%m-%d")
            if not sent_today and now < window_end:
                run_at = pick_time(now, now)
            else:
                run_at = pick_time(now + timedelta(days=1), now)
            log.info("Morning broadcast scheduled at %s", run_at)
            await asyncio.sleep(max(1, (run_at - now_local()).total_seconds()))

            movies = (await api.tmdb("/movie/popular", page=random.randint(1, 5))).get("results", [])
            if not movies:
                await asyncio.sleep(600)
                continue
            m = random.choice(movies)
            movie_id, poster = m.get("id"), img(m.get("poster_path"))
            args = (m.get("title", "—"), year_of(m), round(m.get("vote_average", 0) or 0, 1),
                    (m.get("overview", "") or "")[:200], movie_id)
            await db.kv_set("morning_last", run_at.strftime("%Y-%m-%d"))

            def make(uid):
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=tr(uid, "open_film"), callback_data=f"film:movie:{movie_id}")]])
                text = tr(uid, "morning_msg", *args)
                if poster:
                    return bot.send_photo(uid, poster, caption=text[:1024], reply_markup=kb)
                return bot.send_message(uid, text, reply_markup=kb)

            sent, failed = await broadcast_all(make)
            log.info("Morning broadcast done: sent=%s failed=%s", sent, failed)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Morning broadcast error")
            await asyncio.sleep(600)


# ===== /start и язык =====
async def parse_start_payload(payload: str):
    """Возвращает (ref_id, target). target = (kind, value) или None.
    Новые ссылки: r123 — реферал, m123 — фильм, t123 — сериал, cКОД — свой фильм.
    Старые ссылки с голым числом тоже работают: если такой пользователь есть — реферал, иначе фильм."""
    if not payload:
        return None, None
    if payload[0] == "r" and payload[1:].isdigit():
        return int(payload[1:]), None
    if payload[0] in "mt" and payload[1:].isdigit():
        return None, ("movie" if payload[0] == "m" else "tv", payload[1:])
    if payload[0] == "c" and len(payload) > 1:
        return None, ("custom", payload[1:])
    if payload.isdigit():
        if await db.user_exists(int(payload)):
            return int(payload), None
        return None, ("auto", payload)
    return None, None


@dp.message(CommandStart())
async def start(message: Message, command: CommandObject):
    user = message.from_user
    ref_id, target = await parse_start_payload((command.args or "").strip())
    is_new, referred = await db.upsert_user(user.id, user.username, user.first_name, ref_id)
    if referred:
        count = await db.get_referral_count(ref_id)
        await db.load_lang(ref_id)
        await safe_send(ref_id, lambda: bot.send_message(ref_id, tr(ref_id, "new_user", count)))
    if target and not is_new:
        await open_target(message, user.id, *target)
        return
    if target:
        search_cache[f"pending_{user.id}"] = target
    await message.answer(tr(user.id, "choose_lang"), reply_markup=LANG_KB)


@dp.message(Command("lang"))
async def lang_cmd(message: Message):
    await message.answer(tr(message.from_user.id, "choose_lang"), reply_markup=LANG_KB)


@dp.callback_query(F.data.startswith("lang:"))
async def lang_callback(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    uid = callback.from_user.id
    await db.set_lang(uid, lang)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🎬 Открыть FILMIX App" if lang == "ru" else "🎬 FILMIX App ni ochish",
        web_app=WebAppInfo(url=MINI_APP_URL))]])
    await callback.message.answer(tr(uid, "welcome"), reply_markup=get_menu(uid))
    await callback.message.answer(tr(uid, "choose_section"), reply_markup=kb)
    await callback.answer()
    pending = search_cache.pop(f"pending_{uid}", None)
    if pending:
        await open_target(callback.message, uid, *pending)


@dp.message(Command("stats"))
async def stats(message: Message):
    total, today, requests, referrals, _ = await db.get_stats()
    ref = await db.get_referral_count(message.from_user.id)
    await message.answer(tr(message.from_user.id, "stats", total, today, requests, referrals, ref))


# ===== АДМИНКА =====
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(tr(message.from_user.id, "no_access"))
        return
    total, today, requests, referrals, blocked = await db.get_stats()
    prem_active, stars_total, stars_month = await db.premium_stats()
    await message.answer(
        "👑 <b>Админ панель FILMIX</b>\n\n"
        f"⭐ Premium активных: <b>{prem_active}</b>\n"
        f"💰 Звёзд за 30 дней: <b>{stars_month}</b> · всего: <b>{stars_total}</b>\n\n"
        f"👥 Пользователей: <b>{total}</b>\n🔥 Сегодня: <b>{today}</b>\n"
        f"🔍 Запросов: <b>{requests}</b>\n🔗 Рефералов: <b>{referrals}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n\n"
        "📤 <code>/post ID</code> — постинг в канал\n"
        "📢 <code>/broadcast текст</code> — рассылка\n"
        "📢 Ответь <code>/broadcast</code> на любое сообщение (фото/видео) — разошлю его копию\n\n"
        "🎬 <b>Своя база фильмов:</b>\n"
        "➕ <code>/addfilm КОД | Название | Год | Описание | Постер | Ссылка</code>\n"
        "➖ <code>/deletefilm КОД</code> — удалить фильм\n"
        "🎥 <code>/addvideo КОД MESSAGE_ID</code> — привязать видео из канала\n"
        "📥 Видео в канале добавляются сами (код из подписи «Код: 245» или автоматически).\n"
        "   Старые посты — просто перешли их боту (можно пачкой).\n"
        "🔄 <code>/scan</code> — пройти ВЕСЬ канал и добавить все фильмы с новыми кодами\n"
        "   <code>/scan 100 500</code> — только посты 100–500 · <code>/scan keep</code> — коды из подписей\n"
        "   <code>/scan continue</code> · <code>/scan stop</code> · <code>/scan status</code>\n"
        "📋 <code>/myfilms</code> — список фильмов\n\n"
        "📋 <code>/channels</code> — каналы\n"
        "➕ <code>/addchannel @ch Название</code>\n"
        "➖ <code>/removechannel @ch</code>\n\n"
        "⭐ <b>Premium:</b>\n"
        "🎁 <code>/givepremium USER_ID ДНЕЙ</code> — выдать вручную\n"
        "↩️ <code>/refund CHARGE_ID</code> — вернуть звёзды (ID приходит в уведомлении об оплате)")


@dp.message(Command("channels"))
async def list_channels(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(tr(message.from_user.id, "no_access"))
    channels = await db.get_channels()
    if not channels:
        return await message.answer("📋 Каналов нет.")
    text = "📋 <b>Каналы для проверки подписки:</b>\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. <b>{esc(ch['name'])}</b>\n<code>{esc(ch['username'])}</code>\n\n"
    text += "➕ <code>/addchannel @username Название</code>\n➖ <code>/removechannel @username</code>"
    await message.answer(text)


@dp.message(Command("addchannel"))
async def add_channel_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer(tr(message.from_user.id, "no_access"))
    args = (command.args or "").split()
    if len(args) < 2:
        return await message.answer("❌ Используй:\n<code>/addchannel @username Название</code>")
    username, name = args[0], " ".join(args[1:])
    url = f"https://t.me/{username[1:]}" if username.startswith("@") else f"https://t.me/joinchat/{username}"
    if await db.db_add_channel(username, name, url):
        channels_cache.clear()
        sub_ok_cache.clear()
        await message.answer(f"✅ Канал <b>{esc(name)}</b> добавлен!")
    else:
        await message.answer(f"❌ Канал <code>{esc(username)}</code> уже существует.")


@dp.message(Command("removechannel"))
async def remove_channel_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer(tr(message.from_user.id, "no_access"))
    username = (command.args or "").strip()
    if not username:
        return await message.answer("❌ Используй: <code>/removechannel @username</code>")
    if await db.db_remove_channel(username):
        channels_cache.clear()
        await message.answer(f"✅ Канал <code>{esc(username)}</code> удалён!")
    else:
        await message.answer(f"❌ Канал <code>{esc(username)}</code> не найден.")


@dp.message(Command("addfilm"))
async def addfilm_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Нет доступа.")
    parts = [p.strip() for p in (command.args or "").split("|")]
    if len(parts) < 4:
        return await message.answer(
            "❌ Формат:\n<code>/addfilm КОД | Название | Год | Описание | Постер_URL | Ссылка</code>\n\n"
            "Пример:\n<code>/addfilm 12345 | Оппенгеймер | 2023 | Описание | https://poster.jpg | https://...</code>\n\n"
            "Постер и ссылка необязательны.")
    code, title, year, description = parts[:4]
    poster = parts[4] if len(parts) > 4 else ""
    watch_url = parts[5] if len(parts) > 5 else ""
    if await db.add_custom_film(code, title, year, description, poster, watch_url):
        text = f"✅ Фильм добавлен!\n\n🎬 <b>{esc(title)}</b> ({esc(year)})\n🆔 Код: <code>{esc(code)}</code>"
        if watch_url:
            text += f"\n🔗 Ссылка: {esc(watch_url)}"
        text += f"\n\n🔗 Ссылка для Reels/постов:\n<code>https://t.me/{BOT_USERNAME}?start=c{esc(code)}</code>"
        await message.answer(text)
    else:
        await message.answer("❌ Ошибка добавления.")


@dp.message(Command("deletefilm"))
async def deletefilm_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Нет доступа.")
    code = (command.args or "").strip()
    if not code:
        return await message.answer("❌ Используй: <code>/deletefilm КОД</code>")
    if await db.delete_custom_film(code):
        await message.answer(f"✅ Фильм с кодом <code>{esc(code)}</code> удалён!")
    else:
        await message.answer(f"❌ Фильм с кодом <code>{esc(code)}</code> не найден.")


@dp.message(Command("addvideo"))
async def addvideo_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Нет доступа.")
    args = (command.args or "").split()
    if len(args) != 2 or not args[1].lstrip("-").isdigit():
        return await message.answer(
            "❌ Используй: <code>/addvideo КОД MESSAGE_ID</code>\n\n"
            "Чтобы узнать MESSAGE_ID, перешли видео из канала прямо боту — он подскажет команду сам.")
    if await db.set_film_video(args[0], int(args[1])):
        await message.answer(f"✅ Видео привязано к коду <code>{esc(args[0])}</code>!")
    else:
        await message.answer(f"❌ Фильм с кодом <code>{esc(args[0])}</code> не найден. Сначала добавь через /addfilm.")


@dp.message(Command("myfilms"))
async def myfilms_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Нет доступа.")
    films = await db.get_all_custom_films()
    if not films:
        return await message.answer("📋 Своих фильмов нет.\n\nДобавь через <code>/addfilm</code>")
    text = f"📋 <b>Своя база фильмов ({len(films)} шт):</b>\n\n"
    for f in films[:30]:
        text += f"• <code>{esc(f['code'])}</code> — <b>{esc(f['title'])}</b> ({esc(f['year'])})\n"
    if len(films) > 30:
        text += f"\n<i>...и ещё {len(films) - 30} фильмов</i>"
    await message.answer(text)


@dp.message(Command("post"))
async def post_cmd(message: Message, command: CommandObject):
    uid = message.from_user.id
    if not is_admin(uid):
        return await message.answer(tr(uid, "no_access"))
    arg = (command.args or "").strip()
    if not arg.isdigit():
        return await message.answer("❌ Используй: <code>/post 872585</code>")
    await message.answer(tr(uid, "posting"))
    m = await fetch_title("movie", int(arg))
    if not m:
        return await message.answer(tr(uid, "post_error"))
    await post_to_channels(m)
    await message.answer(tr(uid, "posted", m.get("title", "—")))


async def post_to_channels(m):
    movie_id = m.get("id")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Получить в боте", url=f"https://t.me/{BOT_USERNAME}?start=m{movie_id}")],
        watch_buttons(m.get("title", "")),
    ])
    text = (f"🎬 <b>{esc(m.get('title', '—'))}</b> ({esc(year_of(m))})\n\n"
            f"⭐ Рейтинг: {round(m.get('vote_average', 0) or 0, 1)}/10\n\n"
            f"📝 {esc(m.get('overview', '') or '')}\n\n🆔 Код: <code>{movie_id}</code>")
    poster = img(m.get("poster_path"))
    for ch in await db.get_channels():
        try:
            if poster:
                await bot.send_photo(ch["username"], poster, caption=text[:1024], reply_markup=kb)
            else:
                await bot.send_message(ch["username"], text, reply_markup=kb)
        except Exception as e:
            log.warning("Post error to %s: %s", ch["username"], e)


@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message, command: CommandObject):
    uid = message.from_user.id
    if not is_admin(uid):
        return await message.answer(tr(uid, "no_access"))
    src = message.reply_to_message
    if src:
        def make(target):
            return bot.copy_message(target, src.chat.id, src.message_id)
    else:
        body = (message.html_text or "").split(maxsplit=1)
        if len(body) < 2:
            return await message.answer(tr(uid, "broadcast_usage"))
        text = f"📢 <b>FILMIX:</b>\n\n{body[1]}"

        def make(target):
            return bot.send_message(target, text)

    users = await db.get_active_users()
    status = await message.answer(tr(uid, "broadcast_sending", len(users)))

    async def run():
        sent, failed = await broadcast_all(make)
        try:
            await status.edit_text(tr(uid, "broadcast_done", sent, failed))
        except TelegramBadRequest:
            await message.answer(tr(uid, "broadcast_done", sent, failed))

    asyncio.create_task(run())  # рассылка идёт в фоне, бот продолжает отвечать


# ===== PREMIUM ЗА TELEGRAM STARS =====
PLANS = {"premium_30": (30, PREMIUM_MONTH_STARS, "invoice_month_title"),
         "premium_7": (7, PREMIUM_WEEK_STARS, "invoice_week_title")}
SUBSCRIPTION_PERIOD = 30 * 24 * 60 * 60  # Telegram допускает только 30 дней
invoice_links = TTLCache(maxsize=10, ttl=12 * 60 * 60)


def fmt_date(d) -> str:
    return d.strftime("%d.%m.%Y %H:%M") if d else "—"


async def month_invoice_link(uid) -> str:
    """Ссылка на подписку с автопродлением (одна на язык, кэшируется)."""
    lang = db.get_lang(uid)
    if lang not in invoice_links:
        invoice_links[lang] = await bot.create_invoice_link(
            title=html.unescape(tr(uid, "invoice_month_title")), description=html.unescape(tr(uid, "invoice_desc")),
            payload="premium_30", currency="XTR",
            prices=[LabeledPrice(label="Premium 30", amount=PREMIUM_MONTH_STARS)],
            subscription_period=SUBSCRIPTION_PERIOD)
    return invoice_links[lang]


async def show_premium(message: Message, uid):
    until = await db.get_premium_until(uid)
    active = until and until > now_local()
    text = tr(uid, "premium_active", fmt_date(until)) if active else tr(uid, "premium_info")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr(uid, "buy_month", PREMIUM_MONTH_STARS), url=await month_invoice_link(uid))],
        [InlineKeyboardButton(text=tr(uid, "buy_week", PREMIUM_WEEK_STARS), callback_data="buy:premium_7")],
    ])
    await message.answer(text, reply_markup=kb)


async def ai_allowed(message: Message, uid) -> bool:
    if FREE_AI_PER_DAY <= 0 or is_admin(uid) or await db.has_premium(uid):
        return True
    if await db.ai_use(uid) <= FREE_AI_PER_DAY:
        return True
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=tr(uid, "premium"), callback_data="premium")]])
    await message.answer(tr(uid, "ai_limit", FREE_AI_PER_DAY), reply_markup=kb)
    return False


@dp.message(Command("premium"))
async def premium_cmd(message: Message):
    await show_premium(message, message.from_user.id)


@dp.callback_query(F.data == "premium")
async def premium_callback(callback: CallbackQuery):
    await callback.answer()
    await show_premium(callback.message, callback.from_user.id)


@dp.callback_query(F.data.startswith("buy:"))
async def buy_callback(callback: CallbackQuery):
    uid = callback.from_user.id
    payload = callback.data.split(":", 1)[1]
    if payload not in PLANS:
        return await callback.answer()
    days, amount, title_key = PLANS[payload]
    await callback.answer()
    await bot.send_invoice(uid, title=html.unescape(tr(uid, title_key)),
                           description=html.unescape(tr(uid, "invoice_desc")), payload=payload, currency="XTR",
                           prices=[LabeledPrice(label=f"Premium {days}", amount=amount)])


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=query.invoice_payload in PLANS and query.currency == "XTR")


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    sp = message.successful_payment
    uid = message.from_user.id
    # Дату окончания считаем ДО записи платежа, чтобы ошибка не оставила оплату без Premium
    exp = sp.subscription_expiration_date
    if isinstance(exp, (int, float)):
        exp = datetime.fromtimestamp(exp, TZ)
    exact_until = exp.astimezone(TZ).replace(tzinfo=None) if exp else None
    if not await db.record_payment(uid, sp.telegram_payment_charge_id, sp.invoice_payload,
                                   sp.total_amount, bool(sp.is_recurring)):
        return  # дубль — уже начислено
    if exact_until:
        until = await db.extend_premium(uid, until=exact_until)
    else:
        until = await db.extend_premium(uid, days=PLANS.get(sp.invoice_payload, (30,))[0])
    sub_ok_cache.pop(uid, None)
    renewal = sp.is_recurring and not sp.is_first_recurring
    await message.answer(tr(uid, "premium_renewed" if renewal else "premium_thanks", fmt_date(until)))
    for admin in ADMIN_IDS:
        await safe_send(admin, lambda a=admin: bot.send_message(
            a, f"💰 <b>+{sp.total_amount} ⭐</b> от <code>{uid}</code> "
               f"({esc(message.from_user.full_name)})\n{esc(sp.invoice_payload)}"
               f"{' · продление' if renewal else ''}\n"
               f"До: {fmt_date(until)}\nCHARGE_ID: <code>{esc(sp.telegram_payment_charge_id)}</code>"))


@dp.message(Command("paysupport"))
async def paysupport_cmd(message: Message):
    await message.answer(tr(message.from_user.id, "paysupport", ADMIN_IDS[0]))


@dp.message(Command("refund"))
async def refund_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer(tr(message.from_user.id, "no_access"))
    charge_id = (command.args or "").strip()
    pay = await db.get_payment(charge_id) if charge_id else None
    if not pay:
        return await message.answer("❌ Используй: <code>/refund CHARGE_ID</code> (платёж не найден)")
    if pay["refunded"]:
        return await message.answer("ℹ️ Этот платёж уже возвращён.")
    try:
        await bot.refund_star_payment(user_id=pay["user_id"], telegram_payment_charge_id=charge_id)
    except TelegramBadRequest as e:
        return await message.answer(f"❌ Telegram отказал: {esc(e.message)}")
    await db.mark_refunded(charge_id, pay["user_id"])
    sub_ok_cache.pop(pay["user_id"], None)
    await message.answer(f"✅ Возвращено {pay['amount']} ⭐ пользователю <code>{pay['user_id']}</code>, Premium снят.")


@dp.message(Command("givepremium"))
async def givepremium_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer(tr(message.from_user.id, "no_access"))
    args = (command.args or "").split()
    if len(args) != 2 or not all(a.isdigit() for a in args):
        return await message.answer("❌ Используй: <code>/givepremium USER_ID ДНЕЙ</code>")
    target, days = int(args[0]), int(args[1])
    if not await db.user_exists(target):
        return await message.answer("❌ Такого пользователя нет в базе.")
    until = await db.extend_premium(target, days=days)
    await db.load_lang(target)
    await safe_send(target, lambda: bot.send_message(target, tr(target, "premium_thanks", fmt_date(until))))
    await message.answer(f"✅ Premium для <code>{target}</code> до {fmt_date(until)}")


# ===== АВТОЗАГРУЗКА ФИЛЬМОВ ИЗ КАНАЛА =====
CODE_RE = re.compile(r"(?:код|kod|kodi|code)\s*[:№#\-]?\s*(\d{1,10})|#(\d{1,10})\b", re.IGNORECASE)
AD_RE = re.compile(r"(https?://|t\.me/|@\w{4,}|telegram\.me)", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[2-9]\d|20[0-4]\d)\b")


def parse_caption(caption: str):
    """Из подписи поста: код, название (первая строка), год, описание.
    Код ищется как «Код: 245», «Kod 245», «Code-245» или «#245»."""
    caption = caption or ""
    m = CODE_RE.search(caption)
    code = (m.group(1) or m.group(2)) if m else None
    lines = [ln.strip() for ln in caption.splitlines() if ln.strip()]
    # выкидываем рекламные строки: ссылки, @каналы, строки из одних хэштегов
    lines = [ln for ln in lines if not AD_RE.search(ln) and not re.fullmatch(r"(#\w+\s*)+", ln)]
    content = [ln for ln in lines if not CODE_RE.search(ln) or len(CODE_RE.sub("", ln).strip(" :-|•")) > 3]
    title = ""
    if content:
        title = CODE_RE.sub("", content[0])
        title = re.sub(r"^[^\w«\"(]+", "", title).strip(" :-|•")  # срезаем эмодзи в начале
        title = YEAR_RE.sub("", title).strip(" ()[]-|•")
    y = YEAR_RE.search(caption)
    description = "\n".join(content[1:])[:700]
    return code, title[:200], (y.group(1) if y else ""), description


def is_video_post(msg: Message) -> bool:
    if msg.video:
        return True
    doc = msg.document
    return bool(doc and ((doc.mime_type or "").startswith("video/")
                         or (doc.file_name or "").lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".webm"))))


def post_thumbnail(msg: Message) -> str:
    media = msg.video or msg.document
    thumb = getattr(media, "thumbnail", None)
    return thumb.file_id if thumb else ""


async def enrich_film(title, year, caption):
    """AI чистит подпись → ищем фильм в TMDb → берём нормальное название, постер, рейтинг, описание (RU)."""
    info = await api.ai_extract_film(caption) if caption else None
    kind = (info or {}).get("type")
    y = (info or {}).get("year") or year or None
    queries = [q for q in [(info or {}).get("title_en"), (info or {}).get("title_ru"), title] if q]
    for q in dict.fromkeys(queries):
        for yr in ([y, None] if y else [None]):
            m = await api.match_tmdb(q, yr, kind)
            if m:
                return m
    return None


async def register_channel_post(msg: Message, message_id: int, caption: str, notify: bool = True,
                                new_code: bool = False, enrich: bool = True):
    """new_code=True — код из подписи игнорируется, выдаётся свой свободный (для импорта чужих постов)."""
    code, title, year, description = parse_caption(caption)
    existing = await db.get_film_by_message(message_id)
    if new_code:
        code = None
    if not code:
        code = existing["code"] if existing else await db.next_code()
    if not title:
        media = msg.video or msg.document
        title = (getattr(media, "file_name", "") or "").rsplit(".", 1)[0].replace("_", " ").replace(".", " ")
    poster, tmdb_id, rating = post_thumbnail(msg), None, None
    if enrich:
        m = await enrich_film(title, year, caption or title)
        if m:
            title = m.get("title") or title
            year = year_of(m) or year
            description = m.get("overview") or description
            poster = img(m.get("poster_path")) or poster
            tmdb_id, rating = m.get("id"), round(m.get("vote_average", 0) or 0, 1) or None
    title = title or f"Фильм {code}"
    status = await db.upsert_channel_film(code, title, year, description, poster, message_id, tmdb_id, rating)
    if notify:
        icon = "✅ Добавлен" if status == "new" else "♻️ Обновлён"
        text = (f"{icon} фильм из канала\n\n🎬 <b>{esc(title)}</b> {f'({esc(year)})' if year else ''}\n"
                f"🆔 Код: <code>{esc(code)}</code>\n"
                f"🔗 <code>https://t.me/{BOT_USERNAME}?start=c{esc(code)}</code>")
        for admin in ADMIN_IDS:
            await safe_send(admin, lambda a=admin: bot.send_message(a, text))
    return code, title, status


def is_video_channel(chat_id) -> bool:
    return bool(VIDEO_CHANNEL_ID) and str(chat_id) == str(VIDEO_CHANNEL_ID)


@dp.channel_post()
async def on_channel_post(post: Message):
    if is_video_channel(post.chat.id) and is_video_post(post):
        await register_channel_post(post, post.message_id, post.caption or "")


@dp.edited_channel_post()
async def on_channel_post_edit(post: Message):
    """Поменял подпись/код в посте — фильм в боте обновится."""
    if is_video_channel(post.chat.id) and is_video_post(post):
        await register_channel_post(post, post.message_id, post.caption or "")


@dp.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated):
    """Бота сделали админом канала — присылаем ID канала, чтобы не искать его вручную."""
    if event.chat.type != "channel" or event.new_chat_member.status != "administrator":
        return
    hint = ("✅ Это и есть канал с фильмами." if is_video_channel(event.chat.id) else
            f"Если это канал с фильмами — поставь в Railway → Variables:\n<code>VIDEO_CHANNEL_ID={event.chat.id}</code>")
    for admin in ADMIN_IDS:
        await safe_send(admin, lambda a=admin: bot.send_message(
            a, f"📢 Меня сделали админом канала <b>{esc(event.chat.title)}</b>\nID: <code>{event.chat.id}</code>\n\n{hint}"))


# ===== /scan — ОБХОД ВСЕГО КАНАЛА =====
# Боты не умеют читать историю канала, поэтому бот по очереди пересылает себе каждый пост по номеру,
# разбирает его и сразу удаляет копию. ~2-3 поста в секунду (лимиты Telegram), прогресс сохраняется.
scan_state = {"task": None, "stop": False}
SCAN_DELAY = 0.3


async def find_last_message_id() -> int:
    """Последний номер поста: бот публикует служебное сообщение без звука и тут же удаляет его."""
    m = await bot.send_message(VIDEO_CHANNEL_ID, "🔄", disable_notification=True)
    try:
        await bot.delete_message(VIDEO_CHANNEL_ID, m.message_id)
    except TelegramBadRequest:
        pass
    return m.message_id


async def fetch_post(scan_chat, mid):
    """Пересылает пост в служебный чат и возвращает его (или None, если поста нет)."""
    for _ in range(5):
        try:
            return await bot.forward_message(scan_chat, VIDEO_CHANNEL_ID, mid, disable_notification=True)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramBadRequest:
            return None  # удалён / служебный / не пересылается
    return None


async def run_scan(scan_chat, start, end, status: Message, keep_codes: bool):
    found = added = 0
    names = []
    last_edit = mid = start
    try:
        for mid in range(start, end + 1):
            if scan_state["stop"]:
                break
            post = await fetch_post(scan_chat, mid)
            if post:
                try:
                    if is_video_post(post):
                        found += 1
                        code, title, st = await register_channel_post(post, mid, post.caption or "", notify=False,
                                                                      new_code=not keep_codes)
                        if st == "new":
                            added += 1
                            names.append(f"<code>{esc(code)}</code> {esc(title[:40])}")
                except Exception:
                    log.exception("scan post %s failed", mid)
                finally:
                    try:
                        await bot.delete_message(scan_chat, post.message_id)
                    except TelegramBadRequest:
                        pass
            await asyncio.sleep(SCAN_DELAY)
            if mid - last_edit >= 25 or mid == end:
                last_edit = mid
                await db.kv_set("scan_pos", str(mid + 1))
                pct = int((mid - start + 1) * 100 / max(end - start + 1, 1))
                try:
                    await status.edit_text(f"🔄 Сканирую канал: пост {mid}/{end} ({pct}%)\n"
                                           f"🎬 Видео найдено: <b>{found}</b> · новых: <b>{added}</b>\n\n"
                                           f"Остановить: <code>/scan stop</code>")
                except TelegramBadRequest:
                    pass
    finally:
        stopped = scan_state["stop"]
        await db.kv_set("scan_pos", str(mid if stopped else end + 1))
        tail = "\n".join(names[-15:])
        more = f"\n<i>...и ещё {len(names) - 15}</i>" if len(names) > 15 else ""
        await safe_send(scan_chat, lambda: bot.send_message(
            scan_chat, ("⏸ Сканирование остановлено" if stopped else "✅ Сканирование завершено") +
            f" на посте {mid}.\n🎬 Видео: <b>{found}</b> · добавлено новых: <b>{added}</b>\n\n"
            f"{tail}{more}\n\nНовые посты потом: <code>/scan continue</code>"))
        scan_state["task"] = None


@dp.message(Command("scan"))
async def scan_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return await message.answer(tr(message.from_user.id, "no_access"))
    if not VIDEO_CHANNEL_ID:
        return await message.answer("❌ Сначала задай <code>VIDEO_CHANNEL_ID</code> в Railway → Variables "
                                    "(добавь бота админом в канал — он пришлёт ID).")
    args = (command.args or "").split()
    running = scan_state["task"] is not None and not scan_state["task"].done()
    if args[:1] == ["stop"]:
        scan_state["stop"] = True
        return await message.answer("⏸ Останавливаю..." if running else "Сканирование не запущено.")
    if args[:1] == ["status"]:
        return await message.answer(f"{'🔄 Идёт' if running else '💤 Не запущено'}. "
                                    f"Следующий пост: {await db.kv_get('scan_pos') or 1}")
    if running:
        return await message.answer("🔄 Сканирование уже идёт. <code>/scan stop</code> — остановить.")

    keep_codes = "keep" in args
    nums = [int(a) for a in args if a.isdigit()]
    try:
        last = await find_last_message_id() - 1
    except Exception as e:
        return await message.answer(f"❌ Не могу писать в канал — дай боту право публиковать сообщения.\n{esc(e)}")
    if args[:1] == ["continue"]:
        start, end = int(await db.kv_get("scan_pos") or 1), last
    else:
        start = nums[0] if nums else 1
        end = min(nums[1], last) if len(nums) > 1 else last
    if start > end:
        return await message.answer("✅ Новых постов для сканирования нет.")
    scan_chat = SCAN_CHAT_ID or message.chat.id
    minutes = max(1, round((end - start + 1) * 0.7 / 60))
    status = await message.answer(
        f"🔄 Начинаю сканировать посты {start}–{end} (~{minutes} мин).\n"
        f"Коды: {'из подписей постов' if keep_codes else 'новые свободные'} · "
        "названия, постеры и описания — из TMDb.\n\nМожно закрыть чат — пришлю итог.")
    scan_state["stop"] = False
    scan_state["task"] = asyncio.create_task(run_scan(scan_chat, start, end, status, keep_codes))


@dp.message(F.forward_origin, F.func(is_video_post))
async def forwarded_video_handler(message: Message):
    """Импорт старых постов: перешли боту видео из канала — оно добавится с кодом."""
    if not is_admin(message.from_user.id):
        return
    origin = message.forward_origin
    msg_id = getattr(origin, "message_id", None)
    chat = getattr(origin, "chat", None)
    if not msg_id:
        return await message.answer("❌ Не удалось определить пост. Перешли видео прямо из канала.")
    if chat and is_video_channel(chat.id):
        code, title, status = await register_channel_post(message, msg_id, message.caption or "", notify=False)
        icon = "✅" if status == "new" else "♻️"
        return await message.answer(f"{icon} <b>{esc(title)}</b> → код <code>{esc(code)}</code>")
    tip = (f"\n\nЧтобы видео из этого канала добавлялись сами, поставь <code>VIDEO_CHANNEL_ID={chat.id}</code>"
           if chat else "")
    await message.answer(f"📹 message_id этого видео: <code>{msg_id}</code>\n\n"
                         f"Привяжи к коду: <code>/addvideo КОД {msg_id}</code>{tip}")


# ===== MINI APP (раньше этот хендлер не срабатывал — его перехватывал общий обработчик) =====
@dp.message(F.web_app_data)
async def web_app_handler(message: Message):
    data = message.web_app_data.data.strip()
    uid = message.from_user.id
    if data.startswith(("movie:", "tv:")):
        kind, _, value = data.partition(":")
        if value.isdigit():
            return await open_target(message, uid, kind, value)
    await open_target(message, uid, "auto" if data.isdigit() else "custom", data)


# ===== РАЗДЕЛЫ МЕНЮ =====
async def menu_action(message: Message, uid, action):
    if action == "top":
        await show_list(message, uid, "top", (await api.tmdb("/movie/popular")).get("results", [])[:10])
    elif action == "new":
        await show_list(message, uid, "new", (await api.tmdb("/movie/now_playing")).get("results", [])[:10])
    elif action == "upcoming":
        await show_list(message, uid, "upcoming", (await api.tmdb("/movie/upcoming")).get("results", [])[:10])
    elif action == "uzbek":
        movies = (await api.tmdb("/discover/movie", with_origin_country="UZ",
                                 sort_by="popularity.desc")).get("results", [])[:10]
        if not movies:
            movies = (await api.search_by_title("uzbek film"))[:10]
        await show_list(message, uid, "uzbek", movies, "uzbek_films")
    elif action == "tv_shows":
        shows = [api.normalize_tv(dict(s)) for s in (await api.tmdb("/tv/popular")).get("results", [])[:10]]
        await show_list(message, uid, "tv", shows, "tv_top")
    elif action == "favorites":
        favs = await db.get_favorites(uid)
        if not favs:
            return await message.answer(tr(uid, "no_favorites"))
        await show_list(message, uid, "fav", favs)
    elif action == "quiz":
        await start_quiz(message, uid)
    elif action == "recommend":
        await message.answer(tr(uid, "recommend_prompt"))
    elif action == "premium":
        await show_premium(message, uid)
    elif action == "invite":
        link = f"https://t.me/{BOT_USERNAME}?start=r{uid}"
        await message.answer(tr(uid, "invite_text", link, await db.get_referral_count(uid)))


async def start_quiz(message: Message, uid):
    movies = [m for m in (await api.tmdb("/movie/popular")).get("results", []) if m.get("overview")]
    if len(movies) < 4:
        return
    movie = random.choice(movies)
    title = movie.get("title", "—")
    overview = (movie.get("overview", "") or "")[:300]
    if db.get_lang(uid) == "uz":
        overview = await api.translate_to_uz(overview)
    options = random.sample([m.get("title") for m in movies if m.get("title") != title], 3) + [title]
    random.shuffle(options)
    search_cache[f"quiz_{uid}"] = {"answer": title, "options": options, "movie_id": movie.get("id")}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"quiz:{i}")] for i, opt in enumerate(options)])
    await message.answer(tr(uid, "quiz_title", overview), reply_markup=kb)


async def search_person(message: Message, uid, query=None, person_id=None):
    if person_id is None:
        results = (await api.tmdb("/search/person", query=query)).get("results", [])
        if not results:
            return await message.answer(tr(uid, "not_found"))
        person_id, name = results[0]["id"], results[0].get("name", "—")
    else:
        name = (await api.tmdb(f"/person/{person_id}")).get("name", "—")
    credits = await api.tmdb(f"/person/{person_id}/movie_credits")
    movies = sorted(credits.get("cast", []), key=lambda x: x.get("popularity", 0), reverse=True)[:8]
    await message.answer(tr(uid, "actor_movies", name))
    if movies:
        await show_list(message, uid, "person", movies)


def dedupe(movies):
    seen, out = set(), []
    for m in movies:
        key = (kind_of(m), m.get("id"))
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


RECOMMEND_KW = ["посоветуй", "порекомендуй", "что посмотреть", "хочу посмотреть", "рекомендуй", "подбери",
                "подскажи", "tavsiya", "maslahat", "ko'rmoqchi"]


# ===== ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА =====
@dp.message(F.text & ~F.text.startswith("/"))
async def handle(message: Message):
    text = message.text.strip()
    uid = message.from_user.id

    action = MENU_ACTIONS.get(text)
    if action:
        return await menu_action(message, uid, action)

    if not await require_sub(message, uid, "check_only", "resubscribe"):
        return

    # Свой код фильма (из Reels/постов)
    if len(text) < 20:
        custom = await db.get_custom_film(text)
        if custom:
            return await show_custom_film(message, uid, custom)

    if text.isdigit():
        return await show_film(message, uid, int(text))

    is_ai = any(kw in text.lower() for kw in RECOMMEND_KW) or len(text) > 20
    if is_ai and not await ai_allowed(message, uid):
        return

    if any(kw in text.lower() for kw in RECOMMEND_KW):
        thinking = await message.answer(tr(uid, "ai_recommending"))
        titles = await api.ai_recommend(text)
        found = await asyncio.gather(*[api.search_by_title(t) for t in titles]) if titles else []
        unique = dedupe([m for group in found for m in group])[:5]
        if not unique:
            return await thinking.edit_text(tr(uid, "ai_not_found"))
        await thinking.edit_text(tr(uid, "ai_recommend_result"))
        search_cache[f"{uid}_rec"] = unique
        return await send_card(message, unique, 0, f"{uid}_rec", uid)

    if len(text) > 20:
        thinking = await message.answer(tr(uid, "ai_searching"))
        answer = await api.ai_find_movie(text)
        if answer.lower() == "unknown":
            return await thinking.edit_text(tr(uid, "ai_not_found"))
        titles = [t.strip() for t in answer.split(",") if t.strip()][:3]
        found = await asyncio.gather(*[api.search_by_title(t) for t in titles])
        unique = dedupe([m for group in found for m in group])[:5]
        if not unique:
            return await thinking.edit_text(tr(uid, "ai_no_result", titles[0]))
        await thinking.edit_text(tr(uid, "ai_found", titles[0]))
        search_cache[f"{uid}_search"] = unique
        return await send_card(message, unique, 0, f"{uid}_search", uid)

    custom_results = await db.search_custom_films(text, 1)
    if custom_results:
        return await show_custom_film(message, uid, custom_results[0])

    movies = await api.search_by_title(text)
    if movies:
        search_cache[f"{uid}_search"] = movies
        return await send_card(message, movies, 0, f"{uid}_search", uid)
    await search_person(message, uid, query=text)


# ===== INLINE-РЕЖИМ: @Filmix_bot название — в любом чате =====
@dp.inline_query()
async def inline_search(query: InlineQuery):
    uid = query.from_user.id
    q = query.query.strip()
    customs, items = [], []
    if len(q) >= 2:
        customs, items = await asyncio.gather(db.search_custom_films(q, 5), api.search_multi(q, 15))
    else:
        data = await api.tmdb("/trending/all/week")
        for m in data.get("results", [])[:15]:
            if m.get("media_type") == "tv":
                items.append(api.normalize_tv(dict(m)))
            elif m.get("media_type") == "movie":
                items.append(dict(m))

    results = []
    for f in customs:
        poster = f["poster"] if (f.get("poster") or "").startswith("http") else None
        text = (f"🎬 <b>{esc(f['title'])}</b> ({esc(f['year'])})\n\n📝 {esc((f['description'] or '')[:300])}\n\n"
                f"🆔 Код: <code>{esc(f['code'])}</code>\n👉 @{BOT_USERNAME}")
        results.append(InlineQueryResultArticle(
            id=f"c{f['code']}"[:64], title=f"🎬 {f['title']} ({f['year']})",
            description=(f["description"] or "")[:100], thumbnail_url=poster,
            input_message_content=InputTextMessageContent(
                message_text=text, parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(url=poster, prefer_large_media=True, show_above_text=True)
                if poster else LinkPreviewOptions(is_disabled=True)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text=tr(uid, "open_in_bot"), url=f"https://t.me/{BOT_USERNAME}?start=c{f['code']}")]]),
        ))
    for m in items:
        kind = kind_of(m)
        poster = img(m.get("poster_path")) or None
        rating = round(m.get("vote_average", 0) or 0, 1)
        text = (f"{'📺' if kind == 'tv' else '🎬'} <b>{esc(m.get('title', '—'))}</b> ({esc(year_of(m))})\n"
                f"⭐ {rating}/10\n\n📝 {esc((m.get('overview') or '')[:300])}\n\n👉 @{BOT_USERNAME}")
        results.append(InlineQueryResultArticle(
            id=f"{kind[0]}{m.get('id')}", title=f"{'📺' if kind == 'tv' else '🎬'} {m.get('title', '—')} ({year_of(m)})",
            description=f"⭐ {rating} · {(m.get('overview') or '')[:80]}", thumbnail_url=poster,
            input_message_content=InputTextMessageContent(
                message_text=text, parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(url=poster, prefer_large_media=True, show_above_text=True)
                if poster else LinkPreviewOptions(is_disabled=True)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text=tr(uid, "open_in_bot"), url=f"https://t.me/{BOT_USERNAME}?start={kind[0]}{m.get('id')}")]]),
        ))
    await query.answer(results[:50], cache_time=300, is_personal=False)


# ===== CALLBACKS =====
def parse_kind_id(data: str):
    """'x:movie:123' → ('movie', 123); старый формат 'x:123' → (None, 123)."""
    parts = data.split(":")
    if len(parts) == 3:
        return parts[1], int(parts[2])
    return None, int(parts[1])


@dp.callback_query(F.data.startswith("pick:"))
async def pick_callback(callback: CallbackQuery):
    kind, movie_id = parse_kind_id(callback.data)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await show_film(callback.message, callback.from_user.id, movie_id, kind)
    await callback.answer()


@dp.callback_query(F.data.startswith("check_only"))
async def check_only(callback: CallbackQuery):
    uid = callback.from_user.id
    if await check_sub(uid):
        return await callback.answer(tr(uid, "not_subscribed"), show_alert=True)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(tr(uid, "welcome"), reply_markup=get_menu(uid))
    await callback.answer()


@dp.callback_query(F.data.startswith("open:") | F.data.startswith("check:"))
async def open_callback(callback: CallbackQuery):
    """Кнопка «Проверить подписку» под фильмом. check:ID — старый формат."""
    uid = callback.from_user.id
    if await check_sub(uid):
        return await callback.answer(tr(uid, "not_subscribed"), show_alert=True)
    parts = callback.data.split(":", 2)
    kind, value = (parts[1], parts[2]) if parts[0] == "open" else ("auto", parts[1])
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.answer()
    await open_target(callback.message, uid, kind, value)


@dp.callback_query(F.data.startswith("quiz:"))
async def quiz_answer(callback: CallbackQuery):
    uid = callback.from_user.id
    quiz = search_cache.get(f"quiz_{uid}")
    if not quiz:
        return await callback.answer(tr(uid, "quiz_expired"), show_alert=True)
    raw = callback.data.split(":", 1)[1]
    chosen = quiz["options"][int(raw)] if raw.isdigit() and int(raw) < len(quiz["options"]) else raw
    if chosen != quiz["answer"]:
        return await callback.answer(html.unescape(tr(uid, "quiz_wrong", quiz["answer"])), show_alert=True)
    search_cache.pop(f"quiz_{uid}", None)
    await callback.answer(tr(uid, "quiz_correct"), show_alert=True)
    try:
        await callback.message.edit_reply_markup()
    except TelegramBadRequest:
        pass
    await open_target(callback.message, uid, "movie", str(quiz["movie_id"]))


@dp.callback_query(F.data.startswith("getvideo:"))
async def getvideo_callback(callback: CallbackQuery):
    uid = callback.from_user.id
    code = callback.data.split(":", 1)[1]
    film = await db.get_custom_film(code)
    if not film or not film.get("channel_message_id") or not VIDEO_CHANNEL_ID:
        return await callback.answer(tr(uid, "video_not_found"), show_alert=True)
    if not await require_sub(callback.message, uid, f"open:custom:{code}"):
        return await callback.answer()
    try:
        await bot.copy_message(uid, VIDEO_CHANNEL_ID, film["channel_message_id"], protect_content=PROTECT_CONTENT,
                               caption=film_caption(uid, film) if OWN_CAPTION else None)
        await callback.answer()
    except Exception as e:
        log.warning("getvideo %s failed: %s", code, e)
        await callback.answer(tr(uid, "video_error"), show_alert=True)


@dp.callback_query(F.data.startswith("fav:"))
async def fav_callback(callback: CallbackQuery):
    uid = callback.from_user.id
    kind, movie_id = parse_kind_id(callback.data)
    if await db.is_favorited(uid, movie_id):
        await db.remove_favorite(uid, movie_id)
        return await callback.answer(tr(uid, "removed_fav"))
    m = None
    custom = await db.get_custom_film(str(movie_id))
    if custom:
        m = {"title": custom["title"], "release_date": custom["year"], "vote_average": 0,
             "poster_path": custom["poster"]}
    else:
        for k in ([kind] if kind else ["movie", "tv"]):
            m = await fetch_title(k, movie_id)
            if m:
                break
    if not m:
        return await callback.answer(tr(uid, "film_not_found"), show_alert=True)
    await db.add_favorite(uid, movie_id, m.get("title", "—"), year_of(m),
                          round(m.get("vote_average", 0) or 0, 1), m.get("poster_path", ""))
    await callback.answer(tr(uid, "added_fav"))


@dp.callback_query(F.data.startswith("card:"))
async def card_nav(callback: CallbackQuery):
    _, source, index = callback.data.split(":")
    movies = search_cache.get(source)
    if not movies:
        return await callback.answer(tr(callback.from_user.id, "session_expired"), show_alert=True)
    await send_card(callback.message, movies, int(index), source, callback.from_user.id, edit=True)
    await callback.answer()


@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("film:"))
async def film_callback(callback: CallbackQuery):
    kind, movie_id = parse_kind_id(callback.data)
    await callback.answer()
    await open_target(callback.message, callback.from_user.id, kind or "auto", str(movie_id))


@dp.callback_query(F.data.startswith("sim:"))
async def similar(callback: CallbackQuery):
    uid = callback.from_user.id
    kind, movie_id = parse_kind_id(callback.data)
    results = []
    for k in ([kind] if kind else ["movie", "tv"]):
        results = (await api.tmdb(f"/{k}/{movie_id}/similar")).get("results", [])[:5]
        if results:
            if k == "tv":
                results = [api.normalize_tv(dict(r)) for r in results]
            break
    if not results:
        return await callback.answer(tr(uid, "no_similar"), show_alert=True)
    await callback.answer()
    await show_list(callback.message, uid, "sim", results)


@dp.callback_query(F.data.startswith("cast:"))
async def cast(callback: CallbackQuery):
    uid = callback.from_user.id
    kind, movie_id = parse_kind_id(callback.data)
    actors = []
    for k in ([kind] if kind else ["movie", "tv"]):
        actors = (await api.tmdb(f"/{k}/{movie_id}/credits")).get("cast", [])[:6]
        if actors:
            break
    if not actors:
        return await callback.answer(tr(uid, "no_actors"), show_alert=True)
    text = tr(uid, "actors_title")
    buttons = []
    for a in actors:
        text += f"• <b>{esc(a.get('name', '—'))}</b> — {esc(a.get('character', '—'))}\n"
        buttons.append([InlineKeyboardButton(text=f"🎭 {a.get('name', '—')}", callback_data=f"person:{a.get('id')}")])
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data.startswith("person:"))
async def person_callback(callback: CallbackQuery):
    await callback.answer()
    await search_person(callback.message, callback.from_user.id, person_id=int(callback.data.split(":")[1]))


@dp.errors()
async def on_error(event: ErrorEvent):
    log.exception("Unhandled error: %s", event.exception)
    cq = getattr(event.update, "callback_query", None)
    if cq:
        try:
            await cq.answer("⚠️ Ошибка, попробуй ещё раз", show_alert=False)
        except Exception:
            pass
    return True


# ===== ЗАПУСК =====
async def main():
    await db.init_db()
    await api.init_http()
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск / Boshlash"),
        BotCommand(command="lang", description="Язык / Til"),
        BotCommand(command="premium", description="⭐ Premium"),
        BotCommand(command="stats", description="Статистика / Statistika"),
        BotCommand(command="paysupport", description="Оплата / To'lov"),
    ])
    morning = asyncio.create_task(morning_broadcast())
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        morning.cancel()
        await api.close_http()
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
