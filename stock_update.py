#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Пополнение единичных товаров до 400 шт на складе 1453898 (кабинет 'Яндекс маркет ИП').
Комплекты исключены. Товары с остатком >=400 не трогаем (режим 'пополнить до 400').
Запуск:  python stock_update.py       -> сухой прогон (ничего не пишет)
         python stock_update.py GO    -> запись остатков
"""
import os, sys, json, requests

TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
TARGET = 400
H = {"Api-Key": TOKEN, "Content-Type": "application/json"}
S = requests.Session()
S.headers.update(H)

# ===== КОМПЛЕКТЫ (исключаем из пополнения) — 35 шт =====
SETS = {
    # явные по названию (21)
    "GRA-00040", "GRA-00090", "GRA-00180", "GRA-08220", "GRA-00080",
    "GRA-00190", "GRA-00220", "GRA-00150", "GRA-00070", "GRA-04730",
    "GRA-00130", "GRA-00210", "GRA-04520", "GRA-00350", "GRA-07950",
    "GRA-04490", "GRA-04590", "GRA-00280", "GRA-00030", "GRA-04481",
    "GRA-00170",
    # скрытые (120/180 капсул = 2-3 банки, подтверждено фото) (13)
    "GRA-00140", "GRA-07840", "GRA-01502", "GRA-04401", "GRA-04400",
    "GRA-07920", "GRA-00120", "GRA-00240", "GRA-00060", "GRA-00230",
    "GRA-00110", "GRA-00250", "GRA-00160",
    # спорный, фото = набор 2 банки (1)
    "GRA-02000",
}

cat = {r["offerId"]: r for r in json.load(open("catalog_named.json", encoding="utf-8"))}
allids = list(cat.keys())

singles = [oid for oid in allids if oid not in SETS]
to_update = [oid for oid in singles if cat[oid]["fit"] < TARGET]
skip_high = [oid for oid in singles if cat[oid]["fit"] >= TARGET]

print(f"Всего SKU: {len(allids)}")
print(f"Комплектов (исключены): {len(SETS)}")
print(f"Единичных: {len(singles)}")
print(f"  -> к пополнению до {TARGET} (fit<{TARGET}): {len(to_update)}")
print(f"  -> оставлены как есть (fit>={TARGET}): {len(skip_high)}")
for oid in skip_high:
    print(f"       {oid} fit={cat[oid]['fit']}  {cat[oid]['name'][:55]}")

# контроль: комплекты все существуют в каталоге
missing = [s for s in SETS if s not in cat]
if missing:
    print("!! ВНИМАНИЕ, комплекты не найдены в каталоге:", missing)

if len(sys.argv) > 1 and sys.argv[1] == "GO":
    print("\n=== ЗАПИСЬ ОСТАТКОВ ===")
    ok = 0
    for i in range(0, len(to_update), 500):
        chunk = to_update[i:i + 500]
        body = {"skus": [{"sku": oid, "items": [{"count": TARGET}]} for oid in chunk]}
        r = S.put(f"{BASE}/campaigns/{CID}/offers/stocks", json=body, timeout=90)
        if r.status_code == 200:
            ok += len(chunk)
            print(f"  батч {i//500+1}: {len(chunk)} шт OK")
        else:
            print(f"  батч {i//500+1}: FAIL {r.status_code} {r.text[:500]}")
    print(f"Обновлено: {ok}/{len(to_update)}")
else:
    print("\n(сухой прогон — записи НЕ было; для записи: python stock_update.py GO)")
