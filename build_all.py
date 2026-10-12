#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Яндекс.Маркет FBS: сборка листа подбора с фото + склейка этикеток.
Заказы в статусе PROCESSING/STARTED (ожидают сборки) по всем FBS-кабинетам.
"""
import os, sys, io, json, time, html, base64, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from pypdf import PdfReader, PdfWriter

TOKEN = os.environ.get("YM_API_KEY", "")
BUSINESS_ID = int(os.environ.get("YM_BUSINESS_ID", "0"))
# FBS-кабинеты, где есть заказы «ожидают сборки»
CAMPAIGNS = {
    107803271: "Яндекс маркет ИП",
    148851177: "GraFLab 2",
    148949326: "Склад Ижевск",
}
BASE = "https://api.partner.market.yandex.ru"
H = {"Api-Key": TOKEN, "Content-Type": "application/json"}
ROOT = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(ROOT, "images")
LBL = os.path.join(ROOT, "labels")
OUT = os.path.join(ROOT, "out")
for d in (IMG, LBL, OUT):
    os.makedirs(d, exist_ok=True)

S = requests.Session()
S.headers.update(H)


def fix_moji(s):
    """Восстановить кириллицу, испорченную двойной перекодировкой UTF-8->CP1251."""
    if not s:
        return s
    try:
        r = s.encode("cp1251").decode("utf-8")
        # эвристика: если стало меньше «Р/С»-мусора — берём восстановленное
        return r
    except Exception:
        return s


def get_orders(cid):
    orders = []
    page = 1
    while True:
        r = S.get(f"{BASE}/campaigns/{cid}/orders",
                  params={"status": "PROCESSING", "substatus": "STARTED",
                          "pageSize": 50, "page": page}, timeout=60)
        r.raise_for_status()
        d = r.json()
        orders.extend(d.get("orders", []))
        pg = d.get("pager", {})
        if page >= pg.get("pagesCount", 1) or not d.get("orders"):
            break
        page += 1
    return orders


def get_mappings(offer_ids):
    res = {}
    ids = list(offer_ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        r = S.post(f"{BASE}/businesses/{BUSINESS_ID}/offer-mappings",
                   params={"limit": 200}, json={"offerIds": chunk}, timeout=60)
        r.raise_for_status()
        for m in r.json().get("result", {}).get("offerMappings", []):
            off = m.get("offer", {})
            oid = off.get("offerId")
            pics = off.get("pictures") or []
            res[oid] = {
                "name": fix_moji(off.get("name", "")),
                "picture": pics[0] if pics else "",
                "barcode": (off.get("barcodes") or [""])[0],
            }
    return res


def download(url, path):
    try:
        r = S.get(url, timeout=60)
        if r.status_code == 200 and r.content:
            with open(path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print("  ! dl fail", url[:60], e)
    return False


def get_label(cid, oid, path):
    for attempt in range(6):
        try:
            r = S.get(f"{BASE}/campaigns/{cid}/orders/{oid}/delivery/labels",
                      params={"format": "A9"}, timeout=90)  # A9 = 40x58 мм, термо
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                with open(path, "wb") as f:
                    f.write(r.content)
                return True
            if r.status_code in (420, 429, 500, 503):
                time.sleep(2 + attempt * 2)  # backoff при rate-limit
                continue
            print("  ! label", oid, r.status_code)
            return False
        except Exception as e:
            print("  ! label fail", oid, e)
            time.sleep(2)
    print("  ! label give up", oid)
    return False


def main():
    print("1) Загружаю заказы…")
    all_orders = []
    for cid, cname in CAMPAIGNS.items():
        o = get_orders(cid)
        for x in o:
            x["_cid"] = cid
            x["_cname"] = cname
        all_orders.extend(o)
        print(f"   {cname}: {len(o)}")
    all_orders.sort(key=lambda x: x["id"])
    print(f"   ВСЕГО заказов: {len(all_orders)}")

    # уникальные артикулы
    offer_ids = set()
    for o in all_orders:
        for it in o.get("items", []):
            offer_ids.add(it.get("offerId"))
    offer_ids.discard(None)
    print(f"2) Карточки товаров: {len(offer_ids)} уникальных артикулов")
    maps = get_mappings(offer_ids)

    print("3) Качаю фото товаров…")
    photo_path = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {}
        for oid in offer_ids:
            url = maps.get(oid, {}).get("picture")
            if not url:
                continue
            if url.endswith("/orig"):
                url = url[:-5] + "/300x300"  # компактные фото вместо оригинала
            p = os.path.join(IMG, f"{oid}.jpg")
            photo_path[oid] = p
            if os.path.exists(p) and os.path.getsize(p) > 0:
                continue
            futs[ex.submit(download, url, p)] = oid
        for f in as_completed(futs):
            f.result()

    print("4) Качаю этикетки (по 1 на заказ)…")
    ok_labels = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {}
        for o in all_orders:
            p = os.path.join(LBL, f"{o['id']}.pdf")
            if os.path.exists(p) and os.path.getsize(p) > 0:
                ok_labels.append((o["id"], p))
                continue
            futs[ex.submit(get_label, o["_cid"], o["id"], p)] = (o["id"], p)
        for f in as_completed(futs):
            oid, p = futs[f]
            if f.result():
                ok_labels.append((oid, p))
    # склейка в порядке возрастания № заказа
    ok_map = dict(ok_labels)
    writer = PdfWriter()
    merged = 0
    for o in all_orders:
        p = ok_map.get(o["id"])
        if p and os.path.exists(p):
            for pg in PdfReader(p).pages:
                writer.add_page(pg)
            merged += 1
    labels_pdf = os.path.join(OUT, "Этикетки_ЯндексМаркет_141.pdf")
    with open(labels_pdf, "wb") as f:
        writer.write(f)
    print(f"   Склеено этикеток: {merged} -> {labels_pdf}")

    # данные для листа подбора
    # свод по артикулу
    agg = {}
    for o in all_orders:
        for it in o.get("items", []):
            oid = it.get("offerId")
            cnt = it.get("count", 0)
            a = agg.setdefault(oid, {"count": 0, "orders": 0})
            a["count"] += cnt
            a["orders"] += 1
    # поштучно по заказам
    rows = []
    for o in all_orders:
        items = o.get("items", [])
        rows.append({
            "order": o["id"],
            "cabinet": o["_cname"],
            "items": [{
                "oid": it.get("offerId"),
                "count": it.get("count", 0),
            } for it in items],
        })

    data = {
        "generated": time.strftime("%d.%m.%Y %H:%M"),
        "total_orders": len(all_orders),
        "maps": maps,
        "photo_rel": {oid: f"images/{oid}.jpg" for oid in photo_path},
        "agg": agg,
        "rows": rows,
    }
    with open(os.path.join(ROOT, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("5) data.json готов. Строю HTML…")
    build_html(data)
    print("6) Рендерю PDF через Edge…")
    render_pdf()
    print("ГОТОВО.")
    print("  Этикетки :", labels_pdf)
    print("  Лист     :", os.path.join(OUT, "Лист_подбора.pdf"))


def esc(s):
    return html.escape(str(s or ""))


def build_html(data):
    maps = data["maps"]
    photo = data["photo_rel"]

    def img_tag(oid, cls="ph"):
        p = photo.get(oid)
        if p and os.path.exists(os.path.join(ROOT, p)):
            return f'<img class="{cls}" src="{p}">'
        return f'<div class="{cls} noimg">нет фото</div>'

    # группировка по кабинетам, порядок — по числу заказов (убыв.)
    cabs = {}
    for r in data["rows"]:
        cabs.setdefault(r["cabinet"], []).append(r)
    cab_items = sorted(cabs.items(), key=lambda kv: -len(kv[1]))

    sections = []
    for ci, (cab, rws) in enumerate(cab_items):
        # свод по товарам этого кабинета
        agg = {}
        for r in rws:
            for it in r["items"]:
                a = agg.setdefault(it["oid"], {"count": 0, "orders": 0})
                a["count"] += it["count"]
                a["orders"] += 1
        agg_sorted = sorted(agg.items(), key=lambda kv: maps.get(kv[0], {}).get("name", kv[0]).lower())
        units = sum(v["count"] for v in agg.values())

        srows = []
        for i, (oid, v) in enumerate(agg_sorted, 1):
            m = maps.get(oid, {})
            srows.append(f"""<tr>
  <td class="num">{i}</td>
  <td>{img_tag(oid)}</td>
  <td class="art">{esc(oid)}<div class="bc">{esc(m.get('barcode'))}</div></td>
  <td class="nm">{esc(m.get('name'))}</td>
  <td class="qty">{v['count']}</td>
  <td class="ord">{v['orders']}</td>
  <td class="chk"></td>
