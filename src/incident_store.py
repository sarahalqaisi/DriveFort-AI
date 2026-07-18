from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class IncidentStore:
    """Small SQLite event store used by the demo dashboard.

    The app is still a prototype, so this intentionally stays dependency-free and
    safe for Windows: the database is created in the project folder under data/.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        configured_path = db_path or os.environ.get("DRIVEFORT_INCIDENT_DB") or os.environ.get("ZONEGUARD_INCIDENT_DB") or "data/drivefort_incidents.db"
        self.db_path = Path(configured_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        """Yield a SQLite connection and always close it afterwards.

        sqlite3.Connection's own context manager commits/rolls back but does not
        close the handle, which caused resource warnings during repeated dashboard
        polling and tests.
        """
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    threat_level TEXT NOT NULL,
                    risk REAL NOT NULL,
                    action TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            # Backward-compatible schema migration for forensic audit fields.
            cols = {row[1] for row in conn.execute("PRAGMA table_info(incidents)").fetchall()}
            if "payload_hash" not in cols:
                conn.execute("ALTER TABLE incidents ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''")
            if "prev_hash" not in cols:
                conn.execute("ALTER TABLE incidents ADD COLUMN prev_hash TEXT NOT NULL DEFAULT ''")
            if "chain_hash" not in cols:
                conn.execute("ALTER TABLE incidents ADD COLUMN chain_hash TEXT NOT NULL DEFAULT ''")
            if "integrity_status" not in cols:
                conn.execute("ALTER TABLE incidents ADD COLUMN integrity_status TEXT NOT NULL DEFAULT 'unverified'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at)")

    @staticmethod
    def generate_incident_hash(incident_data: Dict[str, Any]) -> str:
        """Return a deterministic SHA-256 hash for an incident payload."""
        data_string = json.dumps(incident_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(data_string.encode("utf-8")).hexdigest()

    def _last_chain_hash(self) -> str:
        with self._connection() as conn:
            row = conn.execute("SELECT chain_hash FROM incidents ORDER BY id DESC LIMIT 1").fetchone()
        return str(row["chain_hash"] or "") if row else ""

    @staticmethod
    def _chain_hash(payload_hash: str, prev_hash: str, created_at: str, scenario: str) -> str:
        material = "|".join([str(prev_hash or "GENESIS"), str(payload_hash), str(created_at), str(scenario)])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def add_snapshot(self, snapshot: Dict[str, Any]) -> int:
        risks = snapshot.get("risks", {})
        attack = snapshot.get("attack", {})
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        payload_hash = self.generate_incident_hash(snapshot)
        prev_hash = self._last_chain_hash()
        chain_hash = self._chain_hash(payload_hash, prev_hash, created_at, attack.get("attack_name", "normal"))
        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO incidents(created_at, scenario, threat_level, risk, action, summary, payload, payload_hash, prev_hash, chain_hash, integrity_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    attack.get("attack_name", "normal"),
                    risks.get("threat_level", "NORMAL"),
                    float(risks.get("overall", 0.0)),
                    risks.get("action", "ALLOW"),
                    risks.get("summary", ""),
                    payload,
                    payload_hash,
                    prev_hash,
                    chain_hash,
                    "verified",
                ),
            )
            conn.execute("DELETE FROM incidents WHERE id NOT IN (SELECT id FROM incidents ORDER BY id DESC LIMIT 100)")
            return int(cur.lastrowid)

    def list_recent(self, limit: int = 12) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id, created_at, scenario, threat_level, risk, action, summary, payload_hash, prev_hash, chain_hash, integrity_status FROM incidents ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


    def verify_recent(self, limit: int = 25) -> Dict[str, Any]:
        """Verify that stored incident payloads still match their hashes."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id, created_at, scenario, payload, payload_hash, prev_hash, chain_hash FROM incidents ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        verified = 0
        failed = []
        previous = ""
        for row in rows:
            try:
                payload_data = json.loads(row["payload"])
                payload_ok = self.generate_incident_hash(payload_data) == row["payload_hash"]
            except Exception:
                payload_ok = False
            chain_ok = self._chain_hash(row["payload_hash"], row["prev_hash"], row["created_at"], row["scenario"]) == row["chain_hash"]
            link_ok = (not previous) or row["prev_hash"] == previous
            if payload_ok and chain_ok and link_ok:
                verified += 1
            else:
                failed.append({"id": row["id"], "payload_ok": payload_ok, "chain_ok": chain_ok, "link_ok": link_ok})
            previous = row["chain_hash"]
        return {"checked": len(rows), "verified": verified, "failed": failed, "integrity_verified": len(failed) == 0}
