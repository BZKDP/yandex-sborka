#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Комплект для сборки ОДНОЙ отгрузки Яндекс.Маркет:
  папка out/Отгрузка_<id>_<кабинет>_<дата>/ с
    - Этикетки.pdf   (A9 40x58, только заказы этой отгрузки, по № заказа)
    - Лист_подбора.pdf (свод по товарам + поштучно, только эта отгрузка)

Запуск:
  python build_shipment.py <shipmentId>   — одна отгрузка
  python build_shipment.py active          — все «Можно обрабатывать»
"""
import sys, os, html, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pypdf import PdfReader, PdfWriter
import time
import build_all as BA
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# устойчивость к обрывам/таймаутам сети — ретраи на уровне сессии
_retry = Retry(total=6, connect=6, read=6, backoff_factor=1.5,
               status_forcelist=[420, 429, 500, 502, 503, 504], allowed_methods=None)
BA.S.mount("https://", HTTPAdapter(max_retries=_retry))

DATE_FROM, DATE_TO = "2026-08-01", "2026-10-01"
# ВСЕ FBS-кабинеты (не только те, где были заказы на старте)
FBS_CAMPAIGNS = {148949326: "Склад Ижевск", 148851177: "GraFLab 2", 107803271: "Яндекс маркет ИП",
                 130070191: "Яндекс маркет ИП 2", 148851174: "ЯМ ИП Экспресс"}
# ВАЖНО: без явного statuses список СКРЫВАЕТ OUTBOUND_CONFIRMED (готовые к отправке)!
SHIP_STATUSES = ["OUTBOUND_CREATED", "OUTBOUND_READY_FOR_CONFIRMATION", "OUTBOUND_CONFIRMED"]


def req(method, url, **kw):
    """HTTP с повторами при обрыве соединения/5xx."""
    last = None
    for attempt in range(6):
        try:
            r = BA.S.request(method, url, timeout=90, **kw)
            if r.status_code in (420, 429, 500, 502, 503):
                time.sleep(2 + attempt * 2)
                continue
            return r
        except Exception as e:
            last = e
            time.sleep(2 + attempt * 2)
    if last:
        raise last
    return r


def all_shipments():
    out = []
    seen = set()
    for cid, cname in FBS_CAMPAIGNS.items():
        r = req("PUT", f"{BA.BASE}/campaigns/{cid}/first-mile/shipments",
                json={"dateFrom": DATE_FROM, "dateTo": DATE_TO, "statuses": SHIP_STATUSES})
        for s in r.json().get("result", {}).get("shipments", []):
            if s["id"] in seen:
                continue
            seen.add(s["id"])
            out.append((cid, cname, s))
    return out


def get_order(cid, oid):
    r = BA.S.get(f"{BA.BASE}/campaigns/{cid}/orders/{oid}", timeout=60)
    return r.json().get("order", {})


def esc(s):
    return html.escape(str(s or ""))


def build_one(cid, cname, s):
    sid = s["id"]
    date = s.get("planIntervalFrom", "")[:10]
    order_ids = s.get("orderIds", [])
    dest = BA.fix_moji(s.get("warehouseTo", {}).get("name", ""))
    addr = BA.fix_moji(s.get("warehouseTo", {}).get("address", ""))
    safe_cab = cname.replace(" ", "")
    folder = os.path.join(BA.OUT, f"Отгрузка_{sid}_{safe_cab}_{date}")
    os.makedirs(folder, exist_ok=True)
    print(f"\n=== Отгрузка #{sid} · {cname} · {date} · {len(order_ids)} заказов ===")

    # детали заказов
    orders = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(get_order, cid, oid): oid for oid in order_ids}
        for f in as_completed(futs):
            o = f.result()
            if o:
                orders.append(o)
    orders.sort(key=lambda x: x["id"])

    # артикулы -> карточки (фото/имя)
    offer_ids = {it.get("offerId") for o in orders for it in o.get("items", [])}
    offer_ids.discard(None)
    maps = BA.get_mappings(offer_ids)
    # фото (в общий images/, размер 300x300)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {}
        for oid in offer_ids:
            url = maps.get(oid, {}).get("picture")
            if not url:
                continue
            if url.endswith("/orig"):
                url = url[:-5] + "/300x300"
            p = os.path.join(BA.IMG, f"{oid}.jpg")
            if os.path.exists(p) and os.path.getsize(p) > 0:
                continue
            futs[ex.submit(BA.download, url, p)] = oid
        for f in as_completed(futs):
            f.result()

    # этикетки A9
    lbls = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {}
        for o in orders:
            p = os.path.join(BA.LBL, f"{o['id']}.pdf")
            if os.path.exists(p) and os.path.getsize(p) > 0:
                lbls[o["id"]] = p
                continue
            futs[ex.submit(BA.get_label, cid, o["id"], p)] = (o["id"], p)
        for f in as_completed(futs):
            oid, p = futs[f]
            if f.result():
                lbls[oid] = p
    writer = PdfWriter()
    for o in orders:
        p = lbls.get(o["id"])
        if p:
            for pg in PdfReader(p).pages:
                writer.add_page(pg)
    lbl_pdf = os.path.join(folder, "Этикетки.pdf")
    with open(lbl_pdf, "wb") as f:
        writer.write(f)

    # проверка: у всех ли заказов готовы этикетки
    try:
        oi = BA.S.get(f"{BA.BASE}/campaigns/{cid}/first-mile/shipments/{sid}/orders/info",
                      timeout=60).json().get("result", {})
        no = oi.get("orderIdsWithoutLabels", [])
        if no:
            print("   ⚠ ЗАКАЗЫ БЕЗ ЭТИКЕТОК:", no)
    except Exception:
        pass

    # акт приёма-передачи (по складу-отправителю; read-only, до подтверждения)
    wid = s.get("warehouse", {}).get("id")
    if wid:
        try:
            r = BA.S.get(f"{BA.BASE}/campaigns/{cid}/shipments/reception-transfer-act",
                         params={"warehouseId": wid}, timeout=90)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                with open(os.path.join(folder, "Акт_приёма-передачи.pdf"), "wb") as f:
                    f.write(r.content)
            else:
                print("   акт приёма-передачи: HTTP", r.status_code)
        except Exception as e:
            print("   акт: err", e)

    # свод по товарам
    agg = {}
    for o in orders:
        for it in o.get("items", []):
            a = agg.setdefault(it.get("offerId"), {"count": 0, "orders": 0})
            a["count"] += it.get("count", 0)
            a["orders"] += 1
    build_picklist_html(folder, sid, cname, date, dest, addr, orders, maps, agg)
    render(folder)
    units = sum(v["count"] for v in agg.values())
    print(f"   товаров: {units} шт, {len(agg)} SKU | этикеток: {len(writer.pages)} стр")
    print(f"   -> {folder}")


def img_tag(maps_photo_root, oid, cls="ph"):
    p = os.path.join(BA.IMG, f"{oid}.jpg")
    if os.path.exists(p) and os.path.getsize(p) > 0:
        rel = os.path.relpath(p, maps_photo_root).replace("\\", "/")
        return f'<img class="{cls}" src="{rel}">'
    return f'<div class="{cls} noimg">нет фото</div>'


def build_picklist_html(folder, sid, cname, date, dest, addr, orders, maps, agg):
    agg_sorted = sorted(agg.items(), key=lambda kv: maps.get(kv[0], {}).get("name", kv[0]).lower())
    units = sum(v["count"] for v in agg.values())

    srows = []
    for i, (oid, v) in enumerate(agg_sorted, 1):
        m = maps.get(oid, {})
        srows.append(f"""<tr>
  <td class="num">{i}</td><td>{img_tag(folder, oid)}</td>
  <td class="art">{esc(oid)}<div class="bc">{esc(m.get('barcode'))}</div></td>
  <td class="nm">{esc(m.get('name'))}</td>
  <td class="qty">{v['count']}</td><td class="ord">{v['orders']}</td><td class="chk"></td>