</tr>""")

        orows = []
        for r in rws:
            its = r["items"]
            first = True
            rs = len(its)
            for it in its:
                oid = it["oid"]
                m = maps.get(oid, {})
                cell = f'<td class="ordn" rowspan="{rs}"><b>{esc(r["order"])}</b></td>' if first else ""
                orows.append(f"""<tr>
  {cell}
  <td>{img_tag(oid, 'ph2')}</td>
  <td class="art">{esc(oid)}</td>
  <td class="nm">{esc(m.get('name'))}</td>
  <td class="qty">{it['count']}</td>
  <td class="chk"></td>
</tr>""")
                first = False

        sec_cls = "cabsec" if ci > 0 else ""
        sections.append(f"""
<div class="page {sec_cls}">
  <div class="cabhdr">Кабинет: {esc(cab)}</div>
  <div class="sub">
    <span class="badge">{len(rws)} заказов</span>
    <span class="badge">{units} шт</span>
    <span class="badge">{len(agg_sorted)} SKU</span>
  </div>

  <h2>Свод по товарам — набрать со склада</h2>
  <table>
    <thead><tr><th>#</th><th>Фото</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>Зак.</th><th>✓</th></tr></thead>
    <tbody>
    {''.join(srows)}
    </tbody>
  </table>

  <h2 class="sp">Поштучно по заказам — сверка с этикетками (по № заказа)</h2>
  <table>
    <thead><tr><th>№ заказа</th><th>Фото</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>✓</th></tr></thead>
    <tbody>
    {''.join(orows)}
    </tbody>
  </table>
