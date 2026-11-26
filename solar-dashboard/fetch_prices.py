#!/usr/bin/env python3
"""Hent danske spotpriser (DK1 og DK2) fra Energi Data Service og gem dem som timepriser.

Kilder:
  - Elspotprices      (timepriser, til og med 30. september 2025)
  - DayAheadPrices    (kvartersprisser fra 1. oktober 2025; samles til timegennemsnit)

Resultat: prices.json ved siden af dette script:
  {"generated": "...", "unit": "DKK/kWh", "start": "YYYY-MM-DD",
   "areas": {"DK1": [[24 timepriser] | null, ...], "DK2": [...]}}
Dag nummer i i listen er start + i dage (dansk lokal dato, time 0-23 dansk tid).

Brug:  python3 fetch_prices.py [startdato]
"""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

API = "https://api.energidataservice.dk/dataset/"
AREAS = ["DK1", "DK2"]
SWITCH = dt.date(2025, 10, 1)


def fetch(dataset, start, end, columns):
    q = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "filter": json.dumps({"PriceArea": AREAS}),
        "columns": columns,
        "limit": 0,
    }
    url = API + dataset + "?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)["records"]


def main():
    start = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date(2024, 1, 1)
    end = dt.date.today() + dt.timedelta(days=2)
    # sums[area][date][hour] = [sum, count]
    sums = {a: defaultdict(lambda: [[0.0, 0] for _ in range(24)]) for a in AREAS}

    def add(area, time_dk, dkk_mwh):
        if dkk_mwh is None:
            return
        t = dt.datetime.fromisoformat(time_dk)
        cell = sums[area][t.date()][t.hour]
        cell[0] += dkk_mwh / 1000.0
        cell[1] += 1

    if start < SWITCH:
        for r in fetch("Elspotprices", start, min(end, SWITCH), "HourDK,PriceArea,SpotPriceDKK"):
            add(r["PriceArea"], r["HourDK"], r["SpotPriceDKK"])
    for r in fetch("DayAheadPrices", max(start, SWITCH), end, "TimeDK,PriceArea,DayAheadPriceDKK"):
        add(r["PriceArea"], r["TimeDK"], r["DayAheadPriceDKK"])

    last = max(d for a in AREAS for d in sums[a])
    ndays = (last - start).days + 1
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "source": "Energi Data Service (Energinet): Elspotprices og DayAheadPrices",
        "unit": "DKK/kWh",
        "start": start.isoformat(),
        "last": last.isoformat(),
        "areas": {},
    }
    for a in AREAS:
        days = []
        for i in range(ndays):
            d = start + dt.timedelta(days=i)
            if d not in sums[a]:
                days.append(None)
                continue
            cells = sums[a][d]
            hours = [round(s / n, 4) if n else None for s, n in cells]
            # sommertid: en time mangler -> brug naboens pris
            for h in range(24):
                if hours[h] is None:
                    hours[h] = next((hours[k] for k in (h - 1, h + 1) if 0 <= k < 24 and hours[k] is not None), None)
            days.append(hours if None not in hours else None)
        out["areas"][a] = days
    path = Path(__file__).with_name("prices.json")
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"Gemte {path} · {start} – {last} · {ndays} dage")


if __name__ == "__main__":
    main()
