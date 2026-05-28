import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import os
from dotenv import load_dotenv
import time

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
BASE = "https://api.themoviedb.org/3"

all_movies = []

# Качаем популярные фильмы постранично (50 страниц = ~1000 фильмов)
for year in range(2010, 2025):
    for page in range(1, 4):  # 3 страницы на каждый год
        url = f"{BASE}/discover/movie"
        params = {
            "api_key": API_KEY,
            "language": "ru-RU",
            "sort_by": "popularity.desc",
            "primary_release_year": year,
            "page": page,
            "vote_count.gte": 100
        }
        r = requests.get(url, params=params)
        data = r.json()
        for m in data.get("results", []):
            all_movies.append((
                m["id"],
                m.get("title", "—"),
                str(m.get("genre_ids", ["?"])[:1]).strip("[]"),
                year,
                round(m.get("vote_average", 0), 1)
            ))
        time.sleep(0.3)
    print(f"Год {year} загружен — {len(all_movies)} фильмов")

# Убираем дубликаты
seen = set()
unique = []
for m in all_movies:
    if m[0] not in seen:
        seen.add(m[0])
        unique.append(m)

unique.sort(key=lambda x: (-x[3], -x[4]))
print(f"\nВсего уникальных: {len(unique)}")

# Пишем Excel
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Все фильмы"

red = PatternFill("solid", start_color="E50914", end_color="E50914")
hf = Font(bold=True, color="FFFFFF", size=11)
idf = Font(bold=True, color="C00000", size=11)
df = Font(color="111111", size=10)
alt = PatternFill("solid", start_color="FFF5F5", end_color="FFF5F5")
wht = PatternFill("solid", start_color="FFFFFF", end_color="FFFFFF")
thin = Side(style='thin', color="DDDDDD")
brd = Border(left=thin, right=thin, top=thin, bottom=thin)

ws.merge_cells("A1:F1")
ws["A1"] = f"🎬 CINEMATRIX — База фильмов TMDb ({len(unique)} фильмов)"
ws["A1"].font = Font(bold=True, color="FFFFFF", size=13)
ws["A1"].fill = red
ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[1].height = 28

for col, h in enumerate(["#", "TMDb ID (КОД)", "Название", "Жанр ID", "Год", "Рейтинг"], 1):
    c = ws.cell(row=2, column=col, value=h)
    c.font = hf; c.fill = red
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.border = brd

for i, (tid, title, genre, year, rating) in enumerate(unique, 1):
    r = i + 2
    fill = alt if i % 2 == 0 else wht
    for col, val in enumerate([i, tid, title, genre, year, f"⭐{rating}"], 1):
        c = ws.cell(row=r, column=col, value=val)
        c.fill = fill; c.border = brd
        c.alignment = Alignment(horizontal="center" if col != 3 else "left", vertical="center")
        c.font = idf if col == 2 else df
    ws.row_dimensions[r].height = 18

ws.column_dimensions["A"].width = 5
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 46
ws.column_dimensions["D"].width = 12
ws.column_dimensions["E"].width = 7
ws.column_dimensions["F"].width = 12

wb.save("CINEMATRIX_правильные_ID.xlsx")
print("✅ Файл сохранён: CINEMATRIX_правильные_ID.xlsx")