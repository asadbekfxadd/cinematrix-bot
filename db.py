"""Асинхронная работа с PostgreSQL через пул соединений asyncpg.

Схема таблиц совместима со старой версией и с dashboard.py — данные не теряются.
"""

from datetime import datetime, timedelta

import asyncpg

from config import DATABASE_URL, DT_FMT, now_local, now_str

pool: asyncpg.Pool | None = None

# Кэш языка пользователей: tr() вызывается очень часто, ходить за языком в БД каждый раз дорого
LANG_CACHE: dict[int, str] = {}


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10, command_timeout=30)
    async with pool.acquire() as c:
        await c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT,
            joined_at TEXT, last_active TEXT, requests_count INTEGER DEFAULT 0,
            invited_by BIGINT, bonus_until TEXT, lang TEXT DEFAULT 'ru')""")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE")
        await c.execute("""CREATE TABLE IF NOT EXISTS favorites (
            id SERIAL PRIMARY KEY,
            user_id BIGINT, movie_id INTEGER, title TEXT,
            year TEXT, rating REAL, poster TEXT, added_at TEXT)""")
        await c.execute("""CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            inviter_id BIGINT, invited_id BIGINT, created_at TEXT)""")
        await c.execute("""CREATE TABLE IF NOT EXISTS channels (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE, name TEXT, url TEXT)""")
        await c.execute("""CREATE TABLE IF NOT EXISTS custom_films (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE, title TEXT, year TEXT,
            description TEXT, poster TEXT,
            watch_url TEXT, added_at TEXT,
            channel_message_id INTEGER)""")
        await c.execute("ALTER TABLE custom_films ADD COLUMN IF NOT EXISTS channel_message_id INTEGER")
        await c.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")
        # Индексы — ускоряют избранное и рефералов
        await c.execute("CREATE INDEX IF NOT EXISTS idx_fav_user_movie ON favorites (user_id, movie_id)")
        await c.execute("CREATE INDEX IF NOT EXISTS idx_ref_inviter ON referrals (inviter_id)")
        if await c.fetchval("SELECT COUNT(*) FROM channels") == 0:
            await c.execute(
                "INSERT INTO channels (username, name, url) VALUES ($1, $2, $3) ON CONFLICT (username) DO NOTHING",
                "-1001199192573", "FILMIX", "https://t.me/+-BKXmo8rQr8xMjgy")


async def close_db():
    if pool:
        await pool.close()


# ===== ПОЛЬЗОВАТЕЛИ =====
async def user_exists(user_id: int) -> bool:
    return await pool.fetchval("SELECT 1 FROM users WHERE user_id=$1", user_id) is not None


async def upsert_user(user_id, username, first_name, invited_by=None) -> tuple[bool, bool]:
    """Создаёт или обновляет пользователя. Возвращает (новый_ли, засчитан_ли_реферал).
    Реферал засчитывается только если пригласивший реально есть в базе."""
    now = now_str()
    async with pool.acquire() as c, c.transaction():
        inserted = await c.fetchval(
            """INSERT INTO users (user_id, username, first_name, joined_at, last_active, invited_by, lang)
               VALUES ($1, $2, $3, $4, $4, $5, 'ru') ON CONFLICT (user_id) DO NOTHING RETURNING user_id""",
            user_id, username, first_name, now, None)
        if inserted:
            if invited_by and invited_by != user_id and await c.fetchval(
                    "SELECT 1 FROM users WHERE user_id=$1", invited_by):
                await c.execute("UPDATE users SET invited_by=$1 WHERE user_id=$2", invited_by, user_id)
                await c.execute("INSERT INTO referrals (inviter_id, invited_id, created_at) VALUES ($1, $2, $3)",
                                invited_by, user_id, now)
                bonus = (now_local() + timedelta(hours=24)).strftime(DT_FMT)
                await c.execute("UPDATE users SET bonus_until=$1 WHERE user_id=$2", bonus, invited_by)
                LANG_CACHE.setdefault(user_id, "ru")
                return True, True
            LANG_CACHE.setdefault(user_id, "ru")
            return True, False
        row = await c.fetchrow(
            """UPDATE users SET last_active=$1, requests_count=COALESCE(requests_count,0)+1,
                   username=$2, first_name=$3, is_blocked=FALSE
               WHERE user_id=$4 RETURNING lang""",
            now, username, first_name, user_id)
        if row:
            LANG_CACHE[user_id] = row["lang"] or "ru"
        return False, False


async def load_lang(user_id: int) -> str:
    if user_id in LANG_CACHE:
        return LANG_CACHE[user_id]
    lang = await pool.fetchval("SELECT lang FROM users WHERE user_id=$1", user_id)
    LANG_CACHE[user_id] = lang or "ru"
    return LANG_CACHE[user_id]


def get_lang(user_id: int) -> str:
    return LANG_CACHE.get(user_id, "ru")


async def set_lang(user_id: int, lang: str):
    LANG_CACHE[user_id] = lang
    await pool.execute("UPDATE users SET lang=$1 WHERE user_id=$2", lang, user_id)


async def get_stats():
    today = now_local().strftime("%Y-%m-%d")
    async with pool.acquire() as c:
        total = await c.fetchval("SELECT COUNT(*) FROM users")
        today_active = await c.fetchval("SELECT COUNT(*) FROM users WHERE last_active LIKE $1", f"{today}%")
        total_requests = await c.fetchval("SELECT COALESCE(SUM(requests_count),0) FROM users")
        total_referrals = await c.fetchval("SELECT COUNT(*) FROM referrals")
        blocked = await c.fetchval("SELECT COUNT(*) FROM users WHERE is_blocked")
    return total, today_active, total_requests, total_referrals, blocked


async def has_bonus(user_id: int) -> bool:
    val = await pool.fetchval("SELECT bonus_until FROM users WHERE user_id=$1", user_id)
    if not val:
        return False
    try:
        return now_local() < datetime.strptime(val, DT_FMT)
    except ValueError:
        return False


async def get_referral_count(user_id: int) -> int:
    return await pool.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id=$1", user_id)


async def get_active_users():
    """Все, кто не заблокировал бота. Заодно прогреваем кэш языков."""
    rows = await pool.fetch("SELECT user_id, lang FROM users WHERE NOT COALESCE(is_blocked, FALSE)")
    for r in rows:
        LANG_CACHE[r["user_id"]] = r["lang"] or "ru"
    return [r["user_id"] for r in rows]


async def mark_blocked(user_id: int):
    await pool.execute("UPDATE users SET is_blocked=TRUE WHERE user_id=$1", user_id)


# ===== ИЗБРАННОЕ =====
async def is_favorited(user_id: int, movie_id: int) -> bool:
    return await pool.fetchval(
        "SELECT 1 FROM favorites WHERE user_id=$1 AND movie_id=$2", user_id, movie_id) is not None


async def add_favorite(user_id, movie_id, title, year, rating, poster) -> bool:
    if await is_favorited(user_id, movie_id):
        return False
    await pool.execute(
        """INSERT INTO favorites (user_id, movie_id, title, year, rating, poster, added_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        user_id, movie_id, title, year, float(rating or 0), poster, now_str())
    return True


