"""
FILMIX — веб-панель: статистика + управление фильмами/видео.
Отдельное приложение, работает с той же базой PostgreSQL, что и main.py бота.
Запускается НЕЗАВИСИМО от бота: python dashboard.py

Как это работает:
- Бот (main.py) продолжает работать как раньше
- dashboard.py читает/пишет в ту же самую базу PostgreSQL (переменная DATABASE_URL)
- Панель доступна по адресу, который выдал Railway
- Вход защищён паролем (задаётся в .env, переменная DASHBOARD_PASSWORD)
- Раздел "Фильмы" позволяет добавлять/редактировать/удалять коды фильмов
  и привязывать к ним видео из Telegram-канала (channel_message_id) —
  без необходимости лезть в бота командами.
"""

import os
from datetime import datetime, timedelta
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import Flask, render_template_string, jsonify, request, redirect, make_response
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
COOKIE_NAME = "filmix_dash_auth"

app = Flask(__name__)


# ===== ПРОСТАЯ ПАРОЛЬНАЯ ЗАЩИТА (через форму + cookie) =====
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FILMIX — Вход</title>
<style>
  body {
    margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #0d0d12; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  .box {
    background: #16161d; border: 1px solid #26262f; border-radius: 14px;
    padding: 32px; width: 300px; text-align: center;
  }
  h1 { color: #f5f5f7; font-size: 20px; margin: 0 0 20px 0; }
  input {
    width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #26262f;
    background: #0d0d12; color: #f5f5f7; font-size: 14px; margin-bottom: 12px; box-sizing: border-box;
  }
  button {
    width: 100%; padding: 10px; border-radius: 8px; border: none;
    background: #E50914; color: #fff; font-size: 14px; font-weight: 600; cursor: pointer;
  }
  .error { color: #E50914; font-size: 13px; margin-bottom: 12px; }
</style>
</head>
<body>
  <div class="box">
    <h1>🎬 FILMIX Dashboard</h1>
    __ERROR__
    <form method="POST" action="/login">
      <input type="password" name="password" placeholder="Пароль" autofocus>
      <button type="submit">Войти</button>
    </form>
  </div>
</body>
</html>
"""


def is_authed():
    return request.cookies.get(COOKIE_NAME) == DASHBOARD_PASSWORD


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authed():
            if request.path.startswith("/api/"):
                return jsonify({"error": "not_authenticated"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == DASHBOARD_PASSWORD:
            resp = make_response(redirect("/"))
            resp.set_cookie(COOKIE_NAME, DASHBOARD_PASSWORD, max_age=60 * 60 * 24 * 30, httponly=True)
            return resp
        return LOGIN_HTML.replace("__ERROR__", '<div class="error">Неверный пароль</div>')
    return LOGIN_HTML.replace("__ERROR__", "")


# ===== РАБОТА С БАЗОЙ (PostgreSQL) =====
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(conn)
    return conn


def ensure_tables(conn):
    """Создаёт таблицы, если их ещё нет. Не трогает данные, если они уже есть."""
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT,
        joined_at TEXT, last_active TEXT, requests_count INTEGER DEFAULT 0,
        invited_by BIGINT, bonus_until TEXT, lang TEXT DEFAULT 'ru')""")
    c.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id SERIAL PRIMARY KEY,
        user_id BIGINT, movie_id INTEGER, title TEXT,
        year TEXT, rating REAL, poster TEXT, added_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id SERIAL PRIMARY KEY,
        inviter_id BIGINT, invited_id BIGINT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS channels (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE, name TEXT, url TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS custom_films (
        id SERIAL PRIMARY KEY,
        code TEXT UNIQUE, title TEXT, year TEXT,
        description TEXT, poster TEXT,
        watch_url TEXT, added_at TEXT,
        channel_message_id INTEGER)""")
    c.execute("ALTER TABLE custom_films ADD COLUMN IF NOT EXISTS channel_message_id INTEGER")
    conn.commit()


def get_overview_stats():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) AS n FROM users")
    total_users = c.fetchone()["n"]

    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) AS n FROM users WHERE last_active LIKE %s", (f"{today}%",))
    today_active = c.fetchone()["n"]

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    c.execute("SELECT COUNT(*) AS n FROM users WHERE last_active >= %s", (week_ago,))
    week_active = c.fetchone()["n"]

    c.execute("SELECT SUM(requests_count) AS n FROM users")
    total_requests = c.fetchone()["n"] or 0
    c.execute("SELECT COUNT(*) AS n FROM referrals")
    total_referrals = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) AS n FROM favorites")
    total_favorites = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) AS n FROM custom_films")
    total_custom_films = c.fetchone()["n"]

    c.execute("SELECT COALESCE(lang, 'ru') as lang, COUNT(*) as cnt FROM users GROUP BY lang")
    lang_rows = c.fetchall()
    lang_stats = {row["lang"]: row["cnt"] for row in lang_rows}

    conn.close()
    return {
        "total_users": total_users,
        "today_active": today_active,
        "week_active": week_active,
        "total_requests": total_requests,
        "total_referrals": total_referrals,
        "total_favorites": total_favorites,
        "total_custom_films": total_custom_films,
        "lang_stats": lang_stats,
    }


def get_growth_data(days=30):
    """Новые пользователи по дням за последние N дней."""
    conn = get_db()
    c = conn.cursor()
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute(
        """SELECT substr(joined_at, 1, 10) as day, COUNT(*) as cnt
           FROM users
           WHERE joined_at >= %s
           GROUP BY day
           ORDER BY day ASC""",
        (start_date,)
    )
    rows = c.fetchall()
    conn.close()

    counts_by_day = {row["day"]: row["cnt"] for row in rows}
    labels = []
    values = []
    for i in range(days, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        labels.append(day[5:])
        values.append(counts_by_day.get(day, 0))
    return labels, values


def get_top_favorites(limit=10):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT title, year, COUNT(*) as cnt
           FROM favorites
           GROUP BY movie_id, title, year
           ORDER BY cnt DESC
           LIMIT %s""",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [{"title": r["title"], "year": r["year"], "count": r["cnt"]} for r in rows]


def get_top_referrers(limit=10):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT u.user_id, u.username, u.first_name, COUNT(r.id) as cnt
           FROM referrals r
           JOIN users u ON u.user_id = r.inviter_id
           GROUP BY r.inviter_id, u.user_id, u.username, u.first_name
           ORDER BY cnt DESC
           LIMIT %s""",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"name": r["first_name"] or r["username"] or str(r["user_id"]), "count": r["cnt"]}
        for r in rows
    ]


def get_top_active_users(limit=10):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT user_id, username, first_name, requests_count
           FROM users
           ORDER BY requests_count DESC
           LIMIT %s""",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"name": r["first_name"] or r["username"] or str(r["user_id"]), "count": r["requests_count"]}
        for r in rows
    ]


