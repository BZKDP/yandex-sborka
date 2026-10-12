#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, json, requests
TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})
for oid in ["GRA-07502", "GRA-04550", "GRA-07810"]:
    body = {"skus": [{"sku": oid, "items": [{"count": 400}]}]}
    r = S.put(f"{BASE}/campaigns/{CID}/offers/stocks", json=body, timeout=90)
    print(oid, r.status_code, r.text[:400])
