"""Data-source connectors — the router's delegation targets across Omni.

Each connector turns a natural-language question about ONE data source into a
factual text summary (a deterministic lookup — no LLM). Fail-open: a missing DB
or a connectivity error returns ``None`` so the router falls back to its
"this needs the {source}" message instead of crashing.

Sources: whoop (health SQLite), edoras (PostgreSQL), raga (Spotify SQLite),
atma (HTTP API), itihasa (history SQLite). The vault (Obsidian) is handled by
the existing retrieval service, not here.
"""

import logging
import re
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HOME = Path.home()
WHOOP_DB = HOME / "whoop-sync" / "health.db"
RAGA_DB = HOME / "whoop-sync" / "spotify_history.db"
ITIHASA_DB = HOME / "itihasa" / "itihasa.db"
EDORAS_PG_ENV = HOME / ".config" / "edoras-pg.env"


def _readonly_connect(path: Path) -> Optional[sqlite3.Connection]:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


class DataSourceConnector(ABC):
    name = "base"

    @abstractmethod
    def query(self, question: str) -> Optional[str]:
        """Return a factual text summary for the question, or None if unavailable."""


class WhoopSource(DataSourceConnector):
    name = "whoop"

    def query(self, question: str) -> Optional[str]:
        conn = _readonly_connect(WHOOP_DB)
        if conn is None:
            return None
        try:
            rows = conn.execute(
                "SELECT cycle_date, recovery_score, strain_score, resting_heart_rate, "
                "hrv_rmssd_ms, sleep_in_bed_ms, spo2_pct FROM daily_cycles "
                "ORDER BY cycle_date DESC LIMIT 7"
            ).fetchall()
        except Exception as e:
            logger.warning(f"whoop query failed: {e}")
            return None
        finally:
            conn.close()
        if not rows:
            return None
        lines = [f"WHOOP — last {len(rows)} days:"]
        for r in rows:
            sleep_h = (r["sleep_in_bed_ms"] or 0) / 3_600_000
            hrv = round(r["hrv_rmssd_ms"]) if r["hrv_rmssd_ms"] else None
            spo2 = round(r["spo2_pct"]) if r["spo2_pct"] else None
            lines.append(
                f"- {r['cycle_date']}: recovery {round(r['recovery_score'] or 0)}%, "
                f"strain {round(r['strain_score'] or 0, 1)}, RHR {r['resting_heart_rate'] or '?'}, "
                f"HRV {hrv or '?'}ms, sleep {sleep_h:.1f}h, SpO2 {spo2 or '?'}%"
            )
        return "\n".join(lines)


class EdorasSource(DataSourceConnector):
    name = "edoras"

    def _url(self) -> Optional[str]:
        try:
            for line in open(EDORAS_PG_ENV):
                if line.startswith("EDORAS_DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
        return None

    def query(self, question: str) -> Optional[str]:
        url = self._url()
        if not url:
            return None
        import psycopg2

        try:
            conn = psycopg2.connect(url)
            cur = conn.cursor()
            cur.execute(
                "SELECT portfolio_id, snapshot_time, total_value, daily_return, "
                "sharpe_30d, max_drawdown_30d, positions_count "
                "FROM ledger.portfolio_performance "
                "WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM ledger.portfolio_performance) "
                "ORDER BY total_value DESC LIMIT 10"
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.warning(f"edoras query failed: {e}")
            return None
        if not rows:
            return None
        lines = ["Edoras — portfolio snapshot (latest):"]
        for pid, ts, total, dr, sharpe, mdd, pos in rows:
            sh = f"{sharpe:.2f}" if sharpe is not None else "?"
            m = f"{mdd:.1f}%" if mdd is not None else "?"
            d = f"{dr:+.2f}%" if dr is not None else "?"
            lines.append(
                f"- portfolio {pid}: NAV {total:,.2f} | day {d} | "
                f"Sharpe(30d) {sh} | MDD(30d) {m} | {pos} positions"
            )
        return "\n".join(lines)


class RagaSource(DataSourceConnector):
    name = "raga"

    def query(self, question: str) -> Optional[str]:
        conn = _readonly_connect(RAGA_DB)
        if conn is None:
            return None
        try:
            rows = conn.execute(
                "SELECT track_name, artist_names, played_at FROM listening_history "
                "ORDER BY played_at DESC LIMIT 10"
            ).fetchall()
        except Exception as e:
            logger.warning(f"raga query failed: {e}")
            return None
        finally:
            conn.close()
        if not rows:
            return None
        lines = ["Spotify — recently played:"]
        for r in rows:
            lines.append(f"- {r['track_name']} — {r['artist_names']}")
        return "\n".join(lines)


class ItihasaSource(DataSourceConnector):
    name = "itihasa"
    _STOPWORDS = {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
        "is", "are", "was", "were", "when", "where", "how", "why", "what",
        "did", "does", "do", "my", "me", "i", "you", "about", "around",
        "happened", "history", "event", "events", "show", "tell", "find", "list",
    }

    def query(self, question: str) -> Optional[str]:
        conn = _readonly_connect(ITIHASA_DB)
        if conn is None:
            return None
        rows = None
        tokens = [
            t for t in re.findall(r"[a-zA-Z0-9]+", question.lower())
            if t not in self._STOPWORDS and len(t) >= 3
        ]
        if tokens:
            expr = " OR ".join(f'"{t}"*' for t in tokens)
            try:
                rows = conn.execute(
                    "SELECT e.name, e.year, e.era, e.event_type FROM events_fts f "
                    "JOIN events e ON e.id = f.event_id "
                    "WHERE events_fts MATCH ? ORDER BY bm25(events_fts) LIMIT 8",
                    (expr,),
                ).fetchall()
            except Exception:
                rows = None
        if not rows:
            try:
                rows = conn.execute(
                    "SELECT name, year, era, event_type FROM events "
                    "WHERE status='active' ORDER BY year DESC LIMIT 8"
                ).fetchall()
            except Exception:
                pass
        conn.close()
        if not rows:
            return None
        lines = ["Itihasa — matching events:"]
        for r in rows:
            y = f"{abs(r['year'])} BCE" if r["year"] < 0 else f"{r['year']} CE"
            lines.append(f"- {r['name']} ({y}, {r['era']}, {r['event_type']})")
        return "\n".join(lines)


class AtmaSource(DataSourceConnector):
    name = "atma"

    def query(self, question: str) -> Optional[str]:
        from .atma import AtmaConnector

        conn = AtmaConnector()
        tasks = conn.get_recent_tasks(days_back=7)
        if not tasks:
            return None
        lines = ["Atma — recently completed tasks:"]
        for t in tasks[:10]:
            lines.append(f"- {t.title}")
        return "\n".join(lines)


REGISTRY = {
    "whoop": WhoopSource(),
    "edoras": EdorasSource(),
    "raga": RagaSource(),
    "itihasa": ItihasaSource(),
    "atma": AtmaSource(),
}


def query_source(source: str, question: str) -> Optional[str]:
    """Query a non-vault data source; returns text or None (fail-open)."""
    src = REGISTRY.get(source)
    if src is None:
        return None
    try:
        return src.query(question)
    except Exception as e:  # noqa: BLE001 — a broken source must not sink the query
        logger.warning(f"source '{source}' query failed: {e}")
        return None