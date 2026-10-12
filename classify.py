#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Классификация SKU на единичные (single) и комплекты (set) по названию."""
import json, re

rows = json.load(open("catalog_named.json", encoding="utf-8"))

# Признаки комплекта в названии
SET_PATTERNS = [
    r"набор",                       # "Набор ...", "набор GraFLab"
    r"\d+\s*банк",                  # 2 банки, 3 банки, 2 банок
    r"\d+\s*упаковк",               # 2 упаковки, 2 упаковок
    r"\d+\s*шт\s*по",               # 2 шт по 60
    r"\d+\s*[x×х]\s*\d+",           # 2×60, 2x60, 2х60
]
SET_RE = re.compile("|".join(SET_PATTERNS), re.IGNORECASE)

# Отдельные спорные — решаются вручную/по фото
AMBIGUOUS = {
    "GRA-02000",  # "Берберин и Пиколинат хрома ... по 60 капсул" — два разных по 60?
}

sets, singles, amb = [], [], []
for r in rows:
    name = r["name"]
    oid = r["offerId"]
    if oid in AMBIGUOUS:
        amb.append(r)
    elif SET_RE.search(name):
        sets.append(r)
    else:
        singles.append(r)

def dump(title, lst):
    print(f"\n===== {title}: {len(lst)} =====")
    for r in lst:
        print(f"  {r['offerId']:<12} fit={r['fit']:>4}  {r['name']}")

dump("КОМПЛЕКТЫ (исключаем)", sets)
dump("СПОРНЫЕ (проверить фото)", amb)
dump("ЕДИНИЧНЫЕ (-> 400)", singles)

json.dump({"sets": sets, "singles": singles, "ambiguous": amb},
          open("classified.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\nИТОГО: single={len(singles)} set={len(sets)} amb={len(amb)} всего={len(rows)}")
