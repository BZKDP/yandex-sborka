#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Выгрузка отгрузок Яндекс.Маркет FBS: заказы+состав+фото+мэппинг."""
import os, sys, io, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ.get("YM_API_KEY", "")
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
CID = int(os.environ.get("YM_CAMPAIGN_ID", "0"))
CNAME = os.environ.get("YM_CAMPAIGN_NAME", "Яндекс маркет ИП")
# id отгрузок через запятую в YM_SHIPMENTS, напр. "89468451,89380455"
SHIPMENTS = [int(x) for x in os.environ.get("YM_SHIPMENTS", "").split(",") if x.strip()]
BASE = "https://api.partner.market.yandex.ru"
ROOT = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(ROOT, "images")
os.makedirs(IMG, exist_ok=True)
S = requests.Session()
S.headers.update({"Api-Key": TOKEN, "Content-Type": "application/json"})


def api_get(path, **kw):
    for att in range(6):
        try:
            r = S.get(BASE + path, timeout=60, **kw)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (420, 429, 500, 502, 503):
                time.sleep(1.5 + att * 1.5); continue
            print("  ! GET", path, r.status_code, r.text[:120]); return None
        except Exception as e:
            print("  ! GET fail", path, str(e)[:80]); time.sleep(1.5)
    return None


def api_post(path, body, **kw):
    for att in range(6):
        try:
            r = S.post(BASE + path, json=body, timeout=60, **kw)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (420, 429, 500, 502, 503):
                time.sleep(1.5 + att * 1.5); continue
            print("  ! POST", path, r.status_code, r.text[:120]); return None
        except Exception as e:
            print("  ! POST fail", path, str(e)[:80]); time.sleep(1.5)
    return None


def fix_moji(s):
    if not s:
        return s
    try:
        return s.encode("cp1251").decode("utf-8")
    except Exception:
        return s


def get_order(oid):
    d = api_get(f"/campaigns/{CID}/orders/{oid}")
    return (d or {}).get("order")


def get_mappings(offer_ids):
    res = {}
    ids = list(offer_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        d = api_post(f"/businesses/{BUSINESS_ID}/offer-mappings", {"offerIds": chunk}, params={"limit": 200})
        for m in (d or {}).get("result", {}).get("offerMappings", []):
            off = m.get("offer", {})
            oid = off.get("offerId")
            pics = off.get("pictures") or []
            res[oid] = {"name": fix_moji(off.get("name", "")),
                        "picture": pics[0] if pics else "",
                        "barcode": (off.get("barcodes") or [""])[0]}
    return res


def download(url, path):
    try:
        r = S.get(url, timeout=60)
        if r.status_code == 200 and r.content:
            open(path, "wb").write(r.content); return True
    except Exception:
        pass
    return False


def main():
    all_offer_ids = set()
    ship_data = {}
    for ship in SHIPMENTS:
        print(f"\n=== Отгрузка {ship} ===")
        info = api_get(f"/campaigns/{CID}/first-mile/shipments/{ship}")
        res = (info or {}).get("result", {})
        oids = res.get("orderIds") or []
        wh = res.get("warehouse", {})
        print(f"  заказов: {len(oids)} | склад: {wh.get('name')} | интервал: {res.get('planIntervalFrom')}..{res.get('planIntervalTo')}")
        orders = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(get_order, o): o for o in oids}
            for f in as_completed(futs):
                o = f.result()
                if o:
                    orders.append(o)
        orders.sort(key=lambda x: x.get("id"))
        print(f"  получено составов: {len(orders)}")
        for o in orders:
            for it in o.get("items", []):
                if it.get("offerId"):
                    all_offer_ids.add(it["offerId"])
        ship_data[ship] = {
            "shipment": ship,
            "warehouse": wh.get("name"),
            "planFrom": res.get("planIntervalFrom"), "planTo": res.get("planIntervalTo"),
            "deliveryService": (res.get("deliveryService") or {}).get("name"),
            "orders": [{
                "id": o.get("id"),
                "status": o.get("status"), "substatus": o.get("substatus"),
                "delivery": {
                    "type": (o.get("delivery") or {}).get("deliveryPartnerType"),
                    "serviceName": (o.get("delivery") or {}).get("serviceName"),
                    "outletName": ((o.get("delivery") or {}).get("outlet") or {}).get("name"),
                    "address": ((o.get("delivery") or {}).get("address") or {}).get("city"),
                },
                "recipient": ((o.get("buyer") or {}).get("firstName", "") + " " + (o.get("buyer") or {}).get("lastName", "")).strip(),
                "items": [{"offerId": it.get("offerId"), "count": it.get("count", 0),
                           "name": fix_moji(it.get("offerName", ""))} for it in o.get("items", [])],
            } for o in orders],
        }

    print(f"\n=== Мэппинг товаров ({len(all_offer_ids)} артикулов) ===")
    maps = get_mappings(all_offer_ids)
    print(f"  получено карточек: {len(maps)}")

    print("=== Фото ===")
    photo_rel = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {}
        for oid in all_offer_ids:
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
    print(f"  фото: {len(photo_rel)}")

    out = {"campaign": CID, "cname": CNAME, "generated": time.strftime("%d.%m.%Y %H:%M"),
           "maps": maps, "photo_rel": photo_rel, "shipments": ship_data}
    json.dump(out, io.open(os.path.join(ROOT, "ship", "shipdata.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # список артикулов для сервера
    json.dump(sorted(all_offer_ids), io.open(os.path.join(ROOT, "ship", "articles.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("\nСОХРАНЕНО ship/shipdata.json + ship/articles.json")
    for ship, sd in ship_data.items():
        units = sum(it["count"] for o in sd["orders"] for it in o["items"])
        print(f"  {ship}: {len(sd['orders'])} заказов, {units} шт")


if __name__ == "__main__":
    main()
