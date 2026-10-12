#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Лист СБОРКИ заказов Яндекс.Маркет (по заказам, с этикеткой каждого)."""
import os, sys, io, re, json, html, subprocess
sys.stdout.reconfigure(encoding="utf-8")
import fitz
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "ordlist")
LBL = os.path.join(OUT, "labels")
LPNG = os.path.join(OUT, "labels_png"); os.makedirs(LPNG, exist_ok=True)
data = json.load(io.open(os.path.join(OUT, "orddata.json"), encoding="utf-8"))
cells = json.load(io.open(os.path.join(OUT, "cells.json"), encoding="utf-8"))
maps = data["maps"]; photo_rel = data["photo_rel"]; orders = data["orders"]


def esc(s): return html.escape(str(s or ""))
def ci(offerId):
    c = cells.get(offerId) or {}
    if not c.get("found"):
        return {"primary": "", "name": maps.get(offerId, {}).get("name", ""), "art": offerId, "warn": "нет в складе"}
    cs = c.get("cells") or []
    return {"primary": cs[0]["cell"] if cs else "", "name": c.get("sklad_name") or maps.get(offerId, {}).get("name", ""),
            "art": c.get("sklad_article") or offerId, "warn": "" if cs else "нет ячейки"}


def img(offerId, cls="ph2"):
    p = photo_rel.get(offerId)
    if p and os.path.exists(os.path.join(ROOT, p)):
        return f'<img class="{cls}" src="file:///{os.path.join(ROOT, p).replace(chr(92), "/")}">'
    return f'<div class="{cls} noimg">нет фото</div>'


def label_png(oid):
    src = os.path.join(LBL, f"{oid}.pdf")
    if not os.path.exists(src):
        return None
    p = os.path.join(LPNG, f"{oid}.png")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        d = fitz.open(src)
        d[0].get_pixmap(matrix=fitz.Matrix(2.6, 2.6)).save(p)
        d.close()
    return f'file:///{p.replace(chr(92), "/")}'


orows = []
for o in sorted(orders, key=lambda x: x["id"]):
    its = o["items"]; rs = len(its); first = True
    png = label_png(o["id"])
    lbl = f'<img class="lbl" src="{png}">' if png else '<div class="lbl noimg">нет ярлыка</div>'
    target = esc(o.get("outlet") or o.get("city") or "")
    for it in its:
        c = ci(it["offerId"])
        ordcell = (f'<td class="ordn" rowspan="{rs}"><div class="onum">{esc(o["id"])}</div>{lbl}'
                   f'<div class="otarget">{target}</div></td>') if first else ""
        warn = f' <span class="warn">⚠{esc(c["warn"])}</span>' if c["warn"] else ""
        orows.append(f'<tr>{ordcell}<td class="cell"><span class="cellbig">{esc(c["primary"] or "—")}</span>{warn}</td>'
                     f'<td>{img(it["offerId"])}</td><td class="art">{esc(c["art"])}</td>'
                     f'<td class="nm">{esc(c["name"])}</td><td class="qty">{it["count"]}</td><td class="chk"></td></tr>')
        first = False
units = sum(it["count"] for o in orders for it in o["items"])

doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 8mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family:'Segoe UI',Arial,sans-serif; margin:0; color:#111; }}
h1 {{ font-size:19px; margin:0 0 2px; }}
.sub {{ color:#555; font-size:12px; margin-bottom:10px; }}
.badge {{ display:inline-block; background:#ffdd2d; color:#000; font-weight:700; border-radius:6px; padding:2px 8px; margin-right:6px; font-size:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:#f3f3f3; text-align:left; padding:5px; border-bottom:2px solid #ccc; font-size:10px; text-transform:uppercase; }}
td {{ padding:5px; border-bottom:1px solid #e5e5e5; vertical-align:middle; }}
tr {{ page-break-inside:avoid; }}
.ph2 {{ width:60px; height:60px; object-fit:contain; background:#fafafa; border:1px solid #eee; border-radius:6px; }}
.noimg {{ display:flex; align-items:center; justify-content:center; font-size:9px; color:#aaa; }}
.cell {{ width:92px; }}
.cellbig {{ display:inline-block; font-weight:800; font-size:17px; background:#e8f0ff; border:1px solid #b9d0ff; border-radius:5px; padding:1px 6px; white-space:nowrap; }}
.warn {{ color:#c00; font-weight:700; font-size:10px; }}
.art {{ font-weight:700; white-space:nowrap; font-size:12px; }}
.nm {{ font-size:11.5px; line-height:1.25; }}
.qty {{ text-align:center; font-weight:800; font-size:20px; width:50px; }}
.chk {{ width:30px; }}
.chk::after {{ content:''; display:block; width:20px; height:20px; border:2px solid #bbb; border-radius:4px; margin:auto; }}
.ordn {{ width:150px; background:#fcfcfc; text-align:center; }}
.onum {{ font-size:14px; font-weight:800; margin-bottom:3px; }}
.lbl {{ width:130px; border:1px solid #ddd; border-radius:4px; }}
.otarget {{ font-size:10px; color:#666; margin-top:3px; }}
</style></head><body>
<h1>Лист сборки заказов · Яндекс.Маркет · {len(orders)} заказов</h1>
<div class="sub"><span class="badge">{len(orders)} заказов</span><span class="badge">{units} шт</span>
{esc(data['cname'])} · сформировано {esc(data['generated'])}</div>
<table><thead><tr><th>Заказ / этикетка</th><th>Ячейка</th><th>Фото</th><th>Артикул</th><th>Наименование</th><th>Кол-во</th><th>✓</th></tr></thead>
<tbody>{''.join(orows)}</tbody></table>
</body></html>"""
hp = os.path.join(OUT, "assembly.html")
io.open(hp, "w", encoding="utf-8").write(doc)
edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
down = os.environ.get("YM_OUTPUT_DIR", os.path.join(os.path.expanduser("~"), "Downloads"))
dst = os.path.join(down, f"Лист сборки ЯМ {len(orders)} заказов.pdf")
if os.path.exists(dst):
    os.remove(dst)
subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={dst}",
                "file:///" + hp.replace("\\", "/")], timeout=180)
print("ГОТОВО:", dst, "OK" if os.path.exists(dst) else "FAIL", "|", len(orders), "заказов,", units, "шт")