</tr>""")

    orows = []
    for o in orders:
        its = o.get("items", [])
        first = True
        rs = len(its)
        for it in its:
            oid = it.get("offerId")
            m = maps.get(oid, {})
            cell = f'<td class="ordn" rowspan="{rs}"><b>{esc(o["id"])}</b></td>' if first else ""
            orows.append(f"""<tr>
  {cell}<td>{img_tag(folder, oid, 'ph2')}</td>
  <td class="art">{esc(oid)}</td><td class="nm">{esc(m.get('name'))}</td>
  <td class="qty">{it.get('count',0)}</td><td class="chk"></td>
</tr>""")
            first = False

    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
@page {{ size:A4; margin:8mm; }}
* {{ box-sizing:border-box; }}
body {{ font-family:'Segoe UI',Arial,sans-serif; margin:0; color:#111; }}
h1 {{ font-size:20px; margin:0 0 2px; }}
.cabhdr {{ font-size:22px; font-weight:800; margin:2px 0 4px; }}
.sub {{ color:#666; font-size:12px; margin-bottom:6px; }}
.dest {{ background:#fff6d6; border:1px solid #f0d54a; border-radius:8px; padding:6px 10px; font-size:13px; margin-bottom:10px; }}
.badge {{ display:inline-block; background:#ffdd2d; color:#000; font-weight:700; border-radius:6px; padding:2px 8px; margin-right:6px; font-size:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:#f3f3f3; text-align:left; padding:6px; border-bottom:2px solid #ccc; font-size:11px; text-transform:uppercase; }}
td {{ padding:6px; border-bottom:1px solid #e5e5e5; vertical-align:middle; }}
.ph {{ width:96px; height:96px; object-fit:contain; background:#fafafa; border:1px solid #eee; border-radius:8px; }}
.ph2 {{ width:80px; height:80px; object-fit:contain; background:#fafafa; border:1px solid #eee; border-radius:7px; }}
.noimg {{ display:flex; align-items:center; justify-content:center; font-size:10px; color:#aaa; }}
.num,.ord {{ text-align:center; color:#888; width:34px; }}
.art {{ font-weight:700; white-space:nowrap; }}
.bc {{ font-weight:400; color:#999; font-size:9px; }}
.nm {{ font-size:12px; line-height:1.3; }}
.qty {{ text-align:center; font-weight:800; font-size:20px; width:56px; }}
.chk {{ width:34px; }}
.chk::after {{ content:''; display:block; width:22px; height:22px; border:2px solid #bbb; border-radius:4px; margin:auto; }}
.ordn {{ width:130px; font-size:15px; font-weight:700; background:#fcfcfc; }}
h2 {{ font-size:15px; margin:14px 0 8px; }}
tr {{ page-break-inside:avoid; }}
</style></head><body>
<h1>Лист подбора · Отгрузка #{sid}</h1>
<div class="cabhdr">{esc(cname)} · {esc(date)}</div>
<div class="dest"><b>Сдать в:</b> {esc(dest)} · {esc(addr)}</div>
<div class="sub"><span class="badge">{len(orders)} заказов</span><span class="badge">{units} шт</span><span class="badge">{len(agg_sorted)} SKU</span></div>
<h2>Свод по товарам — набрать со склада</h2>
<table><thead><tr><th>#</th><th>Фото</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>Зак.</th><th>✓</th></tr></thead>
<tbody>{''.join(srows)}</tbody></table>
<h2>Поштучно по заказам — сверка с этикетками</h2>
<table><thead><tr><th>№ заказа</th><th>Фото</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>✓</th></tr></thead>
<tbody>{''.join(orows)}</tbody></table>
</body></html>"""
    with open(os.path.join(folder, "picklist.html"), "w", encoding="utf-8") as f:
        f.write(doc)


