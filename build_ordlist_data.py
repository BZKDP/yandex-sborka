#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Лист подбора по СПИСКУ заказов Яндекс.Маркет (campaign 107803271) + склейка этикеток."""
import os, sys, io, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from pypdf import PdfReader, PdfWriter
sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ.get("YM_API_KEY", "")
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
CNAME = os.environ.get("YM_CAMPAIGN_NAME", "Яндекс маркет ИП")
BASE = "https://api.partner.market.yandex.ru"
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "ordlist")
IMG = os.path.join(ROOT, "images")
LBL = os.path.join(OUT, "labels")
os.makedirs(OUT, exist_ok=True); os.makedirs(IMG, exist_ok=True); os.makedirs(LBL, exist_ok=True)
S = requests.Session(); S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})
ORDERS = json.load(io.open(os.path.join(OUT, "orders.json"), encoding="utf-8"))


def fix_moji(s):
    if not s:
        return s
    try:
        return s.encode("cp1251").decode("utf-8")
    except Exception:
        return s


def api_get(path, **kw):
    for att in range(6):
        try:
            r = S.get(BASE + path, timeout=60, **kw)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (420, 429, 500, 502, 503):
                time.sleep(1.5 + att * 1.5); continue
            print("  ! GET", path, r.status_code); return None
        except Exception:
            time.sleep(1.5)
    return None


def get_order(oid):
    d = api_get(f"/campaigns/{CID}/orders/{oid}")
    return (d or {}).get("order")


def get_mappings(offer_ids):
    res = {}
    ids = list(offer_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        for att in range(5):
            try:
                r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-mappings", params={"limit": 200},
                           json={"offerIds": chunk}, timeout=60)
                if r.status_code == 200:
                    for m in r.json().get("result", {}).get("offerMappings", []):
                        off = m.get("offer", {})
                        oid = off.get("offerId")
                        pics = off.get("pictures") or []
                        res[oid] = {"name": fix_moji(off.get("name", "")),
                                    "picture": pics[0] if pics else "",
                                    "barcode": (off.get("barcodes") or [""])[0]}
                    break
                time.sleep(1.5)
            except Exception:
                time.sleep(1.5)
    return res


def download(url, path):
    try:
        r = S.get(url, timeout=60)
        if r.status_code == 200 and r.content:
            open(path, "wb").write(r.content); return True
    except Exception:
        pass
    return False


def get_label(oid, path):
    for att in range(6):
        try:
            r = S.get(f"{BASE}/campaigns/{CID}/orders/{oid}/delivery/labels", params={"format": "A9"}, timeout=90)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                open(path, "wb").write(r.content); return True
            if r.status_code in (420, 429, 500, 503):
                time.sleep(2 + att * 2); continue
            print("  ! label", oid, r.status_code); return False
        except Exception:
            time.sleep(2)
    return False


def main():
    print(f"Заказов в списке: {len(ORDERS)}")
    orders = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(get_order, o): o for o in ORDERS}
        for f in as_completed(futs):
            o = f.result()
            if o:
                orders.append(o)
            else:
                print("  ! не получен заказ", futs[f])
    orders.sort(key=lambda x: str(x.get("id")))
    print(f"Получено составов: {len(orders)}")

    offer_ids = set()
    for o in orders:
        for it in o.get("items", []):
            if it.get("offerId"):
                offer_ids.add(it["offerId"])
    print(f"Артикулов: {len(offer_ids)}")
    maps = get_mappings(offer_ids)

    print("Фото…")
    photo_rel = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {}
        for oid in offer_ids:
            url = maps.get(oid, {}).get("picture")
            if not url:
                continue
            if url.endswith("/orig"):
                url = url[:-5] + "/300x300"
            p = os.path.join(IMG, f"{oid}.jpg")
            photo_rel[oid] = f"images/{oid}.jpg"
            if os.path.exists(p) and os.path.getsize(p) > 0:
                continue
            futs[ex.submit(download, url, p)] = oid
        for f in as_completed(futs):
            f.result()

    print("Этикетки (A9 40×58)…")
    ok = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {}
        for o in orders:
            p = os.path.join(LBL, f"{o['id']}.pdf")
            if os.path.exists(p) and os.path.getsize(p) > 0:
                ok[str(o["id"])] = p; continue
            futs[ex.submit(get_label, o["id"], p)] = (str(o["id"]), p)
        for f in as_completed(futs):
            oid, p = futs[f]
            if f.result():
                ok[oid] = p
    # склейка этикеток в порядке списка
    writer = PdfWriter(); merged = 0
    for oid in [str(o["id"]) for o in orders]:
        p = ok.get(oid)
        if p and os.path.exists(p):
            for pg in PdfReader(p).pages:
                writer.add_page(pg)
            merged += 1
    down = os.environ.get("YM_OUTPUT_DIR", os.path.join(os.path.expanduser("~"), "Downloads"))
    labels_pdf = os.path.join(down, f"Этикетки ЯМ {len(orders)} заказов.pdf")
    with open(labels_pdf, "wb") as f:
        writer.write(f)
    print(f"Этикеток склеено: {merged} -> {labels_pdf}")

    data = {
        "campaign": CID, "cname": CNAME, "generated": time.strftime("%d.%m.%Y %H:%M"),
        "maps": maps, "photo_rel": photo_rel,
        "orders": [{
            "id": str(o.get("id")), "status": o.get("status"), "substatus": o.get("substatus"),
            "recipient": ((o.get("buyer") or {}).get("firstName", "") + " " + (o.get("buyer") or {}).get("lastName", "")).strip(),
            "outlet": ((o.get("delivery") or {}).get("outlet") or {}).get("name") or (o.get("delivery") or {}).get("serviceName"),
            "city": ((o.get("delivery") or {}).get("region") or {}).get("name") or ((o.get("delivery") or {}).get("address") or {}).get("city"),
            "has_label": str(o.get("id")) in ok,
            "items": [{"offerId": it.get("offerId"), "count": it.get("count", 0), "name": fix_moji(it.get("offerName", ""))}
                      for it in o.get("items", [])],
        } for o in orders],
    }
    json.dump(data, io.open(os.path.join(OUT, "orddata.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sorted(offer_ids), io.open(os.path.join(OUT, "articles.json"), "w", encoding="utf-8"), ensure_ascii=False)
    units = sum(it["count"] for o in data["orders"] for it in o["items"])
    print(f"СОХРАНЕНО ordlist/orddata.json + articles.json | {len(orders)} заказов, {units} шт")
    miss = [o for o in ORDERS if o not in [str(x['id']) for x in orders]]
    if miss:
        print("НЕ получены заказы:", miss)


if __name__ == "__main__":
    main()
