"""Внешние API: TMDb и Claude. Одна HTTP-сессия на весь бот + кэши, чтобы не долбить API."""

import difflib
import json
import logging
import re

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


# ===== Распознавание фильма из подписи поста =====
async def ai_extract_film(caption: str) -> dict | None:
    """Claude вытаскивает из «грязной» подписи (реклама, хэштеги, ссылки) настоящее название и год."""
    if not caption or len(caption.strip()) < 3:
        return None
    res = await claude(
        "Below is a caption of a movie/series post from a Telegram channel (may contain ads, links, emojis, "
        "Uzbek/Russian text). Identify the film. Reply ONLY with JSON: "
        '{"title_en": "...", "title_ru": "...", "year": 2020, "type": "movie" or "tv"}. '
        'Use null for unknown fields. If it is not a movie/series, reply {"title_en": null}.\n\n'
        f"Caption:\n{caption[:1500]}", max_tokens=150)
    if not res:
        return None
    m = re.search(r"\{.*\}", res, re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
    return data if data and (data.get("title_en") or data.get("title_ru")) else None


def _similar(a: str, b: str) -> float:
    norm = lambda x: re.sub(r"[^\w]+", " ", (x or "").lower()).strip()
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


async def match_tmdb(query: str, year=None, kind: str | None = None, min_score: float = 0.6) -> dict | None:
    """Ищет фильм/сериал в TMDb и берёт результат, только если название реально похоже."""
    if not query:
        return None
    best, best_score = None, 0.0
    for k in ([kind] if kind in ("movie", "tv") else ["movie", "tv"]):
        params = {"query": query}
        if year:
            params["primary_release_year" if k == "movie" else "first_air_date_year"] = str(year)
        for item in (await tmdb(f"/search/{k}", **params)).get("results", [])[:5]:
            names = [item.get("title"), item.get("original_title"), item.get("name"), item.get("original_name")]
            score = max(_similar(query, n) for n in names if n) if any(names) else 0
            if score > best_score:
                best, best_score = (normalize_tv(dict(item)) if k == "tv" else dict(item)), score
    return best if best_score >= min_score else None
