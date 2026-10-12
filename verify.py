#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка: свежие остатки FBS после пополнения."""
import os, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})

fresh = {}
page_token = None
while True:
    params = {"limit": 200}
    if page_token:
        params["page_token"] = page_token
    r = S.post(f"{BASE}/campaigns/{CID}/offers/stocks", params=params,
               json={"withTurnover": False}, timeout=60)
    r.raise_for_status()
    d = r.json().get("result", {})
    for w in d.get("warehouses", []):
        for off in w.get("offers", []):
            fit = sum(s.get("count", 0) for s in off.get("stocks", []) if s.get("type") == "FIT")
            fresh[off.get("offerId")] = fit
    page_token = r.json().get("paging", {}).get("nextPageToken")
    if not page_token:
        break

# те, что мы обновляли
SETS = set(json.load(open("classified.json", encoding="utf-8")) and [])  # placeholder
import importlib.util
spec = importlib.util.spec_from_file_location("su", "stock_update.py")
# вместо импорта (он выполнит запись) — просто перечитаем список из логики
cat = {r["offerId"]: r for r in json.load(open("catalog_named.json", encoding="utf-8"))}

# повторяем список SETS из stock_update.py
SETS = {
    "GRA-00040","GRA-00090","GRA-00180","GRA-08220","GRA-00080","GRA-00190",
    "GRA-00220","GRA-00150","GRA-00070","GRA-04730","GRA-00130","GRA-00210",
    "GRA-04520","GRA-00350","GRA-07950","GRA-04490","GRA-04590","GRA-00280",
    "GRA-00030","GRA-04481","GRA-00170","GRA-00140","GRA-07840","GRA-01502",
    "GRA-04401","GRA-04400","GRA-07920","GRA-00120","GRA-00240","GRA-00060",
    "GRA-00230","GRA-00110","GRA-00250","GRA-00160","GRA-02000",
}
singles = [oid for oid in cat if oid not in SETS]
updated = [oid for oid in singles if cat[oid]["fit"] < 400]

now400 = [o for o in updated if fresh.get(o) == 400]
not400 = [o for o in updated if fresh.get(o) != 400]
print(f"Обновляли: {len(updated)}")
print(f"  сейчас = 400: {len(now400)}")
print(f"  ещё не 400 (async задержка?): {len(not400)}")
for o in not400:
    print(f"     {o}: было {cat[o]['fit']} -> сейчас {fresh.get(o)}")

# контроль комплектов — что НЕ тронули
sets_changed = [s for s in SETS if fresh.get(s, 0) == 400 and cat[s]["fit"] != 400]
print(f"Комплекты, ставшие 400 (не должно быть): {sets_changed}")
