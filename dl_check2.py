#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, json, requests
rows = {r["offerId"]: r for r in json.load(open("catalog_named.json", encoding="utf-8"))}
want = ["GRA-08110", "GRA-08070", "GRA-08240", "GRA-07740"]
os.makedirs("check", exist_ok=True)
for oid in want:
    url = rows[oid]["picture"]
    if url.endswith("/orig"):
        url = url[:-5] + "/300x300"
    r = requests.get(url, timeout=60)
    open(f"check/{oid}.jpg", "wb").write(r.content)
    print("ok", oid, len(r.content))
