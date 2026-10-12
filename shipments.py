#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, io, sys, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOKEN = os.environ.get("YM_API_KEY", "")
BASE = "https://api.partner.market.yandex.ru"
H = {"Api-Key": TOKEN, "Content-Type": "application/json"}
CAMPAIGNS = {148949326: "Склад Ижевск", 148851177: "GraFLab 2", 107803271: "Яндекс маркет ИП"}


def fix(s):
    try:
        return s.encode("cp1251").decode("utf-8")
    except Exception:
        return s


rows = []
for cid, cname in CAMPAIGNS.items():
    r = requests.put(f"{BASE}/campaigns/{cid}/first-mile/shipments", headers=H,
                     json={"dateFrom": "2026-08-01", "dateTo": "2026-09-10"}, timeout=60)
    for s in r.json().get("result", {}).get("shipments", []):
        rows.append({
            "cid": cid, "cab": cname,
            "id": s["id"],
            "date": s.get("planIntervalFrom", "")[:10],
            "from": s.get("planIntervalFrom", "")[11:16],
            "to": s.get("planIntervalTo", "")[11:16],
            "status": fix(s.get("statusDescription", "")),
            "st": s.get("status", ""),
            "dest": fix(s.get("warehouseTo", {}).get("name", "")),
            "addr": fix(s.get("warehouseTo", {}).get("address", "")),
            "svc": fix(s.get("deliveryService", {}).get("name", "")),
            "n": len(s.get("orderIds", [])),
        })

rows.sort(key=lambda x: (x["date"], x["cab"]))
print(f"ВСЕГО ОТГРУЗОК: {len(rows)}, заказов в них: {sum(r['n'] for r in rows)}\n")
cur = None
for r in rows:
    if r["date"] != cur:
        cur = r["date"]
        print(f"\n=== ДАТА {r['date']} ===")
    active = "🔴 ВЕЗТИ" if r["st"] == "OUTBOUND_READY_FOR_CONFIRMATION" else ("✅ уехала" if r["st"] == "FINISHED" else r["st"])
    print(f"  #{r['id']} | {r['cab']:16} | {r['from']}-{r['to']} | {r['n']:3} зак | {active} ({r['status']})")
    print(f"       → сдать в: {r['dest']} · {r['addr']}")
