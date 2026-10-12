#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""По списку offerId из stocks_current.json подтянуть названия/фото и собрать таблицу."""
import os, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
H = {"Api-Key": TOKEN, "Content-Type": "application/json"}
S = requests.Session()
S.headers.update(H)


def fix_moji(s):
    if not s:
        return s
    try:
        return s.encode("cp1251").decode("utf-8")
    except Exception:
        return s


stocks = json.load(open("stocks_current.json", encoding="utf-8"))
offer_ids = [s["offerId"] for s in stocks]
cur = {s["offerId"]: s["fit"] for s in stocks}

maps = {}
for i in range(0, len(offer_ids), 200):
    chunk = offer_ids[i:i + 200]
    r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-mappings",
               params={"limit": 200}, json={"offerIds": chunk}, timeout=60)
    r.raise_for_status()
    for m in r.json().get("result", {}).get("offerMappings", []):
        off = m.get("offer", {})
        oid = off.get("offerId")
        pics = off.get("pictures") or []
        maps[oid] = {
            "name": fix_moji(off.get("name", "")),
            "picture": pics[0] if pics else "",
        }

rows = []
for oid in offer_ids:
    m = maps.get(oid, {})
    rows.append({
        "offerId": oid,
        "name": m.get("name", ""),
        "fit": cur.get(oid, 0),
        "picture": m.get("picture", ""),
    })
rows.sort(key=lambda x: x["name"].lower())

with open("catalog_named.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

# плоский текст для чтения
with open("catalog_named.txt", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(f"{r['offerId']}\t{r['fit']:>4}\t{r['name']}\n")

print("SKU:", len(rows), "-> catalog_named.json / catalog_named.txt")