# ===== УПРАВЛЕНИЕ ФИЛЬМАМИ/ВИДЕО =====
def list_films():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT code, title, year, description, poster, watch_url, channel_message_id, added_at
                 FROM custom_films ORDER BY added_at DESC""")
    rows = c.fetchall()
    conn.close()
    return rows


def upsert_film(code, title, year, description, poster, watch_url, channel_message_id):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""INSERT INTO custom_films (code, title, year, description, poster, watch_url, channel_message_id, added_at)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                 ON CONFLICT (code) DO UPDATE SET
                    title=EXCLUDED.title, year=EXCLUDED.year, description=EXCLUDED.description,
                    poster=EXCLUDED.poster, watch_url=EXCLUDED.watch_url,
                    channel_message_id=EXCLUDED.channel_message_id""",
              (code, title, year, description, poster, watch_url, channel_message_id, now))
    conn.commit()
    conn.close()


def delete_film(code):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM custom_films WHERE code=%s", (code,))
    conn.commit()
    conn.close()


# ===== HTML: СТАТИСТИКА =====
NAV_HTML = """
<div style="display:flex;gap:10px;margin-bottom:20px;">
  <a href="/" style="color:{home_color};text-decoration:none;font-size:14px;font-weight:600;padding:8px 14px;border-radius:8px;background:#16161d;border:1px solid #26262f;">📊 Статистика</a>
  <a href="/films" style="color:{films_color};text-decoration:none;font-size:14px;font-weight:600;padding:8px 14px;border-radius:8px;background:#16161d;border:1px solid #26262f;">🎬 Фильмы</a>
</div>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FILMIX — Статистика</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0d0d12; --card: #16161d; --border: #26262f; --red: #E50914;
    --text: #f5f5f7; --muted: #9a9aa5;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    padding: 24px;
  }
  h1 { font-size: 26px; margin: 0 0 4px 0; display: flex; align-items: center; gap: 10px; }
  .subtitle { color: var(--muted); margin-bottom: 20px; font-size: 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px; }
  .stat-card .label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
  .stat-card .value { font-size: 28px; font-weight: 700; }
  .stat-card .value.red { color: var(--red); }
  .row { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 16px; }
  @media (max-width: 800px) { .row { grid-template-columns: 1fr; } }
  .panel { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 20px; }
  .panel h2 { font-size: 15px; margin: 0 0 16px 0; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; font-size: 12px; text-transform: uppercase; }
  td.num { text-align: right; color: var(--red); font-weight: 600; }
  .refresh-note { color: var(--muted); font-size: 12px; margin-top: 24px; text-align: center; }
</style>
</head>
<body>

<h1>🎬 FILMIX</h1>
""" + NAV_HTML.format(home_color="#f5f5f7", films_color="#9a9aa5") + """
<div class="subtitle" id="lastUpdated">Загрузка...</div>

<div class="grid" id="overviewGrid"></div>

<div class="row">
  <div class="panel">
    <h2>Рост пользователей (30 дней)</h2>
    <canvas id="growthChart" height="90"></canvas>
  </div>
  <div class="panel">
    <h2>Язык интерфейса</h2>
    <canvas id="langChart" height="90"></canvas>
  </div>
</div>

<div class="row">
  <div class="panel">
    <h2>❤️ Топ избранных фильмов</h2>
    <table id="favTable"><thead><tr><th>Фильм</th><th>Год</th><th>Добавлений</th></tr></thead><tbody></tbody></table>
  </div>
  <div class="panel">
    <h2>🔗 Топ по рефералам</h2>
    <table id="refTable"><thead><tr><th>Пользователь</th><th>Приглашено</th></tr></thead><tbody></tbody></table>
  </div>
</div>

<div class="panel">
  <h2>🔥 Самые активные пользователи</h2>
  <table id="activeTable"><thead><tr><th>Пользователь</th><th>Запросов</th></tr></thead><tbody></tbody></table>
</div>

<div class="refresh-note">Обновляется автоматически каждые 30 секунд</div>

<script>
let growthChart, langChart;

async function loadData() {
  let res, data;
  try {
    res = await fetch('/api/stats');
    if (res.status === 401) { window.location.href = '/login'; return; }
    data = await res.json();
  } catch (e) {
    document.getElementById('lastUpdated').textContent = 'Ошибка загрузки данных: ' + e;
    return;
  }
  if (!res.ok) {
    document.getElementById('lastUpdated').textContent = 'Ошибка сервера: ' + (data.error || res.status);
    return;
  }

  document.getElementById('lastUpdated').textContent = 'Обновлено: ' + new Date().toLocaleTimeString('ru-RU');

  const ov = data.overview;
  document.getElementById('overviewGrid').innerHTML = `
    <div class="stat-card"><div class="label">Всего пользователей</div><div class="value red">${ov.total_users}</div></div>
    <div class="stat-card"><div class="label">Активны сегодня</div><div class="value">${ov.today_active}</div></div>
    <div class="stat-card"><div class="label">Активны за неделю</div><div class="value">${ov.week_active}</div></div>
    <div class="stat-card"><div class="label">Всего запросов</div><div class="value">${ov.total_requests}</div></div>
    <div class="stat-card"><div class="label">Рефералов</div><div class="value">${ov.total_referrals}</div></div>
    <div class="stat-card"><div class="label">В избранном (всего)</div><div class="value">${ov.total_favorites}</div></div>
    <div class="stat-card"><div class="label">Своих фильмов в базе</div><div class="value">${ov.total_custom_films}</div></div>
  `;

  const ctx1 = document.getElementById('growthChart');
  if (growthChart) growthChart.destroy();
  growthChart = new Chart(ctx1, {
    type: 'line',
    data: { labels: data.growth.labels, datasets: [{
      label: 'Новые пользователи', data: data.growth.values,
      borderColor: '#E50914', backgroundColor: 'rgba(229,9,20,0.15)',
      fill: true, tension: 0.3, pointRadius: 2
    }]},
    options: { responsive: true, plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#9a9aa5', maxTicksLimit: 10 }, grid: { color: '#26262f' } },
        y: { ticks: { color: '#9a9aa5', precision: 0 }, grid: { color: '#26262f' } }
      }
    }
  });

  const ctx2 = document.getElementById('langChart');
  if (langChart) langChart.destroy();
  const langLabels = Object.keys(ov.lang_stats).map(l => l === 'ru' ? '🇷🇺 Русский' : '🇺🇿 Узбекский');
  const langValues = Object.values(ov.lang_stats);
  langChart = new Chart(ctx2, {
    type: 'doughnut',
    data: { labels: langLabels, datasets: [{ data: langValues, backgroundColor: ['#E50914', '#3b82f6', '#22c55e'] }] },
    options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#f5f5f7' } } } }
  });

  const favBody = document.querySelector('#favTable tbody');
  favBody.innerHTML = data.top_favorites.map(f =>
    `<tr><td>${f.title}</td><td>${f.year || '—'}</td><td class="num">${f.count}</td></tr>`
  ).join('') || '<tr><td colspan="3" style="color:#9a9aa5">Пока пусто</td></tr>';

  const refBody = document.querySelector('#refTable tbody');
  refBody.innerHTML = data.top_referrers.map(r =>
    `<tr><td>${r.name}</td><td class="num">${r.count}</td></tr>`
  ).join('') || '<tr><td colspan="2" style="color:#9a9aa5">Пока пусто</td></tr>';

  const activeBody = document.querySelector('#activeTable tbody');
  activeBody.innerHTML = data.top_active.map(a =>
    `<tr><td>${a.name}</td><td class="num">${a.count}</td></tr>`
  ).join('') || '<tr><td colspan="2" style="color:#9a9aa5">Пока пусто</td></tr>';
}

loadData();
setInterval(loadData, 30000);
</script>

</body>
</html>
"""


