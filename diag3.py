#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ценовой карантин: старые/новые цены по 7 офферам + детальный вердикт GRA-08210."""
import os, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})

quar = ['GRA-07760', 'GRA-00270', 'GRA-08160', 'GRA-00011',
        'GRA-04600', 'GRA-06984', 'GRA-07740']

# 1) Ценовой карантин — список с ценами
print("=== price-quarantine ===")
r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/price-quarantine",
           params={"limit": 200}, json={}, timeout=60)
print("status", r.status_code)
if r.status_code == 200:
    items = r.json().get("result", {}).get("offers", [])
    print("в карантине всего:", len(items))
    for it in items:
        oid = it.get("offerId")
        cur = it.get("currentPrice", {})
        old = it.get("oldPrice", {})
        print(f"  {oid}: было {old.get('value')} -> стало {cur.get('value')} {cur.get('currencyId','')}")
else:
    print(r.text[:800])

# 2) Детальные вердикты по проблемным (offer-mappings verdicts?)
print("\n=== GRA-08210 подробно (offer-cards raw) ===")
r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-cards",
           params={"limit": 5}, json={"offerIds": ["GRA-08210"]}, timeout=60)
print(json.dumps(r.json(), ensure_ascii=False, indent=1)[:3500])
