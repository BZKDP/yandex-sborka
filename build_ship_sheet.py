#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Лист сборки по отгрузке Яндекс.Маркет: свод по ячейкам + по заказам с этикеткой."""
import os, sys, io, re, json, html, subprocess
sys.stdout.reconfigure(encoding="utf-8")
import fitz  # PyMuPDF

ROOT = os.path.dirname(os.path.abspath(__file__))
LBL_PNG = os.path.join(ROOT, "labels_png")
OUT = os.path.join(ROOT, "out")
DOWN = os.environ.get("YM_OUTPUT_DIR", os.path.join(os.path.expanduser("~"), "Downloads"))
os.makedirs(LBL_PNG, exist_ok=True); os.makedirs(OUT, exist_ok=True)

SHIP_PDF = {
    89468451: os.path.join(DOWN, "89468451_shipment_orders_labels.pdf"),
    89380455: os.path.join(DOWN, "89380455_shipment_orders_labels.pdf"),
    89366949: os.path.join(DOWN, "89366949_shipment_orders_labels.pdf"),
}

data = json.load(io.open(os.path.join(ROOT, "ship", "shipdata.json"), encoding="utf-8"))
cells = json.load(io.open(os.path.join(ROOT, "ship", "cells.json"), encoding="utf-8"))
maps = data["maps"]; photo_rel = data["photo_rel"]


def esc(s): return html.escape(str(s or ""))


def render_labels():
    """Каждую страницу ярлыка → labels_png/{order}.png, вернуть {order_str: (png_rel, meta)}."""
    order_png = {}
    for ship, pdf in SHIP_PDF.items():
        if not os.path.exists(pdf):
            print("  ! нет PDF", pdf); continue
        doc = fitz.open(pdf)
        for i, page in enumerate(doc):
            txt = page.get_text() or ""
            m = re.search(r"номер заказа\s+(\d+)", txt)
            oid = m.group(1) if m else f"{ship}_p{i}"
            p = os.path.join(LBL_PNG, f"{oid}.png")
            if not (os.path.exists(p) and os.path.getsize(p) > 0):
                pix = page.get_pixmap(matrix=fitz.Matrix(2.6, 2.6))
                pix.save(p)
            order_png[oid] = f"labels_png/{oid}.png"
        doc.close()
    print(f"  ярлыков отрендерено: {len(order_png)}")
    return order_png


