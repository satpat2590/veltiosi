#!/usr/bin/env python3
"""Veltiosi search UI — fast ranked search across Omni + note viewer.

Run: PYTHONPATH=src uvicorn server:app --host 127.0.0.1 --port 8611
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

STATIC = ROOT / "static"

app = FastAPI(title="Veltiosi Search", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "veltiosi-search", "version": "2.0.0"}


@app.get("/api/search")
def search(q: str = Query(...), top_k: int = Query(15), rerank: bool = Query(True)):
    from veltiosi.services.omni_search import search_everything

    return search_everything(q, top_k=top_k, rerank=rerank)


@app.get("/api/note")
def note(path: str = Query(...)):
    from veltiosi.services.omni_search import read_note

    n = read_note(path)
    if n is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return n


app.mount("/static", StaticFiles(directory=STATIC), name="static")


# Warm the embedding index + model at startup so the first search isn't slow.
from veltiosi.services.semantic_search import get_index  # noqa: E402

get_index()