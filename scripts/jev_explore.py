"""Explore what Jev unlocks beyond the fixed Veltiosi taxonomy.

Three demonstrations on the SAME generic ``JevDecider`` primitive:
  1. Arbitrary-label classification  — prove a future domain (Itihasa) reuses
     the plumbing unchanged by classifying snippets against a bespoke label set.
  2. Ordering via Score              — rank items on a rubric, the "ordering"
     primitive (prefigures ranking historical events by causal significance).
  3. Concept convergence via Noul    — detect whether a note extends an existing
     thread (the "compounding page" / dedup unlock).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from veltiosi.indexing.jev_decider import JevDecider

d = JevDecider()
print(f"JevDecider enabled={d.enabled}")

# ── 1. Arbitrary-label classification (extensibility) ────────────────────────
print("\n=== 1. Arbitrary-label classification (Itihasa event types) ===")
EVENT_TYPES = {
    "economic_crisis": "A financial or market crisis, crash, or monetary rupture",
    "war": "Armed conflict between states or factions",
    "empire_rise": "A state or empire expanding and consolidating power",
    "empire_fall": "A state or empire collapsing or fragmenting",
    "technological_shift": "A major technological or systemic discontinuity",
    "pandemic": "A widespread disease affecting large populations",
    "other": "None of the above fits",
}
samples = [
    ("1492", "Christopher Columbus reaches the Americas, initiating transatlantic exchange."),
    ("1453", "Constantinople falls to the Ottoman Turks, ending the Byzantine Empire."),
    ("1971", "The United States ends the Bretton Woods gold convertibility of the dollar."),
    ("1347", "The Black Death reaches Europe, killing a third of the population."),
]
for label, text in samples:
    dec = d.choice(text, EVENT_TYPES, "Classify this historical event.")
    print(f"  {label:6s} -> {dec.argmax:20s} (top2={[f'{k}:{v:.2f}' for k,v in dec.top_k(2)]})")

# ── 2. Ordering via Score ────────────────────────────────────────────────────
print("\n=== 2. Ordering: rank historical events by causal significance ===")
RUBRIC = [
    "Localized, minor consequence",
    "Regional consequence, one domain affected",
    "National consequence, several domains",
    "Civilizational consequence, shapes decades",
    "World-historical, reshapes the long arc",
]
pretenders = [
    ("Black Death 1347", "Wipes out a third of Europe; labor scarcity ends feudalism."),
    ("Bretton Woods 1971", "Fiat era begins; global capital flows and inflation dynamics change."),
    ("Fall of Rome 476", "Western Roman Empire collapses; Europe fragments for a millennium."),
    ("Printing press 1440", "Mass literacy, Reformation, scientific revolution follow."),
]
for name, text in pretenders:
    dec = d.score(text, RUBRIC, "How causally significant is this event on world history?")
    # expectation over the rubric index = a continuous "significance" number 0..4
    sig = dec.expectation({RUBRIC[i]: i for i in range(len(RUBRIC))})
    print(f"  {name:20s} significance={sig:.2f}  (conf={dec.confidence and round(dec.confidence,2)})")

# ── 3. Concept convergence via Noul ──────────────────────────────────────────
print("\n=== 3. Concept convergence (does note B extend note A's thread?) ===")
anchor = "Cellular automata as a substrate where simple rules produce consciousness-like self-organization."
candidates = {
    "Compression as Consciousness Genesis": "If consciousness is compression, cellular automata compress local rules into global order.",
    "Power Encoding in Financial Systems": "Wealth concentrates in markets through asymmetric rule interpretation.",
    "Minimal Computational Substrates": "The smallest rule set that still yields self-modeling behavior is a consciousness floor.",
}
for title, text in candidates.items():
    dec = d.noul(
        state={"anchor": anchor, "candidate": text},
        instructions="Does the candidate note extend the SAME conceptual thread as the anchor note?",
    )
    print(f"  {title:40s} converges={dec.distribution.get('true', 0):.2f}")

print("\nDone.")