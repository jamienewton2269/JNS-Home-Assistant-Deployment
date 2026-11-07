"""Private Club Manager beta, localhost ONLY; deliberately no public listener.

Requires exact CLUB_BETA_ORIGIN=https://approved-private-hostname, peer-mapped
PostgreSQL clubbeta role and an independently approved synthetic officer key.
The TLS reverse proxy must NOT expose this port directly.
"""
import json
import os
import sys
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit
from uuid import UUID

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "auth"))
from webauthn_flow import WebAuthnFlow
from pg_webauthn_store import PostgreSQLWebAuthnStore
from officer_controller import OfficerController
from read_api import ReadOnlyBetaAPI, READ_ROUTES

MAX_BODY = 16384
ASSETS = {"/login": ("login.html", "text/html"), "/assets/style.css": ("style.css", "text/css"),
          "/assets/browser.js": ("browser.js", "text/javascript"), "/beta": ("beta.html", "text/html")}

def validate_origin(origin):
    p = urlsplit(origin)
    if (p.scheme != "https" or not p.hostname or p.hostname in ("localhost", "127.0.0.1")
        or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment
        or p.port not in (None, 443)):
        raise ValueError("Exact approved private HTTPS origin is required")
    return p.hostname.lower(), "https://" + p.hostname.lower()

class Handler(BaseHTTPRequestHandler):
    controller = None
    expected_host = None
    expected_origin = None

    def log_message(self, fmt, *args):
        # Never log incoming URLs, identifiers, cookies or authentication data.
        pass

    def send_body(self, status, payload, mime="application/json", cookie=None):
        data = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def deny(self, status, message):
        self.send_body(status, {"error":message})

    def host_ok(self):
        return self.headers.get("Host","") == self.expected_host

    def do_GET(self):
        if self.path == "/healthz":
            self.send_body(200, {"status":"ok","environment":"private-synthetic-beta","bind":"loopback"})
            return
        if not self.host_ok():
            return self.deny(421, "Unexpected host")
        if self.path in ASSETS:
            if self.path == "/beta":
                try:
                    self.controller.read("/api/v1/dashboard", self.headers.get("Cookie",""))
                except Exception:
                    self.send_response(303)
                    self.send_header("Location","/login")
                    self.send_header("Cache-Control","no-store")
                    self.end_headers()
                    return
            filename, mime = ASSETS[self.path]
            try:
                content = (HERE / "static" / filename).read_text(encoding="utf-8")
                return self.send_body(200, content, mime)
            except OSError:
                return self.deny(503, "Asset unavailable")
        if self.path not in READ_ROUTES:
            return self.deny(404, "Unknown route")
        try:
            data = self.controller.read(self.path, self.headers.get("Cookie",""))
            return self.send_body(200, data)
        except PermissionError:
            return self.deny(401, "Named officer passkey session required")
        except Exception as exc:
            if getattr(exc, "pgcode", None) == "42501":
                return self.deny(403, "Permission denied")
            return self.deny(503, "Read unavailable")

    def do_POST(self):
        if not self.host_ok() or self.headers.get("Origin") != self.expected_origin:
            return self.deny(403, "Browser origin rejected")
        if self.path not in ("/auth/webauthn/begin", "/auth/webauthn/complete", "/auth/logout"):
            return self.deny(404, "Unknown operation")
        if self.headers.get("Content-Type","").split(";")[0].strip().lower() != "application/json":
            return self.deny(415, "JSON required")
        try:
            count = int(self.headers.get("Content-Length","0"))
            if not 2 <= count <= MAX_BODY:
                raise ValueError("Bad size")
            body = json.loads(self.rfile.read(count).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("Bad format")
            if self.path == "/auth/logout":
                cleared = self.controller.logout(self.headers.get("Cookie",""))
                return self.send_body(200, {"signed_out":True}, cookie=cleared)
            officer_id = UUID(body["officer_id"])
            if self.path.endswith("/begin"):
                cid, options = self.controller.begin_passkey(officer_id)
                return self.send_body(200, {"challenge_id":str(cid),"options":json.loads(options)})
            cid = UUID(body["challenge_id"])
            if not isinstance(body["response"],dict):
                raise ValueError("Bad assertion")
            cookie = self.controller.complete_passkey(officer_id,cid,body["response"])
            return self.send_body(200, {"authenticated":True,"expires_in_seconds":900},cookie=cookie)
        except (ValueError, KeyError, TypeError, PermissionError):
            return self.deny(403, "Passkey authentication unavailable")
        except Exception:
            return self.deny(503, "Authentication unavailable")

    def do_PUT(self):
        self.deny(405, "Read-only beta")
    def do_DELETE(self):
        self.deny(405, "Read-only beta")
    def do_PATCH(self):
        self.deny(405, "Read-only beta")

def main():
    origin = os.environ["CLUB_BETA_ORIGIN"]
    rp, canonical = validate_origin(origin)
    import psycopg2
    # Peer authentication is required. The legacy clubmgr role is never used.
    db = lambda: psycopg2.connect("dbname=club_manager user=clubbeta")
    Handler.controller = OfficerController(WebAuthnFlow(rp, canonical, PostgreSQLWebAuthnStore(db)),
                                            db, ReadOnlyBetaAPI(db))
    Handler.expected_host = rp
    Handler.expected_origin = canonical
    ThreadingHTTPServer(("127.0.0.1",8766), Handler).serve_forever()

if __name__ == "__main__":
    main()
