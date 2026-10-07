#!/usr/bin/env python3
"""Survey the Obsidian vault for redundancy / irrelevance candidates.

Stage 1 (mechanical, no LLM): auto-generated stubs, empty notes, exact dups,
near-duplicate embedding pairs, orphaned auto-pages.
"""
import os, re, json, hashlib, sys
from collections import Counter, defaultdict
from pathlib import Path

VAULT = Path.home() / "Obsidian"
RO = {"01-Natural-Philosophy","02-Economics","03-Geopolitics","04-Language",
      "05-Computation","06-Research-Frameworks","07-Poetry","16-Meetings",
      "17-References","Satya's Roamings"}

def strip_fm(txt):
    m = re.match(r'^---\r?\n.*?\r?\n---\r?\n?', txt, re.DOTALL)
    return txt[m.end():] if m else txt

def author(txt):
    m = re.search(r'author:\s*([\w-]+)', txt)
    return m.group(1) if m else None

notes = []
for p in VAULT.rglob("*.md"):
    if "/.git/" in str(p) or "/.obsidian/" in str(p):
        continue
    rel = str(p.relative_to(VAULT))
    top = rel.split("/")[0]
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    body = strip_fm(raw)
    notes.append({
        "rel": rel, "top": top, "path": str(p),
        "raw_len": len(raw), "body_len": len(body.strip()),
        "author": author(raw),
        "auto_created": "veltiosi_linker" in raw or "Auto-created by Veltiosi" in raw,
        "is_index": rel.endswith("index.md") or "Maps-of-Content" in rel or rel.endswith("-Index.md"),
        "managed_only": ("veltiosi-managed" in raw) and len(body.strip()) < 300,
        "hash": hashlib.md5(body.strip().encode()).hexdigest(),
    })

print(f"TOTAL notes: {len(notes)}")
print(f"Read-only-folder notes: {sum(1 for n in notes if n['top'] in RO)}")
print(f"Read-write-folder notes: {sum(1 for n in notes if n['top'] not in RO)}")
print()

# 1. Auto-generated linker/tag pages
auto = [n for n in notes if n["auto_created"]]
print(f"=== 1. AUTO-GENERATED (veltiosi_linker / Auto-created) : {len(auto)} ===")
for n in sorted(auto, key=lambda x: x["body_len"]):
    print(f"  [{n['body_len']:>5}B] {n['rel']}")

# 2. Empty / stub notes (body < 120 chars)
stubs = [n for n in notes if n["body_len"] < 120]
print(f"\n=== 2. STUBS (<120B body) : {len(stubs)} ===")
for n in sorted(stubs, key=lambda x: x["body_len"]):
    print(f"  [{n['body_len']:>5}B] {n['rel']}")

# 3. Exact duplicate bodies
byhash = defaultdict(list)
for n in notes:
    if n["body_len"] > 50:  # ignore trivial
        byhash[n["hash"]].append(n["rel"])
dups = {h: v for h, v in byhash.items() if len(v) > 1}
print(f"\n=== 3. EXACT DUPLICATE BODIES : {len(dups)} groups ===")
for h, v in sorted(dups.items(), key=lambda x: -len(x[1])):
    print(f"  ({len(v)} files): {v[0]}  <->  {', '.join(v[1:])}")

# 4. Tiny-content tag pages / index pages in 20-Task-System
ts = [n for n in notes if n["top"] == "20-Task-System"]
small_ts = [n for n in ts if n["body_len"] < 200]
print(f"\n=== 4. 20-Task-System small pages (<200B): {len(small_ts)} of {len(ts)} ===")
for n in sorted(small_ts, key=lambda x: x["body_len"])[:40]:
    print(f"  [{n['body_len']:>5}B] {n['rel']}")

json.dump(notes, open("/tmp/veltiosi_survey.json", "w"), indent=1)
print(f"\n[saved /tmp/veltiosi_survey.json]")
