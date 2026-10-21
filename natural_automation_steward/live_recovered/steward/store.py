import json, sqlite3, time, threading
from pathlib import Path

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
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(self.path,check_same_thread=False)
        self.db.execute("PRAGMA busy_timeout=3000")
        self.db.executescript(SCHEMA)
    def set_fact(self,namespace,key,value):
        with self.lock:
            self.db.execute("""INSERT INTO facts(namespace,key,value_json,updated_at)
          VALUES(?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET
          value_json=excluded.value_json,updated_at=excluded.updated_at""",
          (namespace,key,json.dumps(value,sort_keys=True),time.time()))
            self.db.commit()
    def observe(self,kind,source,payload):
        with self.lock:
            self.db.execute("INSERT INTO observations(ts,kind,source,payload_json) VALUES(?,?,?,?)",
          (time.time(),kind,source,json.dumps(payload,sort_keys=True)))
            self.db.commit()
    def status(self):
        with self.lock:
            return {
          "facts":self.db.execute("SELECT count(*) FROM facts").fetchone()[0],
          "observations":self.db.execute("SELECT count(*) FROM observations").fetchone()[0],
          "repairs":self.db.execute("SELECT count(*) FROM repairs").fetchone()[0],
        }
