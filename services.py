"""Внешние API: TMDb и Claude. Одна HTTP-сессия на весь бот + кэши, чтобы не долбить API."""

import json
import logging

import aiohttp
from cachetools import LRUCache, TTLCache

from config import AI_MODEL, ANTHROPIC_API_KEY, TMDB_API_KEY, TMDB_URL

log = logging.getLogger("filmix.services")

session: aiohttp.ClientSession | None = None

_tmdb_cache = TTLCache(maxsize=3000, ttl=30 * 60)   # ответы TMDb — 30 минут
_translate_cache = LRUCache(maxsize=5000)           # переводы описаний на узбекский


async def init_http():
    global session
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))


async def close_http():
    if session:
        await session.close()


# ===== TMDb =====
async def tmdb(path: str, **params) -> dict:
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", **params}
    key = path + json.dumps(params, sort_keys=True)
    if key in _tmdb_cache:
        return _tmdb_cache[key]
    try:
        async with session.get(f"{TMDB_URL}{path}", params=params) as r:
            data = await r.json()
    except Exception as e:
        log.warning("TMDb %s failed: %s", path, e)
        return {}
    if r.status == 200:
        _tmdb_cache[key] = data
        return data
    return {}


def normalize_tv(item: dict) -> dict:
    item["title"] = item.get("name", item.get("title", "—"))
    item["release_date"] = item.get("first_air_date", item.get("release_date", ""))
    item["is_tv"] = True
    return item


async def search_by_title(title: str):
    results = (await tmdb("/search/movie", query=title)).get("results", [])[:2]
    tv = (await tmdb("/search/tv", query=title)).get("results", [])[:1]
    return results + [normalize_tv(dict(t)) for t in tv]


async def search_multi(query: str, limit: int = 15):
    """Для inline-режима: фильмы и сериалы одним запросом."""
    data = await tmdb("/search/multi", query=query)
    out = []
    for item in data.get("results", []):
        if item.get("media_type") == "movie":
            out.append(dict(item))
        elif item.get("media_type") == "tv":
            out.append(normalize_tv(dict(item)))
        if len(out) >= limit:
            break
    return out


# ===== Claude =====
async def claude(prompt: str, max_tokens: int = 200, timeout: int = 30) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": AI_MODEL, "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as r:
            data = await r.json()
        if "content" in data:
            return data["content"][0]["text"].strip()
        log.warning("Claude error: %s", data.get("error"))
    except Exception as e:
        log.warning("Claude request failed: %s", e)
    return None


async def translate_to_uz(text: str) -> str:
    if not text or len(text) < 10:
        return text
    if text in _translate_cache:
        return _translate_cache[text]
    res = await claude(f"Translate to Uzbek. Reply ONLY with translation:\n\n{text}", max_tokens=500, timeout=15)
    if res:
        _translate_cache[text] = res
        return res
    return text


async def ai_find_movie(description: str) -> str:
    res = await claude(
        f"What movie/show is described? Description: {description}. "
        "Reply ONLY with English title. If multiple options, separate with commas. If unknown: unknown")
    return res.strip('"') if res else "unknown"


async def ai_recommend(query: str):
    res = await claude(f"Recommend 5 movies/shows for: {query}. Reply ONLY with English titles separated by commas.")
    if not res:
        return []
    return [t.strip() for t in res.split(",") if t.strip()][:5]
