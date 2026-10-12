#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, json, requests
rows = {r["offerId"]: r for r in json.load(open("catalog_named.json", encoding="utf-8"))}
want = ["GRA-02000", "GRA-00240", "GRA-00060", "GRA-07840", "GRA-00230",
        "GRA-00110", "GRA-00160", "GRA-00250", "GRA-01502", "GRA-00140",
        "GRA-04400", "GRA-04401", "GRA-07920", "GRA-00120"]
os.makedirs("check", exist_ok=True)
for oid in want:
    url = rows[oid]["picture"]
    if url.endswith("/orig"):
        url = url[:-5] + "/300x300"
    try:
        r = requests.get(url, timeout=60)
        open(f"check/{oid}.jpg", "wb").write(r.content)
        print("ok", oid, len(r.content))
    except Exception as e:
        print("fail", oid, e)
