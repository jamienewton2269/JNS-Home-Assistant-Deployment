import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS facts(
  namespace TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at REAL NOT NULL,
  PRIMARY KEY(namespace,key)
);
CREATE TABLE IF NOT EXISTS observations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repairs(
  id TEXT PRIMARY KEY,
  fingerprint TEXT UNIQUE,
  title TEXT NOT NULL,
  subsystem TEXT NOT NULL,
  recipe_json TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5,
  successful_runs INTEGER NOT NULL DEFAULT 0,
  failed_runs INTEGER NOT NULL DEFAULT 0,
  portable INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS repair_search USING fts5(
  repair_id UNINDEXED,title,subsystem,problem,symptoms,diagnosis,steps
);
"""


class StewardStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA busy_timeout=3000")
        self.db.executescript(SCHEMA)

    def set_fact(self, namespace, key, value):
        with self.lock:
            self.db.execute(
                """INSERT INTO facts(namespace,key,value_json,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET
                value_json=excluded.value_json,updated_at=excluded.updated_at""",
                (namespace, key, json.dumps(value, sort_keys=True), time.time()),
            )
            self.db.commit()

    def get_fact(self, namespace: str, key: str) -> Any | None:
        with self.lock:
            row = self.db.execute(
                "SELECT value_json FROM facts WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
            return None if row is None else json.loads(row[0])

    def observe(self, kind, source, payload):
        with self.lock:
            self.db.execute(
                "INSERT INTO observations(ts,kind,source,payload_json) VALUES(?,?,?,?)",
                (time.time(), kind, source, json.dumps(payload, sort_keys=True)),
            )
            self.db.commit()

    @staticmethod
    def _search_text(recipe: dict[str, Any]) -> tuple[str, str, str, str]:
        symptoms = " ".join(str(x) for x in recipe.get("symptoms", []) if x)
        steps = " ".join(
            str(x)
            for key in ("preconditions", "repair_steps", "verification_steps", "rollback_steps")
            for x in recipe.get(key, [])
            if x
        )
        return (
            str(recipe.get("problem", "")),
            symptoms,
            str(recipe.get("diagnosis", "")),
            steps,
        )

    def upsert_repair(
        self,
        *,
        repair_id: str,
        fingerprint: str,
        recipe: dict[str, Any],
        successful_runs: int = 0,
        failed_runs: int = 0,
    ) -> str:
        title = str(recipe.get("title") or "Repair")
        subsystem = str(recipe.get("subsystem") or "unknown")
        confidence = float(recipe.get("confidence", 0.5))
        portable = int(bool(recipe.get("portable", False)))
        now = time.time()

        with self.lock:
            existing = self.db.execute(
                "SELECT id,recipe_json,successful_runs,failed_runs FROM repairs WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if existing:
                repair_id = existing[0]
                old = json.loads(existing[1])
                old.update({k: v for k, v in recipe.items() if v not in (None, [], {}, "")})
                recipe = old
                successful_runs += int(existing[2])
                failed_runs += int(existing[3])
                title = str(recipe.get("title") or title)
                subsystem = str(recipe.get("subsystem") or subsystem)
                confidence = max(confidence, float(recipe.get("confidence", 0.5)))
                portable = int(bool(recipe.get("portable", portable)))

            raw = json.dumps(recipe, sort_keys=True)
            self.db.execute(
                """INSERT INTO repairs(
                    id,fingerprint,title,subsystem,recipe_json,confidence,
                    successful_runs,failed_runs,portable,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    fingerprint=excluded.fingerprint,
                    title=excluded.title,
                    subsystem=excluded.subsystem,
                    recipe_json=excluded.recipe_json,
                    confidence=excluded.confidence,
                    successful_runs=excluded.successful_runs,
                    failed_runs=excluded.failed_runs,
                    portable=excluded.portable,
                    updated_at=excluded.updated_at
                """,
                (
                    repair_id,
                    fingerprint,
                    title,
                    subsystem,
                    raw,
                    confidence,
                    successful_runs,
                    failed_runs,
                    portable,
                    now,
                ),
            )
            self.db.execute("DELETE FROM repair_search WHERE repair_id=?", (repair_id,))
            problem, symptoms, diagnosis, steps = self._search_text(recipe)
            self.db.execute(
                """INSERT INTO repair_search(
                    repair_id,title,subsystem,problem,symptoms,diagnosis,steps
                ) VALUES(?,?,?,?,?,?,?)""",
                (repair_id, title, subsystem, problem, symptoms, diagnosis, steps),
            )
            self.db.commit()
            return repair_id

    def search_repairs(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                """SELECT r.recipe_json
                FROM repair_search s
                JOIN repairs r ON r.id=s.repair_id
                WHERE repair_search MATCH ?
                ORDER BY bm25(repair_search), r.confidence DESC, r.updated_at DESC
                LIMIT ?""",
                (query, int(limit)),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def status(self):
        with self.lock:
            return {
                "facts": self.db.execute("SELECT count(*) FROM facts").fetchone()[0],
                "observations": self.db.execute("SELECT count(*) FROM observations").fetchone()[0],
                "repairs": self.db.execute("SELECT count(*) FROM repairs").fetchone()[0],
            }
