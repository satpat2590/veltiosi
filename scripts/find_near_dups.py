#!/usr/bin/env python3
"""Near-duplicate detection via embedding cosine similarity (Stage 2, no LLM)."""
import sys, json
import numpy as np
sys.path.insert(0, "src")
from veltiosi.services.semantic_search import get_index

THRESH = 0.88

idx = get_index()
V = idx.vectors.astype(np.float32)
N = len(idx.paths)
# vectors already normalized => V @ V.T is cosine
sim = V @ V.T
np.fill_diagonal(sim, 0.0)

# top pairs above threshold
rows, cols = np.triu_indices(N, k=1)
vals = sim[rows, cols]
mask = vals > THRESH
pairs = sorted(
    [(float(vals[i]), idx.paths[rows[i]], idx.paths[cols[i]]) for i in range(len(vals)) if mask[i]],
    key=lambda x: -x[0],
)

print(f"index notes: {N}")
print(f"near-duplicate pairs (cosine > {THRESH}): {len(pairs)}\n")
for s, a, b in pairs[:60]:
    def rel(p): return p.replace("/home/satyamini/Obsidian/", "")
    print(f"  {s:.3f}\n    A: {rel(a)}\n    B: {rel(b)}")

# also dump top similarity distribution (to show how much redundancy exists)
json.dump([{"sim": s, "a": a, "b": b} for s, a, b in pairs], open("/tmp/near_dups.json", "w"), indent=1)
print(f"\n[saved /tmp/near_dups.json with {len(pairs)} pairs]")
