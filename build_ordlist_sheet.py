#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Лист подбора по списку заказов Яндекс.Маркет: свод по ячейкам + по заказам."""
import os, sys, io, re, json, html, subprocess
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "ordlist")
data = json.load(io.open(os.path.join(OUT, "orddata.json"), encoding="utf-8"))
cells = json.load(io.open(os.path.join(OUT, "cells.json"), encoding="utf-8"))
maps = data["maps"]; photo_rel = data["photo_rel"]; orders = data["orders"]


def esc(s): return html.escape(str(s or ""))
CELL_RE = re.compile(r"С(\d+)П(\d+)К(\d+)")
def cell_key(n):
    m = CELL_RE.search(n or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (999, 999, 999)


def ci(offerId):
    c = cells.get(offerId) or {}
    if not c.get("found"):
        return {"primary": "", "all": [], "name": maps.get(offerId, {}).get("name", ""), "art": offerId, "bc": "", "warn": "нет в складе"}
    cs = c.get("cells") or []
    bc = (c.get("barcode_list") or "").split(";")[0] if c.get("barcode_list") else ""
    return {"primary": cs[0]["cell"] if cs else "", "all": cs, "name": c.get("sklad_name") or maps.get(offerId, {}).get("name", ""),
            "art": c.get("sklad_article") or offerId, "bc": bc, "warn": "" if cs else "нет ячейки"}


def img(offerId, cls="ph"):
    p = photo_rel.get(offerId)
    if p and os.path.exists(os.path.join(ROOT, p)):
        absu = "file:///" + os.path.join(ROOT, p).replace("\\", "/")
        return f'<img class="{cls}" src="{absu}">'
    return f'<div class="{cls} noimg">нет фото</div>'


# свод
agg = {}
for o in orders:
    for it in o["items"]:
        a = agg.setdefault(it["offerId"], {"count": 0, "orders": 0})
        a["count"] += it["count"]; a["orders"] += 1
rows = sorted(agg.items(), key=lambda kv: (cell_key(ci(kv[0])["primary"]), ci(kv[0])["name"]))
units = sum(v["count"] for _, v in rows)
srows = []
for i, (offerId, v) in enumerate(rows, 1):
    c = ci(offerId)
    cell = f'<span class="cellbig">{esc(c["primary"] or "—")}</span>'
    if len(c["all"]) > 1:
        cell += '<div class="cellalt">ещё: ' + ", ".join(f'{esc(x["cell"])}·{int(x["qty"])}' for x in c["all"][1:]) + '</div>'
    warn = f'<div class="warn">⚠ {esc(c["warn"])}</div>' if c["warn"] else ""
    srows.append(f'<tr><td class="num">{i}</td><td>{img(offerId)}</td><td class="cell">{cell}{warn}</td>'
                 f'<td class="art">{esc(c["art"])}<div class="bc">{esc(c["bc"])}</div></td><td class="nm">{esc(c["name"])}</td>'
                 f'<td class="qty">{v["count"]}</td><td class="ord">{v["orders"]}</td><td class="chk"></td></tr>')

# по заказам
orows = []
for o in sorted(orders, key=lambda x: x["id"]):
    its = o["items"]; rs = len(its); first = True
    target = esc(o.get("outlet") or o.get("city") or "")
    nolbl = "" if o.get("has_label") else '<div class="warn">нет ярлыка</div>'
    for it in its:
        c = ci(it["offerId"])
        cellcol = (f'<td class="ordn" rowspan="{rs}"><div class="onum">{esc(o["id"])}</div>'
                   f'<div class="otarget">{target}</div>{nolbl}</td>') if first else ""
        warn = f' <span class="warn">⚠{esc(c["warn"])}</span>' if c["warn"] else ""
        orows.append(f'<tr>{cellcol}<td>{img(it["offerId"], "ph2")}</td>'
                     f'<td class="cell"><span class="cellbig">{esc(c["primary"] or "—")}</span>{warn}</td>'
                     f'<td class="art">{esc(c["art"])}</td><td class="nm">{esc(c["name"])}</td>'
                     f'<td class="qty">{it["count"]}</td><td class="chk"></td></tr>')
        first = False

doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 8mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family:'Segoe UI',Arial,sans-serif; margin:0; color:#111; }}
h1 {{ font-size:19px; margin:0 0 2px; }}
.sub {{ color:#555; font-size:12px; margin-bottom:8px; }}
.badge {{ display:inline-block; background:#ffdd2d; color:#000; font-weight:700; border-radius:6px; padding:2px 8px; margin-right:6px; font-size:12px; }}
h2 {{ font-size:15px; margin:14px 0 8px; padding:4px 8px; background:#111; color:#fff; border-radius:5px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:#f3f3f3; text-align:left; padding:5px; border-bottom:2px solid #ccc; font-size:10px; text-transform:uppercase; }}
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
.onum {{ font-size:15px; font-weight:800; }}
.otarget {{ font-size:10px; color:#666; margin-top:3px; }}
.pagebreak {{ page-break-before: always; }}
</style></head><body>
<h1>Лист подбора · Яндекс.Маркет · 37 заказов</h1>
<div class="sub"><span class="badge">{len(orders)} заказов</span><span class="badge">{units} шт</span><span class="badge">{len(rows)} SKU</span>
{esc(data['cname'])} · сформировано {esc(data['generated'])} · этикетки отдельным файлом «Этикетки ЯМ 37 заказов.pdf»</div>

<h2>1 · Собрать со склада — по ячейкам</h2>
<table><thead><tr><th>#</th><th>Фото</th><th>Ячейка</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>Зак.</th><th>✓</th></tr></thead>
<tbody>{''.join(srows)}</tbody></table>

<div class="pagebreak"></div>
<h2>2 · Разложить по заказам (этикетки — отдельный файл, по № заказа)</h2>
<table><thead><tr><th>№ заказа</th><th>Фото</th><th>Ячейка</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>✓</th></tr></thead>
<tbody>{''.join(orows)}</tbody></table>
</body></html>"""
hp = os.path.join(OUT, "picklist.html")
io.open(hp, "w", encoding="utf-8").write(doc)

edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
down = os.environ.get("YM_OUTPUT_DIR", os.path.join(os.path.expanduser("~"), "Downloads"))
dst = os.path.join(down, "Лист подбора ЯМ 37 заказов.pdf")
if os.path.exists(dst):
    os.remove(dst)
subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={dst}",
                "file:///" + hp.replace("\\", "/")], timeout=180)
print("ГОТОВО:", dst, "OK" if os.path.exists(dst) else "FAIL", "|", len(orders), "заказов,", units, "шт,", len(rows), "SKU")
