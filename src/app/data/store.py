"""Persistent payload cache (SQLite, zlib-compressed JSON).

The store is deliberately dumb: ``(kind, key) -> JSON document`` plus the
metadata the repository needs to decide freshness (when it was fetched, where
it came from, whether it is final). Interpretation lives elsewhere.

Every call is short and guarded by one lock, so it is safe to use from worker
threads (the repository runs it through ``asyncio.to_thread`` for big payloads).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS payload (
    kind        TEXT NOT NULL,
    key         TEXT NOT NULL,
    fetched_at  REAL NOT NULL,
    source      TEXT NOT NULL,
    complete    INTEGER NOT NULL DEFAULT 0,
    size        INTEGER NOT NULL DEFAULT 0,
    body        BLOB NOT NULL,
    PRIMARY KEY (kind, key)
);
CREATE INDEX IF NOT EXISTS payload_kind ON payload (kind);
CREATE TABLE IF NOT EXISTS kv (
    k          TEXT PRIMARY KEY,
    v          TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


@dataclass(slots=True)
class Record:
    kind: str
    key: str
    body: Any
    fetched_at: float
    source: str
    complete: bool


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path) if str(path) != ":memory:" else path
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    # ------------------------------------------------------------------ payloads

    def get(self, kind: str, key: str) -> Record | None:
        with self._lock:
            row = self._db.execute(
                "SELECT fetched_at, source, complete, body FROM payload WHERE kind=? AND key=?",
                (kind, key),
            ).fetchone()
        if row is None:
            return None
        fetched_at, source, complete, blob = row
        try:
            body = json.loads(zlib.decompress(blob))
        except (zlib.error, json.JSONDecodeError):
            return None  # corrupted row: behave as a cache miss and let it be refetched
        return Record(kind, key, body, fetched_at, source, bool(complete))

    def put(
        self,
        kind: str,
        key: str,
        body: Any,
        *,
        source: str,
        complete: bool = False,
        fetched_at: float | None = None,
    ) -> float:
        blob = zlib.compress(json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(), 6)
        stamp = time.time() if fetched_at is None else fetched_at
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO payload (kind, key, fetched_at, source, complete, size, body)"
                " VALUES (?,?,?,?,?,?,?)",
                (kind, key, stamp, source, int(complete), len(blob), blob),
            )
            self._db.commit()
        return stamp

    def touch(self, kind: str, key: str, fetched_at: float | None = None) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE payload SET fetched_at=? WHERE kind=? AND key=?",
                (time.time() if fetched_at is None else fetched_at, kind, key),
            )
            self._db.commit()

    def delete(self, kind: str, key: str | None = None) -> int:
        with self._lock:
            if key is None:
                cur = self._db.execute("DELETE FROM payload WHERE kind=?", (kind,))
            else:
                cur = self._db.execute("DELETE FROM payload WHERE kind=? AND key=?", (kind, key))
            self._db.commit()
            return cur.rowcount

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM payload")
            self._db.commit()

    def keys(self, kind: str) -> list[tuple[str, float, bool]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT key, fetched_at, complete FROM payload WHERE kind=? ORDER BY key", (kind,)
            ).fetchall()
        return [(key, fetched_at, bool(complete)) for key, fetched_at, complete in rows]

    def meta(self, kind: str, key: str) -> tuple[float, str, bool] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT fetched_at, source, complete FROM payload WHERE kind=? AND key=?", (kind, key)
            ).fetchone()
        return None if row is None else (row[0], row[1], bool(row[2]))

    def stats(self) -> dict:
        with self._lock:
            rows = self._db.execute(
                "SELECT kind, COUNT(*), COALESCE(SUM(size),0), MIN(fetched_at), MAX(fetched_at)"
                " FROM payload GROUP BY kind ORDER BY kind"
            ).fetchall()
        kinds = {
            kind: {"count": count, "bytes": size, "oldest": oldest, "newest": newest}
            for kind, count, size, oldest, newest in rows
        }
        return {
            "kinds": kinds,
            "total_bytes": sum(k["bytes"] for k in kinds.values()),
            "total_items": sum(k["count"] for k in kinds.values()),
        }

    # ------------------------------------------------------------------ key/value

    def kv_get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return default

    def kv_set(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO kv (k, v, updated_at) VALUES (?,?,?)",
                (key, json.dumps(value, ensure_ascii=False), time.time()),
            )
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()