</div>""")

    total_sku = len({it["oid"] for r in data["rows"] for it in r["items"]})
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 8mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; color:#111; }}
.page {{ padding: 0; }}
h1 {{ font-size: 20px; margin: 0 0 2px; }}
.top {{ padding: 0 0 4px; }}
.cabhdr {{ font-size: 22px; font-weight: 800; margin: 4px 0 6px; }}
.sub {{ color:#666; font-size:12px; margin-bottom:10px; }}
.badge {{ display:inline-block; background:#ffdd2d; color:#000; font-weight:700;
         border-radius:6px; padding:2px 8px; margin-right:6px; font-size:12px; }}
table {{ width:100%; border-collapse: collapse; font-size:13px; }}
th {{ background:#f3f3f3; text-align:left; padding:6px; border-bottom:2px solid #ccc; font-size:11px; text-transform:uppercase; letter-spacing:.3px; }}
td {{ padding:6px; border-bottom:1px solid #e5e5e5; vertical-align:middle; }}
.ph {{ width:96px; height:96px; object-fit:contain; background:#fafafa; border:1px solid #eee; border-radius:8px; }}
.ph2 {{ width:80px; height:80px; object-fit:contain; background:#fafafa; border:1px solid #eee; border-radius:7px; }}
.noimg {{ display:flex; align-items:center; justify-content:center; font-size:10px; color:#aaa; }}
.num,.ord {{ text-align:center; color:#888; width:34px; }}
.art {{ font-weight:700; white-space:nowrap; font-size:13px; }}
.bc {{ font-weight:400; color:#999; font-size:9px; }}
.nm {{ font-size:12px; line-height:1.3; }}
.qty {{ text-align:center; font-weight:800; font-size:20px; width:56px; }}
.chk {{ width:34px; }}
.chk::after {{ content:''; display:block; width:22px; height:22px; border:2px solid #bbb; border-radius:4px; margin:auto; }}
.ordn {{ width:130px; font-size:15px; font-weight:700; background:#fcfcfc; }}
.cabsec {{ page-break-before: always; }}
h2 {{ font-size:15px; margin:0 0 8px; padding-top:4px; }}
h2.sp {{ margin-top:16px; }}
tr {{ page-break-inside: avoid; }}
</style></head><body>

<div class="top">
  <h1>Лист подбора · Яндекс.Маркет FBS</h1>
  <div class="sub">
    <span class="badge">{data['total_orders']} заказов</span>
    <span class="badge">{total_sku} SKU</span>
    по {len(cab_items)} кабинетам · сформировано {esc(data['generated'])}
  </div>
</div>
{''.join(sections)}
</body></html>"""
    with open(os.path.join(ROOT, "picklist.html"), "w", encoding="utf-8") as f:
        f.write(doc)


def render_pdf():
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    src = os.path.join(ROOT, "picklist.html")
    dst = os.path.join(OUT, "Лист_подбора.pdf")
    if os.path.exists(dst):
        os.remove(dst)
    subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={dst}", "file:///" + src.replace("\\", "/")],
                   timeout=180)
    print("   PDF:", "OK" if os.path.exists(dst) else "FAIL")


if __name__ == "__main__":
    main()
