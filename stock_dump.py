#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Выгрузка текущих остатков FBS по кабинету 'Яндекс маркет ИП' (107803271)."""
import os, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
H = {"Api-Key": TOKEN, "Content-Type": "application/json"}
S = requests.Session()
S.headers.update(H)

all_skus = []
page_token = None
while True:
    params = {"limit": 200}
    if page_token:
        params["page_token"] = page_token
    r = S.post(f"{BASE}/campaigns/{CID}/offers/stocks",
               params=params, json={"withTurnover": False}, timeout=60)
    if r.status_code != 200:
        print("status", r.status_code, r.text[:1500]); raise SystemExit
    d = r.json().get("result", {})
    warehouses = d.get("warehouses", [])
    for w in warehouses:
        wid = w.get("warehouseId")
        for off in w.get("offers", []):
            stocks = off.get("stocks", [])
            fit = sum(s.get("count", 0) for s in stocks if s.get("type") == "FIT")
            total = sum(s.get("count", 0) for s in stocks)
            all_skus.append({
                "warehouseId": wid,
                "offerId": off.get("offerId"),
                "fit": fit,
                "total": total,
                "stocks": stocks,
            })
    page_token = r.json().get("paging", {}).get("nextPageToken")
    if not page_token:
        break

whids = sorted({s["warehouseId"] for s in all_skus})
print("warehouseIds:", whids)
print("SKU всего:", len(all_skus))
with open("stocks_current.json", "w", encoding="utf-8") as f:
    json.dump(all_skus, f, ensure_ascii=False, indent=1)
print("-> stocks_current.json")
