import gspread

gc = gspread.service_account(filename="d:/Downloads/gscapi-390409-4a9cf4824d2c.json")
sh = gc.open_by_key("1SPvZyiIYyAQHmmg2tkW6jA_iPiBWTQHRm2lqUlVD9AA")
ws = sh.worksheet("Задания")
rows = ws.get_all_records()
print("Прочитал строк:", len(rows))
print(rows[:2])  # первые 2 строки
