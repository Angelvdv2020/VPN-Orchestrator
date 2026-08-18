from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 received_at INTEGER NOT NULL,
 observed_at INTEGER NOT NULL,
 device_id TEXT NOT NULL,
 nonce TEXT NOT NULL,
 path_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('up','down','unknown')),
 network TEXT NOT NULL CHECK(network IN ('mobile','wifi','unknown')),
 operator TEXT NOT NULL DEFAULT '',
 country TEXT NOT NULL DEFAULT '',
 latency_ms REAL,
 detail TEXT NOT NULL DEFAULT '',
 UNIQUE(device_id, nonce)
);
CREATE INDEX IF NOT EXISTS telemetry_recent ON telemetry(received_at DESC);
CREATE INDEX IF NOT EXISTS telemetry_path ON telemetry(path_id, network, received_at DESC);
"""


class TelemetryStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        return db

    def add(self, device_id: str, nonce: str, payload: dict[str, Any], *, received_at: int | None = None) -> int:
        now = int(time.time()) if received_at is None else received_at
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO telemetry
                (received_at,observed_at,device_id,nonce,path_id,status,network,operator,country,latency_ms,detail)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (now, int(payload["observed_at"]), device_id, nonce, payload["path_id"],
                 payload["status"], payload["network"], payload.get("operator", ""),
                 payload.get("country", ""), payload.get("latency_ms"), payload.get("detail", "")),
            )
            return int(cur.lastrowid)

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        with self.connect() as db:
            rows = db.execute("SELECT * FROM telemetry ORDER BY received_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(x) for x in rows]

    def summary(self, since: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT path_id, network, operator, country, status,
                COUNT(*) samples, ROUND(AVG(latency_ms),1) avg_latency_ms,
                MAX(received_at) last_seen
                FROM telemetry WHERE received_at >= ?
                GROUP BY path_id,network,operator,country,status
                ORDER BY path_id,network,status""", (since,)
            ).fetchall()
        return [dict(x) for x in rows]

    def prune(self, before: int) -> int:
        with self.connect() as db:
            cur = db.execute("DELETE FROM telemetry WHERE received_at < ?", (before,))
            return int(cur.rowcount)
