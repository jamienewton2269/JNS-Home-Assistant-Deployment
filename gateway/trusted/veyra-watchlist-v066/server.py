#!/usr/bin/env python3
"""VEYRA local watchlist beta v0.6.6: stdlib HTTP + SQLite, no programme media."""
from __future__ import annotations
import datetime as dt
import json
import os
import re
import sqlite3
import threading
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "0.6.6"
HOST, PORT = "127.0.0.1", 8772
DB = Path(os.environ.get("VEYRA_WATCHLIST_DB", "/var/lib/veyra/watchlist/watchlist.sqlite3"))
HERE = Path(__file__).resolve().parent
MAX_BODY = 8192
PROVIDERS = {"itvx": "ITVX", "iplayer": "BBC iPlayer", "channel4": "Channel 4",
             "netflix": "Netflix", "primevideo": "Prime Video", "disney": "Disney+",
             "other": "Other"}
DB_LOCK = threading.Lock()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def connect():
    c = sqlite3.connect(DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=5000")
    return c

def setup():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS watch_items (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, media_type TEXT NOT NULL,
            provider TEXT NOT NULL, provider_url TEXT NOT NULL DEFAULT '',
            season INTEGER, episode INTEGER, release_year INTEGER,
            status TEXT NOT NULL DEFAULT 'planned',
            progress INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
            catalogue_id TEXT NOT NULL DEFAULT '', watched_at TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS watch_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
            event_type TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
            occurred_at TEXT NOT NULL,
            FOREIGN KEY(item_id) REFERENCES watch_items(id))""")
        c.execute("CREATE INDEX IF NOT EXISTS watch_items_updated ON watch_items(updated_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS watch_events_item ON watch_events(item_id,seq DESC)")

def fail(msg, status=400):
    raise ValueError(msg) if status == 400 else LookupError(msg)

def clip(value, name, maximum, required=False):
    if not isinstance(value, str):
        fail(name + " must be text")
    value = value.strip()
    if len(value) > maximum or (required and not value):
        fail(name + " length invalid")
    return value

def integer(value, label, maximum):
    if value is None or value == "":
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        fail(label + " out of range")
    return value

def validate(data, current=None):
    if not isinstance(data, dict):
        fail("Expected JSON object")
    allowed = {"title", "media_type", "provider", "provider_url", "season",
               "episode", "release_year", "progress", "note", "catalogue_id"}
    if any(k not in allowed for k in data):
        fail("Unexpected field (watched requires the explicit Complete action)")
    d = dict(current or {})
    d.update(data)
    d["title"] = clip(d.get("title", ""), "Title", 180, True)
    d["media_type"] = clip(d.get("media_type", "series"), "Type", 10)
    if d["media_type"] not in ("series", "film"):
        fail("Type must be series or film")
    d["provider"] = clip(d.get("provider", "other"), "Provider", 24)
    if d["provider"] not in PROVIDERS:
        fail("Unknown provider")
    d["provider_url"] = clip(d.get("provider_url", ""), "Provider link", 1200)
    if d["provider_url"]:
        u = urllib.parse.urlsplit(d["provider_url"])
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443):
            fail("Use an HTTPS provider URL without credentials")
    d["season"] = integer(d.get("season"), "Season", 200)
    d["episode"] = integer(d.get("episode"), "Episode", 1000)
    d["release_year"] = integer(d.get("release_year"), "Year", 2200)
    if d["media_type"] == "film":
        d["season"], d["episode"] = None, None
    d["note"] = clip(d.get("note", ""), "Notes", 800)
    d["catalogue_id"] = clip(d.get("catalogue_id", ""), "Catalogue id", 60)
    d["progress"] = integer(d.get("progress", 0), "Progress", 99)
    if d["progress"] is None:
        d["progress"] = 0
    return d

def log_event(c, item, event, detail=""):
    c.execute("INSERT INTO watch_events (item_id,event_type,detail,occurred_at) VALUES (?,?,?,?)",
              (item, event, detail, now()))

class API(BaseHTTPRequestHandler):
    server_version = "VeyraWatchlist/" + VERSION
    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)

    def cors_safe(self):
        host = self.headers.get("Host", "")
        if host not in ("127.0.0.1:8772", "localhost:8772"):
            self.error(403, "Localhost host required")
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in ("http://127.0.0.1:8772", "http://localhost:8772"):
            self.error(403, "Origin denied")
            return False
        return True

    def headers(self, code, media="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", media)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
            "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; "
            "img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()

    def send(self, code, obj):
        blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.headers(code)
        self.wfile.write(blob)

    def error(self, status, message):
        self.send(status, {"error": message})

    def do_GET(self):
        if not self.cors_safe():
            return
        u = urllib.parse.urlsplit(self.path)
        if u.path in ("/", "/index.html", "/app.js", "/app.css"):
            name = {"/":"index.html", "/index.html":"index.html",
                    "/app.js":"app.js", "/app.css":"app.css"}[u.path]
            typ = "text/html; charset=utf-8" if name.endswith("html") else (
                "application/javascript; charset=utf-8" if name.endswith("js") else "text/css; charset=utf-8")
            try:
                b = (HERE/name).read_bytes()
            except OSError:
                return self.error(500, "UI asset missing")
            self.headers(200, typ)
            self.wfile.write(b)
            return
        if u.path == "/api/health":
            return self.send(200, {"ok":True, "version":VERSION, "data":"SQLite local", "automatic_watched_detection":False})
        if u.path == "/api/items":
            with connect() as c:
                items = [dict(r) for r in c.execute(
                    "SELECT * FROM watch_items WHERE archived=0 ORDER BY updated_at DESC LIMIT 1000")]
            return self.send(200, {"items":items})
        m = re.fullmatch(r"/api/items/([a-f0-9-]{36})/history", u.path)
        if m:
            with connect() as c:
                events = [dict(r) for r in c.execute(
                    "SELECT event_type,detail,occurred_at FROM watch_events WHERE item_id=? ORDER BY seq DESC LIMIT 100",
                    (m.group(1),))]
            return self.send(200, {"events":events})
        if u.path == "/api/search":
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0].strip()
            if not 2 <= len(q) <= 75:
                return self.error(400, "Search between 2 and 75 characters")
            try:
                url = "https://api.tvmaze.com/search/shows?q=" + urllib.parse.quote(q)
                req = urllib.request.Request(url, headers={"User-Agent":"VEYRA-local-watchlist/0.6.6"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    raw = r.read(350000)
                rows = json.loads(raw)
                result = []
                for row in rows[:10]:
                    show = row.get("show") or {}
                    name = show.get("name")
                    if not isinstance(name, str):
                        continue
                    result.append({"title": name[:180],
                        "year": int(show["premiered"][:4]) if re.match(r"^\d{4}",show.get("premiered") or "") else None,
                        "catalogue_id":str(show.get("id",""))[:60]})
                return self.send(200, {"suggestions":result, "provider_availability_verified":False})
            except Exception:
                return self.send(200, {"suggestions":[], "provider_availability_verified":False,
                                       "notice":"Catalogue unavailable; manual entry works"})
        return self.error(404, "Not found")

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            fail("Content-Type must be application/json")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            fail("Invalid size")
        if not 0 < size <= MAX_BODY:
            fail("Request too large or empty")
        try:
            return json.loads(self.rfile.read(size))
        except (ValueError,UnicodeDecodeError):
            fail("Invalid JSON")

    def write(self, method):
        if not self.cors_safe():
            return
        try:
            data = self.read_json()
            p = urllib.parse.urlsplit(self.path).path
            with DB_LOCK, connect() as c:
                if method == "POST" and p == "/api/items":
                    item = validate(data)
                    item_id = str(uuid.uuid4())
                    date = now()
                    c.execute("""INSERT INTO watch_items
                        (id,title,media_type,provider,provider_url,season,episode,release_year,
                         status,progress,note,catalogue_id,created_at,updated_at)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (item_id,item["title"],item["media_type"],item["provider"],
                         item["provider_url"],item["season"],item["episode"],item["release_year"],
                         "watching" if item["progress"] else "planned", item["progress"],
                         item["note"],item["catalogue_id"],date,date))
                    log_event(c,item_id,"added","Manually added")
                    return self.send(201, {"id":item_id, "status":"created"})
                m = re.fullmatch(r"/api/items/([a-f0-9-]{36})(?:/(complete|archive))?", p)
                if not m:
                    return self.error(404,"Not found")
                ident, action = m.groups()
                row = c.execute("SELECT * FROM watch_items WHERE id=?", (ident,)).fetchone()
                if not row:
                    return self.error(404,"Item not found")
                if action == "complete" and method == "POST":
                    if not isinstance(data,dict) or data != {"confirmed":True}:
                        fail("Explicit completion confirmation required")
                    c.execute("UPDATE watch_items SET status='watched',progress=100,watched_at=?,updated_at=? WHERE id=?",
                              (now(),now(),ident))
                    log_event(c,ident,"complete","Manually confirmed, not provider verified")
                elif action == "archive" and method == "POST":
                    if not isinstance(data,dict) or data != {"confirmed":True}:
                        fail("Explicit archive confirmation required")
                    c.execute("UPDATE watch_items SET archived=1,updated_at=? WHERE id=?", (now(),ident))
                    log_event(c,ident,"archive","Archived, history retained")
                elif action is None and method == "PATCH":
                    if row["status"] == "watched":
                        fail("Completed item is read-only in beta; add another episode")
                    current = {key: row[key] for key in
                               ("title","media_type","provider","provider_url","season","episode",
                                "release_year","note","catalogue_id","progress")}
                    item = validate(data,current)
                    cols = list(item)
                    # All keys are controlled by the validator, not client SQL.
                    c.execute("UPDATE watch_items SET " + ",".join(k+"=?" for k in cols) +
                              ",status=?,updated_at=? WHERE id=?",
                              [item[k] for k in cols]+
                              ["watching" if item["progress"] else "planned",now(),ident])
                    log_event(c,ident,"edit","Updated or progress recorded")
                else:
                    return self.error(404,"Unknown action")
            return self.send(200, {"ok":True,"id":ident})
        except ValueError as e:
            return self.error(400,str(e))
        except Exception as e:
            print("Backend error:",type(e).__name__, str(e),flush=True)
            return self.error(500,"Internal server error")

    def do_POST(self): self.write("POST")
    def do_PATCH(self): self.write("PATCH")
    def do_OPTIONS(self): self.error(405,"Not allowed")

if __name__ == "__main__":
    setup()
    server = ThreadingHTTPServer((HOST,PORT),API)
    print("VEYRA WATCHLIST "+VERSION+" http://%s:%d DB=%s" % (HOST,PORT,DB),flush=True)
    server.serve_forever(poll_interval=.5)
