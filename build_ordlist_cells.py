#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Резолвер складских ячеек для листа сборки ЯМ: читает ordlist/articles.json,
ищет товары в bd2 (products_s + shelf_box_items_s + shelf_boxes_s) по артикулу,
пишет ordlist/cells.json в формате, который ждут build_ordlist_sheet/assembly."""
import os, sys, io, json, re
sys.stdout.reconfigure(encoding="utf-8")
import psycopg2

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "ordlist")
DB = dict(host=os.environ.get("WMS_DB_HOST", ""), port=int(os.environ.get("WMS_DB_PORT", "5432")),
          dbname=os.environ.get("WMS_DB_NAME", ""), user=os.environ.get("WMS_DB_USER", ""),
          password=os.environ.get("WMS_DB_PASSWORD", ""), sslmode="disable", connect_timeout=10)

articles = json.load(io.open(os.path.join(OUT, "articles.json"), encoding="utf-8"))
# штрихкоды по offerId из выгрузки (для fallback, когда код Яндекса != код склада)
try:
    _maps = json.load(io.open(os.path.join(OUT, "orddata.json"), encoding="utf-8")).get("maps", {})
except Exception:
    _maps = {}
base_art = lambda a: re.sub(r"_\d+$", "", str(a or "").strip().upper())

import time
conn = None
for att in range(6):
    try:
        conn = psycopg2.connect(**DB); break
    except Exception as ex:
        print("   retry connect", att + 1, str(ex)[:60]); time.sleep(2 + att)
if conn is None:
    raise SystemExit("Не удалось подключиться к bd2")
conn.autocommit = True
cur = conn.cursor()


SEL = "select id, article, name, coalesce(barcode_list,''), entity_type from products_s "


def find_product(offer):
    cur.execute(SEL + "where upper(article)=upper(%s) limit 1", (offer,))
    r = cur.fetchone()
    if r:
        return r, "exact"
    cur.execute(SEL + "where upper(regexp_replace(article,'_\\d+$',''))=%s and entity_type is distinct from 'bundle' limit 1", (base_art(offer),))
    r = cur.fetchone()
    if r:
        return r, "base"
    # fallback по штрихкоду из карточки Яндекса (MRKT/OZN/EAN есть в barcode_list склада)
    bc = (_maps.get(offer) or {}).get("barcode") or ""
    if bc:
        cur.execute(SEL + "where entity_type is distinct from 'bundle' and position(%s in coalesce(barcode_list,''))>0 limit 1", (bc,))
        r = cur.fetchone()
        if r:
            return r, "barcode"
    return None, ""


def get_cells(pid):
    cur.execute("select b.name, i.quantity from shelf_box_items_s i "
                "join shelf_boxes_s b on b.id=i.shelf_box_id where i.product_id=%s "
                "order by (i.quantity>0) desc, i.quantity desc, b.name", (pid,))
    return [{"cell": name, "qty": float(qty or 0)} for name, qty in cur.fetchall()]


result = {}
found = miss = nocell = 0
for offer in articles:
    p, how = find_product(offer)
    if not p:
        result[offer] = {"found": False}
        miss += 1
        print("  ! нет в складе:", offer)
        continue
    pid, art, name, bl, etype = p
    cells = [c for c in get_cells(pid) if c["qty"] > 0] or get_cells(pid)
    if how != "exact":
        print(f"  ~ {offer} -> склад {art} (по {how})")
    result[offer] = {
        "found": True, "matched": how,
        "product_id": pid, "sklad_article": art, "sklad_name": name,
        "barcode_list": bl, "cells": cells,
    }
    found += 1
    if not any(c["qty"] > 0 for c in cells):
        nocell += 1
        print("  ~ нет ячейки с остатком:", offer, "->", art)

json.dump(result, io.open(os.path.join(OUT, "cells.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
cur.close(); conn.close()
print(f"cells.json: найдено {found}, нет в складе {miss}, без ячейки {nocell} (всего {len(articles)})")
