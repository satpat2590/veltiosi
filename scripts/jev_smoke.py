"""Live smoke test: one Jev call against a real Roamings note."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from veltiosi.indexing.jev_client import JevClient
from veltiosi.indexing.jev_classifier import JevNoteClassifier

VAULT = Path.home() / "Obsidian"
notes = sorted((VAULT / "Satya's Roamings").glob("*.md"))
note = notes[0]
content = note.read_text(encoding="utf-8")
title = note.stem

client = JevClient()
print(f"enabled={client.enabled} model={client.model} base_url={client.base_url}")

t0 = time.monotonic()
answers = client.decide(
    JevNoteClassifier.render_state(title, content),
    JevNoteClassifier(client=client).build_questions(),
)
dt = time.monotonic() - t0
print(f"raw answers in {dt:.2f}s:")
if answers is None:
    print("  -> None (FAIL)")
    sys.exit(1)

import json

print(json.dumps(answers, indent=2))

cls = JevNoteClassifier(client=client).classify(title, content)
print("\nParsed JevClassification:")
print(f"  root={cls.root} conf={cls.root_confidence} probs={cls.root_probabilities}")
print(f"  note_type={cls.note_type} conf={cls.note_type_confidence}")
print(f"  requires_slope={cls.requires_slope} cross_domain={cls.cross_domain}")
print(f"  subcategories={cls.subcategories}")