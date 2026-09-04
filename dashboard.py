"""
FILMIX — веб-панель статистики
Отдельное приложение, читает ту же базу filmix.db, что и main.py бота.
Запускается НЕЗАВИСИМО от бота: python dashboard.py

Как это работает:
- Бот (main.py) продолжает работать как раньше, ничего в нём не меняется
- dashboard.py открывает ту же самую базу filmix.db (только для чтения)
- Панель доступна по адресу http://ВАШ_IP:5000
- Вход защищён паролем (задаётся в .env, переменная DASHBOARD_PASSWORD)
"""

import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template_string, jsonify, request, redirect, make_response
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "filmix.db"
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
COOKIE_NAME = "filmix_dash_auth"

app = Flask(__name__)


# ===== ПРОСТАЯ ПАРОЛЬНАЯ ЗАЩИТА (через форму + cookie) =====
# Используем cookie вместо стандартного HTTP Basic Auth, потому что Basic Auth
# не всегда автоматически повторно отправляется браузером при запросах через
# JavaScript (fetch), из-за чего страница статистики зависала на "Загрузка...".
# Cookie отправляется браузером автоматически при КАЖДОМ запросе к сайту — надёжнее.

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
            # Для страниц — редирект на форму входа. Для API — просто ошибка 401.
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


# ===== РАБОТА С БАЗОЙ =====
def ensure_tables(conn):
    """Создаёт таблицы, если их ещё нет (например, бот ни разу не запускался
    на этой машине). Не трогает данные, если таблицы уже существуют."""
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        joined_at TEXT, last_active TEXT, requests_count INTEGER DEFAULT 0,
        invited_by INTEGER, bonus_until TEXT, lang TEXT DEFAULT 'ru')""")
    c.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, movie_id INTEGER, title TEXT,
        year TEXT, rating REAL, poster TEXT, added_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inviter_id INTEGER, invited_id INTEGER, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, name TEXT, url TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS custom_films (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE, title TEXT, year TEXT,
        description TEXT, poster TEXT,
        watch_url TEXT, added_at TEXT)""")
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)
    return conn