CELL_RE = re.compile(r"С(\d+)П(\d+)К(\d+)")
def cell_key(name):
    m = CELL_RE.search(name or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (999, 999, 999)


def item_cell_info(offerId):
    c = cells.get(offerId) or {}
    if not c.get("found"):
        return {"primary": "", "all": [], "sklad_name": "", "barcode": "", "warn": "нет в складе"}
    cs = c.get("cells") or []
    primary = cs[0]["cell"] if cs else ""
    scan_bc = (c.get("barcode_list") or "").split(";")[0] if c.get("barcode_list") else ""
    return {"primary": primary, "all": cs, "sklad_name": c.get("sklad_name") or "",
            "sklad_article": c.get("sklad_article") or offerId, "barcode": scan_bc,
            "warn": "" if cs else "нет ячейки"}


def img_tag(offerId, cls="ph"):
    p = photo_rel.get(offerId)
    if p and os.path.exists(os.path.join(ROOT, p)):
        return f'<img class="{cls}" src="{p}">'
    return f'<div class="{cls} noimg">нет фото</div>'


def build_sheet(ship, sd, order_png):
    orders_all = sd["orders"]
    # к сборке = есть ярлык (не отменённые). Остальные — отдельно.
    to_pick, cancelled = [], []
    for o in orders_all:
        oid = str(o["id"])
        if o["status"] == "CANCELLED":
            cancelled.append(o)
        else:
            to_pick.append(o)
    to_pick.sort(key=lambda o: o["id"])

    # свод по товарам
    agg = {}
    for o in to_pick:
        for it in o["items"]:
            a = agg.setdefault(it["offerId"], {"count": 0, "orders": 0})
            a["count"] += it["count"]; a["orders"] += 1
    agg_rows = []
    for offerId, v in agg.items():
        ci = item_cell_info(offerId)
        agg_rows.append((offerId, v, ci))
    agg_rows.sort(key=lambda r: (cell_key(r[2]["primary"]), r[2]["sklad_name"]))
    units = sum(v["count"] for _, v, _ in agg_rows)

    srows = []
    for i, (offerId, v, ci) in enumerate(agg_rows, 1):
        cell_html = f'<span class="cellbig">{esc(ci["primary"] or "—")}</span>'
        if len(ci["all"]) > 1:
            others = ", ".join(f'{esc(c["cell"])}·{int(c["qty"])}' for c in ci["all"][1:])
            cell_html += f'<div class="cellalt">ещё: {others}</div>'
        warn = f'<div class="warn">⚠ {esc(ci["warn"])}</div>' if ci["warn"] else ""
        srows.append(f"""<tr>
  <td class="num">{i}</td>
  <td>{img_tag(offerId)}</td>
  <td class="cell">{cell_html}{warn}</td>
  <td class="art">{esc(ci.get('sklad_article', offerId))}<div class="bc">{esc(ci['barcode'])}</div></td>
  <td class="nm">{esc(ci['sklad_name'] or maps.get(offerId,{}).get('name'))}</td>
  <td class="qty">{v['count']}</td>
  <td class="ord">{v['orders']}</td>
  <td class="chk"></td>
</tr>""")

    # по заказам
    orows = []
    for o in to_pick:
        oid = str(o["id"])
        its = o["items"]; rs = len(its)
        png = order_png.get(oid)
        lbl = f'<img class="lbl" src="{png}">' if png else '<div class="lbl noimg">нет ярлыка</div>'
        dst = o.get("delivery", {}) or {}
        target = esc(dst.get("outletName") or dst.get("address") or dst.get("serviceName") or "")
        first = True
        for it in its:
            offerId = it["offerId"]; ci = item_cell_info(offerId)
            ordcell = (f'<td class="ordn" rowspan="{rs}"><div class="onum">{esc(oid)}</div>{lbl}'
                       f'<div class="otarget">{target}</div></td>') if first else ""
            warn = f' <span class="warn">⚠{esc(ci["warn"])}</span>' if ci["warn"] else ""
            orows.append(f"""<tr>
  {ordcell}
  <td>{img_tag(offerId, 'ph2')}</td>
  <td class="cell"><span class="cellbig">{esc(ci['primary'] or '—')}</span>{warn}</td>
  <td class="art">{esc(ci.get('sklad_article', offerId))}</td>
  <td class="nm">{esc(ci['sklad_name'] or maps.get(offerId,{}).get('name'))}</td>
  <td class="qty">{it['count']}</td>
  <td class="chk"></td>
</tr>""")
            first = False

    canc_html = ""
    if cancelled:
        items = "".join(f'<li>{esc(o["id"])} — {esc(o["substatus"])}</li>' for o in cancelled)
        canc_html = f'<div class="canc"><b>Отменены (НЕ собирать), {len(cancelled)}:</b><ul>{items}</ul></div>'

    plan = ""
    if sd.get("planFrom"):
        plan = esc(sd["planFrom"][:10])

    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 8mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family:'Segoe UI',Arial,sans-serif; margin:0; color:#111; }}
h1 {{ font-size:19px; margin:0 0 2px; }}
.sub {{ color:#555; font-size:12px; margin-bottom:8px; }}
.badge {{ display:inline-block; background:#ffdd2d; color:#000; font-weight:700; border-radius:6px; padding:2px 8px; margin-right:6px; font-size:12px; }}
h2 {{ font-size:15px; margin:14px 0 8px; padding:4px 8px; background:#111; color:#fff; border-radius:5px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:#f3f3f3; text-align:left; padding:5px; border-bottom:2px solid #ccc; font-size:10px; text-transform:uppercase; letter-spacing:.3px; }}
td {{ padding:5px; border-bottom:1px solid #e5e5e5; vertical-align:middle; }}
tr {{ page-break-inside:avoid; }}
.ph {{ width:74px; height:74px; object-fit:contain; background:#fafafa; border:1px solid #eee; border-radius:7px; }}
.ph2 {{ width:60px; height:60px; object-fit:contain; background:#fafafa; border:1px solid #eee; border-radius:6px; }}
.noimg {{ display:flex; align-items:center; justify-content:center; font-size:9px; color:#aaa; }}
.num,.ord {{ text-align:center; color:#888; width:30px; }}
.cell {{ width:92px; }}
.cellbig {{ display:inline-block; font-weight:800; font-size:17px; background:#e8f0ff; border:1px solid #b9d0ff; border-radius:5px; padding:1px 6px; white-space:nowrap; }}
.cellalt {{ color:#888; font-size:9px; margin-top:2px; }}
.warn {{ color:#c00; font-weight:700; font-size:10px; }}
.art {{ font-weight:700; white-space:nowrap; font-size:12px; }}
.bc {{ font-weight:400; color:#999; font-size:9px; }}
.nm {{ font-size:11.5px; line-height:1.25; }}
.qty {{ text-align:center; font-weight:800; font-size:20px; width:50px; }}
.chk {{ width:30px; }}
.chk::after {{ content:''; display:block; width:20px; height:20px; border:2px solid #bbb; border-radius:4px; margin:auto; }}
.ordn {{ width:150px; background:#fcfcfc; text-align:center; }}
.onum {{ font-size:14px; font-weight:800; margin-bottom:3px; }}
.lbl {{ width:130px; border:1px solid #ddd; border-radius:4px; }}
.otarget {{ font-size:9px; color:#666; margin-top:3px; line-height:1.2; }}
.canc {{ margin-top:14px; font-size:11px; color:#a00; }}
.canc ul {{ margin:4px 0; }}
.pagebreak {{ page-break-before: always; }}
</style></head><body>
<h1>Лист сборки · Яндекс.Маркет · Отгрузка №{ship}</h1>
<div class="sub">
  <span class="badge">{len(to_pick)} заказов</span>
  <span class="badge">{units} шт</span>
  <span class="badge">{len(agg_rows)} SKU</span>
  {esc(data['cname'])} · склад {esc(sd.get('warehouse'))} · отгрузка {plan} · сформировано {esc(data['generated'])}
</div>

<h2>1 · Собрать со склада — по ячейкам</h2>
<table>
<thead><tr><th>#</th><th>Фото</th><th>Ячейка</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>Зак.</th><th>✓</th></tr></thead>
<tbody>{''.join(srows)}</tbody>
</table>

<div class="pagebreak"></div>
<h2>2 · Разложить по заказам + наклеить этикетку</h2>
<table>
<thead><tr><th>Заказ / этикетка</th><th>Фото</th><th>Ячейка</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>✓</th></tr></thead>
<tbody>{''.join(orows)}</tbody>
</table>
{canc_html}
</body></html>"""
    hp = os.path.join(ROOT, f"picklist_{ship}.html")
    io.open(hp, "w", encoding="utf-8").write(doc)
    return hp, len(to_pick), units, len(agg_rows), len(cancelled)


def render_pdf(src, dst):
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if os.path.exists(dst):
        os.remove(dst)
    subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={dst}", "file:///" + src.replace("\\", "/")], timeout=180)
    return os.path.exists(dst)


def main():
    print("Рендер ярлыков…")
    order_png = render_labels()
    for ship, sd in data["shipments"].items():
        ship = int(ship)
        hp, no, un, sku, canc = build_sheet(ship, sd, order_png)
        dst = os.path.join(DOWN, f"Лист сборки ЯМ {ship}.pdf")
        ok = render_pdf(hp, dst)
        print(f"  Отгрузка {ship}: {no} заказов, {un} шт, {sku} SKU, отменено {canc} → {'OK' if ok else 'FAIL'}  {dst}")


if __name__ == "__main__":
    main()
