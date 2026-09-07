import asyncio
import json
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

URL = "https://www.surf-forecast.com/breaks/Saltstein/forecasts/latest/six_day"
JSON_FILE = "surf_esp32.json"


def rens_verdi(tekst: str) -> float:
    if not tekst:
        return 0.0

    ren = tekst.replace("\xa0", "").strip()
    if ren in ["-", "–", "—", ""] or not re.search(r"\d", ren):
        return 0.0

    try:
        return float(ren)
    except ValueError:
        return 0.0


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_selector(".forecast-table__content", state="visible")

        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    time_row = soup.select_one(".forecast-table__table > thead:nth-child(1) > tr:nth-child(3)")
    tbody2 = soup.select_one(".forecast-table__table > tbody:nth-child(2)")

    if not time_row or not tbody2:
        print("Kunne ikke finne tabellelementene.")
        return

    row_periode = tbody2.select_one("tr:nth-child(3)")
    row_energi = tbody2.select_one("tr:nth-child(5)")

    first_td = time_row.select_one("td.forecast-table__cell:nth-child(1) > div:nth-child(1) > span:nth-child(1)")
    first_time = first_td.get_text().strip().upper() if first_td else ""

    drop_count = 0
    if "AM" in first_time:
        drop_count = 3
    elif "PM" in first_time:
        drop_count = 2
    elif "NIGHT" in first_time:
        drop_count = 1

    col_idx = 1 + drop_count
    imorgen = datetime.now().date() + timedelta(days=1)
    
    visnings_indeks = 0

    # Initialiserer en fast liste for ukedagene (0 = Mandag, 1 = Tirsdag, ..., 6 = Søndag)
    dager_status = [False] * 7

    while True:
        td_time = time_row.select_one(f"td.forecast-table__cell:nth-child({col_idx})")
        if not td_time:
            break

        span_time = td_time.select_one("div:nth-child(1) > span:nth-child(1)")
        raw_time = span_time.get_text().strip().upper() if span_time else ""

        if not raw_time or not any(t in raw_time for t in ["AM", "PM", "NIGHT"]):
            break

        # Beregn faktisk dato og finn ukedagsindeks (0 = Mandag, 6 = Søndag)
        dager_offset = visnings_indeks // 3
        dato_obj = imorgen + timedelta(days=dager_offset)
        ukedag_idx = dato_obj.weekday()

        # Hent periode og energi
        data_col_idx = col_idx + 1

        td_periode = row_periode.select_one(f"td:nth-child({data_col_idx})") if row_periode else None
        if td_periode:
            sub_div = td_periode.select_one("div:nth-child(1) > div:nth-child(3)") or td_periode.select_one("div:nth-child(1) > div:nth-child(1)")
            raw_periode = sub_div.get_text() if sub_div else td_periode.get_text()
        else:
            raw_periode = "0"

        td_energi = row_energi.select_one(f"td:nth-child({data_col_idx})") if row_energi else None
        if td_energi:
            div_energi = td_energi.select_one("div:nth-child(1)")
            raw_energi = div_energi.get_text() if div_energi else td_energi.get_text()
        else:
            raw_energi = "0"

        periode_num = rens_verdi(raw_periode)
        energi_num = rens_verdi(raw_energi)

        # Hvis ett tidsrom den dagen er bra, settes ukedagens status til True
        if periode_num >= 6 and energi_num >= 110:
            dager_status[ukedag_idx] = True

        col_idx += 1
        visnings_indeks += 1

    # ESP32 får kun en superenkel liste med 1 (True) eller 0 (False) for hver ukedag
    esp32_data = [1 if status else 0 for status in dager_status]

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(esp32_data, f)

    print("Data lagret for ESP32 (Mandag = index 0):")
    print(esp32_data)


if __name__ == "__main__":
    asyncio.run(main())