# ===== HTML: УПРАВЛЕНИЕ ФИЛЬМАМИ =====
FILMS_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FILMIX — Фильмы</title>
<style>
  :root {
    --bg: #0d0d12; --card: #16161d; --border: #26262f; --red: #E50914;
    --text: #f5f5f7; --muted: #9a9aa5;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    padding: 24px;
  }
  h1 { font-size: 26px; margin: 0 0 20px 0; display: flex; align-items: center; gap: 10px; }
  .panel { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 20px; margin-bottom: 20px; }
  .panel h2 { font-size: 15px; margin: 0 0 16px 0; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; margin-top: 10px; }
  input, textarea {
    width: 100%; padding: 9px 12px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--bg); color: var(--text); font-size: 14px; box-sizing: border-box; font-family: inherit;
  }
  textarea { resize: vertical; min-height: 60px; }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
  button {
    margin-top: 16px; padding: 10px 18px; border-radius: 8px; border: none;
    background: var(--red); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer;
  }
  button.secondary { background: #2a2a33; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; }
  .code { color: var(--red); font-weight: 700; }
  .yes { color: #22c55e; }
  .no { color: var(--muted); }
  .actions button { margin: 2px 2px 0 0; padding: 5px 10px; font-size: 12px; }
  .hint { color: var(--muted); font-size: 12px; margin-top: 6px; }
</style>
</head>
<body>

<h1>🎬 FILMIX</h1>
""" + NAV_HTML.format(home_color="#9a9aa5", films_color="#f5f5f7") + """

<div class="panel">
  <h2 id="formTitle">➕ Добавить / обновить фильм</h2>
  <form id="filmForm">
    <div class="form-grid">
      <div>
        <label>Код (уникальный, обязателен)</label>
        <input type="text" id="f_code" required>
      </div>
      <div>
        <label>Год</label>
        <input type="text" id="f_year">
      </div>
    </div>
    <label>Название</label>
    <input type="text" id="f_title" required>
    <label>Описание</label>
    <textarea id="f_description"></textarea>
    <div class="form-grid">
      <div>
        <label>Постер (URL картинки)</label>
        <input type="text" id="f_poster">
      </div>
      <div>
        <label>ID видео в канале (channel_message_id)</label>
        <input type="text" id="f_channel_message_id" placeholder="напр. 42">
      </div>
    </div>
    <label>Внешняя ссылка «Смотреть» (необязательно, если есть видео в канале)</label>
    <input type="text" id="f_watch_url">
    <div class="hint">Если заполнено «ID видео в канале» — пользователю покажется кнопка «Смотреть видео», которая копирует ролик прямо из вашего Telegram-канала. Иначе — кнопка со ссылкой.</div>
    <button type="submit">💾 Сохранить</button>
    <button type="button" class="secondary" onclick="resetForm()">Очистить форму</button>
  </form>
</div>

<div class="panel">
  <h2>📋 Все фильмы</h2>
  <table>
    <thead><tr><th>Код</th><th>Название</th><th>Год</th><th>Видео</th><th>Добавлен</th><th>Действия</th></tr></thead>
    <tbody id="filmsBody"></tbody>
  </table>
</div>

<script>
async function loadFilms() {
  const res = await fetch('/api/films');
  if (res.status === 401) { window.location.href = '/login'; return; }
  const films = await res.json();
  const body = document.getElementById('filmsBody');
  body.innerHTML = films.map(f => `
    <tr>
      <td class="code">${f.code}</td>
      <td>${f.title}</td>
      <td>${f.year || '—'}</td>
      <td>${f.channel_message_id ? '<span class="yes">✔ есть</span>' : '<span class="no">нет</span>'}</td>
      <td>${f.added_at || '—'}</td>
      <td class="actions">
        <button onclick='editFilm(${JSON.stringify(f)})'>✏️ Изменить</button>
        <button class="secondary" onclick="deleteFilm('${f.code}')">🗑 Удалить</button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="6" style="color:#9a9aa5">Фильмов пока нет</td></tr>';
}

function editFilm(f) {
  document.getElementById('f_code').value = f.code;
  document.getElementById('f_title').value = f.title || '';
  document.getElementById('f_year').value = f.year || '';
  document.getElementById('f_description').value = f.description || '';
  document.getElementById('f_poster').value = f.poster || '';
  document.getElementById('f_watch_url').value = f.watch_url || '';
  document.getElementById('f_channel_message_id').value = f.channel_message_id || '';
  document.getElementById('formTitle').textContent = '✏️ Редактирование: ' + f.code;
  window.scrollTo({top: 0, behavior: 'smooth'});
}

function resetForm() {
  document.getElementById('filmForm').reset();
  document.getElementById('formTitle').textContent = '➕ Добавить / обновить фильм';
}

document.getElementById('filmForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const payload = {
    code: document.getElementById('f_code').value.trim(),
    title: document.getElementById('f_title').value.trim(),
    year: document.getElementById('f_year').value.trim(),
    description: document.getElementById('f_description').value.trim(),
    poster: document.getElementById('f_poster').value.trim(),
    watch_url: document.getElementById('f_watch_url').value.trim(),
    channel_message_id: document.getElementById('f_channel_message_id').value.trim() || null,
  };
  const res = await fetch('/api/films', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  if (res.status === 401) { window.location.href = '/login'; return; }
  if (res.ok) { resetForm(); loadFilms(); } else { alert('Ошибка сохранения'); }
});

async function deleteFilm(code) {
  if (!confirm('Удалить фильм с кодом ' + code + '?')) return;
  const res = await fetch('/api/films/' + encodeURIComponent(code), { method: 'DELETE' });
  if (res.status === 401) { window.location.href = '/login'; return; }
  loadFilms();
}

loadFilms();
</script>

</body>
</html>
"""


@app.route("/")
@requires_auth
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/stats")
@requires_auth
def api_stats():
    try:
        overview = get_overview_stats()
        labels, values = get_growth_data(30)
        return jsonify({
            "overview": overview,
            "growth": {"labels": labels, "values": values},
            "top_favorites": get_top_favorites(10),
            "top_referrers": get_top_referrers(10),
            "top_active": get_top_active_users(10),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/films")
@requires_auth
def films_page():
    return render_template_string(FILMS_HTML)


@app.route("/api/films", methods=["GET"])
@requires_auth
def api_films_list():
    try:
        return jsonify(list_films())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/films", methods=["POST"])
@requires_auth
def api_films_upsert():
    try:
        data = request.get_json(force=True)
        code = (data.get("code") or "").strip()
        title = (data.get("title") or "").strip()
        if not code or not title:
            return jsonify({"error": "code и title обязательны"}), 400
        year = (data.get("year") or "").strip()
        description = (data.get("description") or "").strip()
        poster = (data.get("poster") or "").strip()
        watch_url = (data.get("watch_url") or "").strip()
        channel_message_id = data.get("channel_message_id")
        channel_message_id = int(channel_message_id) if channel_message_id not in (None, "") else None
        upsert_film(code, title, year, description, poster, watch_url, channel_message_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/films/<code>", methods=["DELETE"])
@requires_auth
def api_films_delete(code):
    try:
        delete_film(code)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    print(f"📊 FILMIX Dashboard запущен на порту {port}")
    print(f"🔑 Пароль: {DASHBOARD_PASSWORD}")
    app.run(host="0.0.0.0", port=port)
