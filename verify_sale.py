#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Финальная проверка: пополненные единичные не скрыты и статус PUBLISHED."""
import os, json, requests
from concurrent.futures import ThreadPoolExecutor

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})

SETS = {
 "GRA-00040","GRA-00090","GRA-00180","GRA-08220","GRA-00080","GRA-00190",
 "GRA-00220","GRA-00150","GRA-00070","GRA-04730","GRA-00130","GRA-00210",
 "GRA-04520","GRA-00350","GRA-07950","GRA-04490","GRA-04590","GRA-00280",
 "GRA-00030","GRA-04481","GRA-00170","GRA-00140","GRA-07840","GRA-01502",
 "GRA-04401","GRA-04400","GRA-07920","GRA-00120","GRA-00240","GRA-00060",
 "GRA-00230","GRA-00110","GRA-00250","GRA-00160","GRA-02000",
}
cat = {r["offerId"]: r for r in json.load(open("catalog_named.json", encoding="utf-8"))}
singles = [o for o in cat if o not in SETS]
replenished = [o for o in singles if cat[o]["fit"] < 400]

r = S.get(f"{BASE}/campaigns/{CID}/hidden-offers", params={"limit": 200}, timeout=60)
hid = {h["offerId"] for h in r.json().get("result", {}).get("hiddenOffers", [])}

# статусы пачкой
statuses = {}
for i in range(0, len(replenished), 100):
    chunk = replenished[i:i+100]
    rr = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-mappings",
                params={"limit": 100}, json={"offerIds": chunk}, timeout=60)
    for m in rr.json().get("result", {}).get("offerMappings", []):
        off = m.get("offer", {})
        st = None
        for c in off.get("campaigns", []):
            if c.get("campaignId") == CID:
                st = c.get("status")
        statuses[off.get("offerId")] = st

still_hidden = [o for o in replenished if o in hid]
by_status = {}
for o in replenished:
    by_status.setdefault(statuses.get(o), []).append(o)

print(f"Пополнено единичных: {len(replenished)}")
print(f"Ещё в скрытых: {len(still_hidden)} {still_hidden}")
print("Статусы по кабинету 107803271:")
for st, lst in sorted(by_status.items(), key=lambda x: str(x[0])):
    print(f"  {st}: {len(lst)}")
    if st != "PUBLISHED":
        print("     ", lst)