async def remove_favorite(user_id: int, movie_id: int):
    await pool.execute("DELETE FROM favorites WHERE user_id=$1 AND movie_id=$2", user_id, movie_id)


async def get_favorites(user_id: int):
    rows = await pool.fetch(
        "SELECT movie_id, title, year, rating, poster FROM favorites WHERE user_id=$1 ORDER BY added_at DESC",
        user_id)
    return [{"id": r["movie_id"], "title": r["title"], "release_date": r["year"],
             "vote_average": r["rating"], "poster_path": r["poster"]} for r in rows]


# ===== СВОЯ БАЗА ФИЛЬМОВ =====
def _film(r):
    return dict(r) if r else None


async def add_custom_film(code, title, year, description, poster, watch_url) -> bool:
    try:
        await pool.execute(
            """INSERT INTO custom_films (code, title, year, description, poster, watch_url, added_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT (code) DO UPDATE SET
                  title=EXCLUDED.title, year=EXCLUDED.year, description=EXCLUDED.description,
                  poster=EXCLUDED.poster, watch_url=EXCLUDED.watch_url, added_at=EXCLUDED.added_at""",
            str(code), title, year, description, poster, watch_url, now_str())
        return True
    except asyncpg.PostgresError:
        return False


async def get_custom_film(code):
    return _film(await pool.fetchrow(
        """SELECT code, title, year, description, poster, watch_url, channel_message_id
           FROM custom_films WHERE code=$1""", str(code)))


async def set_film_video(code, channel_message_id: int) -> bool:
    res = await pool.execute("UPDATE custom_films SET channel_message_id=$1 WHERE code=$2",
                             channel_message_id, str(code))
    return res.endswith(" 1")


async def delete_custom_film(code) -> bool:
    res = await pool.execute("DELETE FROM custom_films WHERE code=$1", str(code))
    return res.endswith(" 1")


async def get_all_custom_films():
    return await pool.fetch("SELECT code, title, year, watch_url FROM custom_films ORDER BY added_at DESC")


async def search_custom_films(query: str, limit: int = 10):
    rows = await pool.fetch(
        """SELECT code, title, year, description, poster, watch_url, channel_message_id
           FROM custom_films WHERE title ILIKE $1 ORDER BY added_at DESC LIMIT $2""",
        f"%{query}%", limit)
    return [dict(r) for r in rows]


# ===== КАНАЛЫ =====
async def get_channels():
    rows = await pool.fetch("SELECT username, name, url FROM channels")
    return [dict(r) for r in rows]


async def db_add_channel(username, name, url) -> bool:
    try:
        await pool.execute("INSERT INTO channels (username, name, url) VALUES ($1, $2, $3)", username, name, url)
        return True
    except asyncpg.UniqueViolationError:
        return False


async def db_remove_channel(username) -> bool:
    res = await pool.execute("DELETE FROM channels WHERE username=$1", username)
    return res.endswith(" 1")


# ===== KEY-VALUE (служебное) =====
async def kv_get(key: str):
    return await pool.fetchval("SELECT value FROM kv WHERE key=$1", key)


async def kv_set(key: str, value: str):
    await pool.execute("INSERT INTO kv (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value=$2",
                       key, value)
