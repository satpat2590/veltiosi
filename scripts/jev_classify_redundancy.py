#!/usr/bin/env python3
"""Classify redundancy candidates with Jev (System One calibrated choice).

Stage 3 (LLM): near-duplicate pairs -> redundant/distinct; stubs + auto-gen
tag pages -> eliminate/keep. Fail-open: on any Jev failure the candidate is
flagged 'unknown' rather than auto-eliminated.
"""
import sys, json, re
from pathlib import Path
sys.path.insert(0, "src")
from veltiosi.indexing.jev_decider import JevDecider

VAULT = Path.home() / "Obsidian"
RO = {"01-Natural-Philosophy","02-Economics","03-Geopolitics","04-Language",
      "05-Computation","06-Research-Frameworks","07-Poetry","16-Meetings",
      "17-References","Satya's Roamings"}

def rel(p): return str(p).replace(str(VAULT)+"/", "")

def body(path, n=500):
    try:
        t = Path(path).read_text(encoding="utf-8", errors="replace")
        m = re.match(r'^---\r?\n.*?\r?\n---\r?\n?', t, re.DOTALL)
        t = t[m.end():] if m else t
        return t.strip()[:n]
    except Exception:
        return ""

decider = JevDecider()
results = {"pairs": [], "stubs": []}

# ---- near-duplicate pairs ----
pairs = json.load(open("/tmp/near_dups.json"))
# dedupe to unique files involved (a file may appear in several pairs)
seen_files = set()
uniq_pairs = []
for p in pairs:
    if p["a"] not in seen_files and p["b"] not in seen_files:
        uniq_pairs.append(p)
        seen_files.add(p["a"]); seen_files.add(p["b"])

print(f"classifying {len(uniq_pairs)} unique near-duplicate pairs with Jev…")
for p in uniq_pairs:
    a, b = p["a"], p["b"]
    state = {
        "note_A": {"path": rel(a), "title": Path(a).stem, "body": body(a)},
        "note_B": {"path": rel(b), "title": Path(b).stem, "body": body(b)},
    }
    d = decider.choice(
        state,
        {"redundant": "same ground; one can be archived/merged without losing unique info",
         "distinct": "meaningfully different; both should be kept"},
        instructions="Are these two notes redundant (one can be archived without losing unique information)?",
    )
    ro_ = (rel(a).split("/")[0] in RO) or (rel(b).split("/")[0] in RO)
    results["pairs"].append({
        "sim": p["sim"], "a": rel(a), "b": rel(b),
        "verdict": d.argmax, "conf": d.confidence, "dist": d.distribution,
        "read_only": ro_,
    })

# ---- stubs + auto-generated ----
survey = json.load(open("/tmp/veltiosi_survey.json"))
stub_cands = [n for n in survey if n["auto_created"] or n["body_len"] < 120]
print(f"classifying {len(stub_cands)} stubs/auto-generated with Jev…")
for n in stub_cands:
    state = {"path": n["rel"], "title": Path(n["path"]).stem, "body": body(n["path"], 400)}
    d = decider.choice(
        state,
        {"eliminate": "auto-generated stub or empty placeholder; no lasting value; safe to archive/remove",
         "keep": "has unique content worth keeping"},
        instructions="Is this note an auto-generated stub / empty placeholder that can be eliminated, or does it hold unique content?",
    )
    results["stubs"].append({
        "path": n["rel"], "body_len": n["body_len"], "auto": n["auto_created"],
        "verdict": d.argmax, "conf": d.confidence, "dist": d.distribution,
        "read_only": n["top"] in RO,
    })

json.dump(results, open("/tmp/jev_redundancy.json", "w"), indent=1, default=str)
print("\n[saved /tmp/jev_redundancy.json]")