def render(folder):
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    src = os.path.join(folder, "picklist.html")
    dst = os.path.join(folder, "Лист_подбора.pdf")
    if os.path.exists(dst):
        os.remove(dst)
    subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={dst}", "file:///" + src.replace("\\", "/")], timeout=180)


def confirm_shipment(sid, places):
    """Указать число мест (упаковок), подтвердить отгрузку, скачать ярлык на коробку + акт.
    НЕОБРАТИМО: после подтверждения состав отгрузки менять нельзя."""
    ships = all_shipments()
    t = [(c, n, s) for c, n, s in ships if str(s["id"]) == str(sid)]
    if not t:
        print("Отгрузка не найдена:", sid)
        return
    cid, cname, s = t[0]
    date = s.get("planIntervalFrom", "")[:10]
    acts = s.get("availableActions") or []
    print(f"Отгрузка #{sid} · {cname} · {date} · {len(s.get('orderIds',[]))} заказов")
    print("availableActions:", acts)
    if "CONFIRM" not in acts:
        print("⚠ CONFIRM сейчас недоступен (возможно уже подтверждена или не наступил cutoff).")

    # 1) число упаковок
    r = req("PUT", f"{BA.BASE}/campaigns/{cid}/first-mile/shipments/{sid}/pallets",
            json={"placesCount": int(places)})
    print(f"1) мест={places}: HTTP {r.status_code} {('' if r.ok else r.text[:200])}")

    # 2) подтверждение
    r = req("POST", f"{BA.BASE}/campaigns/{cid}/first-mile/shipments/{sid}/confirm", json={})
    print(f"2) подтверждение: HTTP {r.status_code} {('OK' if r.ok else r.text[:250])}")
    if not r.ok:
        return

    # 3) ярлык на коробку + акт → в папку отгрузки
    safe_cab = cname.replace(" ", "")
    folder = os.path.join(BA.OUT, f"Отгрузка_{sid}_{safe_cab}_{date}")
    os.makedirs(folder, exist_ok=True)
    r = req("GET", f"{BA.BASE}/campaigns/{cid}/first-mile/shipments/{sid}/transportation-waybill")
    if r.status_code == 200 and r.content[:4] == b"%PDF":
        with open(os.path.join(folder, "Ярлык_на_коробку.pdf"), "wb") as f:
            f.write(r.content)
        print("3) ярлык на коробку: OK ->", folder)
    else:
        print("3) ярлык на коробку: HTTP", r.status_code, r.text[:150])
    wid = s.get("warehouse", {}).get("id")
    if wid:
        r = req("GET", f"{BA.BASE}/campaigns/{cid}/shipments/reception-transfer-act",
                params={"warehouseId": wid})
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            with open(os.path.join(folder, "Акт_приёма-передачи.pdf"), "wb") as f:
                f.write(r.content)
            print("4) акт приёма-передачи: обновлён")
    print("ГОТОВО.")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "active"
    if arg == "confirm":
        if len(sys.argv) < 4:
            print("Использование: python build_shipment.py confirm <shipmentId> <число_коробок>")
            return
        confirm_shipment(sys.argv[2], sys.argv[3])
        return
    ships = all_shipments()
    if arg == "active":
        targets = [(c, n, s) for c, n, s in ships if s.get("status") == "OUTBOUND_READY_FOR_CONFIRMATION"]
        print(f"Активных отгрузок («Можно обрабатывать»): {len(targets)}")
    elif arg == "all":
        targets = [(c, n, s) for c, n, s in ships if s.get("status") != "FINISHED"]
        print(f"Незавершённых отгрузок (все, кроме уехавших): {len(targets)}")
    else:
        targets = [(c, n, s) for c, n, s in ships if str(s["id"]) == arg]
        if not targets:
            print("Отгрузка не найдена:", arg)
            return
    for c, n, s in targets:
        build_one(c, n, s)
    print("\nГОТОВО.")


if __name__ == "__main__":
    main()
