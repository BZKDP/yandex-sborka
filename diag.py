#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, io, sys, time, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
CAMPAIGNS = {148949326: "Склад Ижевск", 148851177: "GraFLab 2", 107803271: "Яндекс маркет ИП",
             130070191: "Яндекс маркет ИП 2", 148851174: "ЯМ ИП Экспресс"}
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})
S.mount("https://", HTTPAdapter(max_retries=Retry(total=6, connect=6, read=6, backoff_factor=1.5,
        status_forcelist=[420, 429, 500, 502, 503, 504], allowed_methods=None)))


def fix(s):
    try:
        return s.encode("cp1251").decode("utf-8")
    except Exception:
        return s


rows = []
for cid, cname in CAMPAIGNS.items():
    r = S.put(f"{BASE}/campaigns/{cid}/first-mile/shipments",
              json={"dateFrom": "2026-08-01", "dateTo": "2026-10-01"}, timeout=90)
    for s in r.json().get("result", {}).get("shipments", []):
        # детальный запрос за availableActions + placesCount
        d = S.get(f"{BASE}/campaigns/{cid}/first-mile/shipments/{s['id']}", timeout=90).json().get("result", {})
        rows.append((cid, cname, d))

# скрываем завершённые прошлые
active = [r for r in rows if r[2].get("currentStatus", {}).get("status") != "FINISHED"
          and r[2].get("status") != "FINISHED"]
rows.sort(key=lambda x: x[2].get("planIntervalFrom", ""))

print("ВСЕ ОТГРУЗКИ (кроме завершённых-уехавших):\n")
for cid, cname, d in rows:
    st = d.get("currentStatus", {})
    stype = st.get("status") if isinstance(st, dict) else d.get("status")
    if stype == "FINISHED":
        continue
    sid = d["id"]
    date = d.get("planIntervalFrom", "")[:10]
    acts = d.get("availableActions") or []
    pc = d.get("palletsCount") or {}
    sig = d.get("signature", {}).get("signed")
    n = len(d.get("orderIds", []))
    print(f"#{sid} | {cname:16} | {date} | {n:3} зак | статус={stype}")
    print(f"     placesCount(мест)={pc} | подписан={sig}")
    print(f"     можно сделать: {acts}")
    print()
