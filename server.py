#!/usr/bin/env python3
"""Veltiosi search UI — natural-language search, Jev-routed, over the vault.

Run: PYTHONPATH=src uvicorn server:app --host 127.0.0.1 --port 8611
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

STATIC = ROOT / "static"

app = FastAPI(title="Veltiosi Search", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_workflow = None


def _get_workflow():
    global _workflow
    if _workflow is None:
        from veltiosi.workflows.wiki_query import WikiQueryWorkflow

        _workflow = WikiQueryWorkflow()
    return _workflow


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "veltiosi-search", "version": "1.0.0"}


@app.get("/api/search")
def search(q: str = Query(...), top_k: int = Query(8)):
    from veltiosi.services.omni_search import search_everything

    return search_everything(q, top_k=top_k)


app.mount("/static", StaticFiles(directory=STATIC), name="static")