def get_overview_stats():
    conn = get_db()
    c = conn.cursor()

    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")
    today_active = c.execute(
        "SELECT COUNT(*) FROM users WHERE last_active LIKE ?", (f"{today}%",)
    ).fetchone()[0]

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    week_active = c.execute(
        "SELECT COUNT(*) FROM users WHERE last_active >= ?", (week_ago,)
    ).fetchone()[0]

    total_requests = c.execute("SELECT SUM(requests_count) FROM users").fetchone()[0] or 0
    total_referrals = c.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
    total_favorites = c.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
    total_custom_films = c.execute("SELECT COUNT(*) FROM custom_films").fetchone()[0]

    lang_rows = c.execute(
        "SELECT COALESCE(lang, 'ru') as lang, COUNT(*) as cnt FROM users GROUP BY lang"
    ).fetchall()
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
    rows = c.execute(
        """SELECT substr(joined_at, 1, 10) as day, COUNT(*) as cnt
           FROM users
           WHERE joined_at >= ?
           GROUP BY day
           ORDER BY day ASC""",
        (start_date,)
    ).fetchall()
    conn.close()

    # Заполняем пропущенные дни нулями, чтобы график был непрерывным
    counts_by_day = {row["day"]: row["cnt"] for row in rows}
    labels = []
    values = []
    for i in range(days, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        labels.append(day[5:])  # ММ-ДД для компактности
        values.append(counts_by_day.get(day, 0))
    return labels, values


def get_top_favorites(limit=10):
    """Самые часто добавляемые в избранное фильмы."""
    conn = get_db()
    c = conn.cursor()
    rows = c.execute(
        """SELECT title, year, COUNT(*) as cnt
           FROM favorites
           GROUP BY movie_id, title
           ORDER BY cnt DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [{"title": r["title"], "year": r["year"], "count": r["cnt"]} for r in rows]


def get_top_referrers(limit=10):
    """Пользователи с наибольшим числом рефералов."""
    conn = get_db()
    c = conn.cursor()
    rows = c.execute(
        """SELECT u.user_id, u.username, u.first_name, COUNT(r.id) as cnt
           FROM referrals r
           JOIN users u ON u.user_id = r.inviter_id
           GROUP BY r.inviter_id
           ORDER BY cnt DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {"name": r["first_name"] or r["username"] or str(r["user_id"]), "count": r["cnt"]}
        for r in rows
    ]


def get_top_active_users(limit=10):
    """Пользователи с наибольшим числом запросов."""
    conn = get_db()
    c = conn.cursor()
    rows = c.execute(
        """SELECT user_id, username, first_name, requests_count
           FROM users
           ORDER BY requests_count DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {"name": r["first_name"] or r["username"] or str(r["user_id"]), "count": r["requests_count"]}
        for r in rows
    ]


# ===== HTML-ШАБЛОН =====
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
    --bg: #0d0d12;
    --card: #16161d;
    --border: #26262f;
    --red: #E50914;
    --text: #f5f5f7;
    --muted: #9a9aa5;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    padding: 24px;
  }
  h1 {
    font-size: 26px;
    margin: 0 0 4px 0;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .subtitle { color: var(--muted); margin-bottom: 28px; font-size: 14px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
  }
  .stat-card .label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
  .stat-card .value { font-size: 28px; font-weight: 700; }
  .stat-card .value.red { color: var(--red); }
  .row {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }
  @media (max-width: 800px) { .row { grid-template-columns: 1fr; } }
  .panel {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
  }
  .panel h2 {
    font-size: 15px;
    margin: 0 0 16px 0;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; font-size: 12px; text-transform: uppercase; }
  td.num { text-align: right; color: var(--red); font-weight: 600; }
  .refresh-note { color: var(--muted); font-size: 12px; margin-top: 24px; text-align: center; }
</style>
</head>
<body>

<h1>🎬 FILMIX — Статистика</h1>
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
    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }
    data = await res.json();
  } catch (e) {
    document.getElementById('lastUpdated').textContent = 'Ошибка загрузки данных: ' + e;
    return;
  }
  if (!res.ok) {
    document.getElementById('lastUpdated').textContent =
      'Ошибка сервера: ' + (data.error || res.status);
    return;
  }

  document.getElementById('lastUpdated').textContent =
    'Обновлено: ' + new Date().toLocaleTimeString('ru-RU');

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

  // График роста
  const ctx1 = document.getElementById('growthChart');
  if (growthChart) growthChart.destroy();
  growthChart = new Chart(ctx1, {
    type: 'line',
    data: {
      labels: data.growth.labels,
      datasets: [{
        label: 'Новые пользователи',
        data: data.growth.values,
        borderColor: '#E50914',
        backgroundColor: 'rgba(229,9,20,0.15)',
        fill: true,
        tension: 0.3,
        pointRadius: 2
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#9a9aa5', maxTicksLimit: 10 }, grid: { color: '#26262f' } },
        y: { ticks: { color: '#9a9aa5', precision: 0 }, grid: { color: '#26262f' } }
      }
    }
  });

  // Круговая диаграмма языков
  const ctx2 = document.getElementById('langChart');
  if (langChart) langChart.destroy();
  const langLabels = Object.keys(ov.lang_stats).map(l => l === 'ru' ? '🇷🇺 Русский' : '🇺🇿 Узбекский');
  const langValues = Object.values(ov.lang_stats);
  langChart = new Chart(ctx2, {
    type: 'doughnut',
    data: {
      labels: langLabels,
      datasets: [{ data: langValues, backgroundColor: ['#E50914', '#3b82f6', '#22c55e'] }]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'bottom', labels: { color: '#f5f5f7' } } }
    }
  });

  // Таблица избранного
  const favBody = document.querySelector('#favTable tbody');
  favBody.innerHTML = data.top_favorites.map(f =>
    `<tr><td>${f.title}</td><td>${f.year || '—'}</td><td class="num">${f.count}</td></tr>`
  ).join('') || '<tr><td colspan="3" style="color:#9a9aa5">Пока пусто</td></tr>';

  // Таблица рефералов
  const refBody = document.querySelector('#refTable tbody');
  refBody.innerHTML = data.top_referrers.map(r =>
    `<tr><td>${r.name}</td><td class="num">${r.count}</td></tr>`
  ).join('') || '<tr><td colspan="2" style="color:#9a9aa5">Пока пусто</td></tr>';

  // Таблица активных
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


if __name__ == "__main__":
    # Railway сам назначает порт через переменную окружения PORT.
    # Если её нет (например, тестируете локально на своём компьютере) — используем 5000.
    port = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", 5000)))
    print(f"📊 FILMIX Dashboard запущен на порту {port}")
    print(f"🔑 Пароль: {DASHBOARD_PASSWORD}")
    app.run(host="0.0.0.0", port=port)
