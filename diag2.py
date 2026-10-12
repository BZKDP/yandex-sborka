#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Повтор снятия GRA-08200 + причины DISABLED_AUTOMATICALLY / REJECTED."""
import os, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})

# 1) повтор снятия скрытия
r = S.delete(f"{BASE}/campaigns/{CID}/hidden-offers",
             json={"hiddenOffers": [{"offerId": "GRA-08200"}]}, timeout=60)
print("re-unhide GRA-08200:", r.status_code, r.text[:200])

problem = ['GRA-07760', 'GRA-00270', 'GRA-08160', 'GRA-00011',
           'GRA-04600', 'GRA-06984', 'GRA-07740', 'GRA-08210']

# 2) offer-cards: статус карточки + ошибки
print("\n=== offer-cards ===")
r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-cards",
           params={"limit": 50}, json={"offerIds": problem}, timeout=60)
print("status", r.status_code)
data = r.json().get("result", {}).get("offerCards", [])
for c in data:
    oid = c.get("offerId")
    cs = c.get("cardStatus")
    errs = c.get("errors") or []
    warns = c.get("warnings") or []
    print(f"\n{oid}: cardStatus={cs}")
    for e in errs:
        print("   ERR:", e)
    for w in warns[:5]:
        print("   warn:", w.get("type"), w.get("message", "")[:100])
