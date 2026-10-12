#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Снять скрытие с пополненных единичных товаров (кабинет 107803271),
чтобы они пошли в продажу.
  python unhide.py            -> анализ + ТЕСТ снятия на 1 оффере (GRA-07502)
  python unhide.py GO         -> снять скрытие со всех пополненных
"""
import os, sys, json, requests

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
replenished = [o for o in singles if cat[o]["fit"] < 400]   # 61 пополненных


def hidden_now():
    r = S.get(f"{BASE}/campaigns/{CID}/hidden-offers", params={"limit": 200}, timeout=60)
    return {h["offerId"] for h in r.json().get("result", {}).get("hiddenOffers", [])}


hid = hidden_now()
target = [o for o in replenished if o in hid]
already_visible = [o for o in replenished if o not in hid]
print(f"Пополнено единичных: {len(replenished)}")
print(f"  из них СКРЫТО (надо открыть): {len(target)}")
print(f"  уже видимы: {len(already_visible)} {already_visible}")


def unhide(ids):
    body = {"hiddenOffers": [{"offerId": o} for o in ids]}
    r = S.delete(f"{BASE}/campaigns/{CID}/hidden-offers", json=body, timeout=90)
    return r.status_code, r.text[:400]


def status_of(oid):
    r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-mappings",
               params={"limit": 1}, json={"offerIds": [oid]}, timeout=60)
    off = r.json().get("result", {}).get("offerMappings", [{}])[0].get("offer", {})
    for c in off.get("campaigns", []):
        if c.get("campaignId") == CID:
            return c.get("status")
    return None


mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode == "GO":
    print("\n=== СНЯТИЕ СКРЫТИЯ СО ВСЕХ ===")
    ok = 0
    for i in range(0, len(target), 200):
        chunk = target[i:i+200]
        code, txt = unhide(chunk)
        print(f"  батч {i//200+1}: {len(chunk)} шт -> {code} {txt}")
        if code == 200:
            ok += len(chunk)
    print(f"Снято скрытие: {ok}/{len(target)}")
    left = hidden_now()
    still = [o for o in target if o in left]
    print(f"Осталось скрытыми из целевых: {len(still)} {still}")
else:
    test = "GRA-07502"
    print(f"\n=== ТЕСТ на {test} ===")
    print("статус ДО:", status_of(test))
    print("в скрытых ДО:", test in hidden_now())
    code, txt = unhide([test])
    print("DELETE:", code, txt)
    print("в скрытых ПОСЛЕ:", test in hidden_now())
    print("статус ПОСЛЕ:", status_of(test))
