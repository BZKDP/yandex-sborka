#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Диагностика: почему единичные не продаются. Полный статус офферов + скрытые."""
import os, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})

# 1) Полный дамп offer-mappings по паре офферов (структура/статусы)
r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-mappings",
           params={"limit": 5},
           json={"offerIds": ["GRA-07502", "GRA-07750", "GRA-08800"]}, timeout=60)
print("=== offer-mappings RAW ===")
print(json.dumps(r.json(), ensure_ascii=False, indent=1)[:7000])

# 2) Скрытые офферы кабинета
print("\n=== hidden-offers ===")
rh = S.get(f"{BASE}/campaigns/{CID}/hidden-offers", params={"limit": 200}, timeout=60)
print("status", rh.status_code)
try:
    hj = rh.json()
    hids = [h.get("offerId") for h in hj.get("result", {}).get("hiddenOffers", [])]
    print("скрытых:", len(hids))
    print(hids)
except Exception:
    print(rh.text[:1000])
