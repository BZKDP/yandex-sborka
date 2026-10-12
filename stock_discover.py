#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Разведка: проверить ключ, найти кабинет 'Яндекс маркет ИП' и его склады."""
import os, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
H = {"Api-Key": TOKEN, "Content-Type": "application/json"}
S = requests.Session()
S.headers.update(H)

print("=== GET /campaigns ===")
r = S.get(f"{BASE}/campaigns", timeout=60)
print("status:", r.status_code)
try:
    d = r.json()
except Exception:
    print(r.text[:2000]); raise SystemExit
for c in d.get("campaigns", []):
    print(f"  campaignId={c.get('id')}  business={c.get('business',{}).get('id')}  "
          f"domain={c.get('domain')}  placementType={c.get('placementType')}  "
          f"clientId={c.get('clientId')}")

print("\n=== склады по кабинетам (FBS/DBS) ===")
for c in d.get("campaigns", []):
    cid = c.get("id")
    rw = S.get(f"{BASE}/campaigns/{cid}/warehouses", timeout=60)
    if rw.status_code != 200:
        print(f"  campaign {cid}: warehouses status {rw.status_code}")
        continue
    whs = rw.json().get("result", {}).get("warehouses", [])
    for w in whs:
        addr = w.get("address", {})
        print(f"  campaign {cid}: warehouseId={w.get('id')}  name={w.get('name')!r}  "
              f"addr={addr}")
