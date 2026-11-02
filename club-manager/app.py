#!/usr/bin/env python3
"""JNS Club Manager development prototype. Synthetic records only.
Localhost-bound service; NOT a production security or GDPR implementation.
"""
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import psycopg2

SECRET_FILE = "/etc/jns-club-manager/admin.secret"
with open(SECRET_FILE, encoding="utf-8") as f:
    ADMIN_SECRET = f.read().strip()
DB = "dbname=club_manager user=clubmgr"
TITLE = "JNS Club Manager — Development"

def esc(s):
    return html.escape(str(s), quote=True)

def db():
    return psycopg2.connect(DB)

def audit_verified():
    with db() as cn, cn.cursor() as cur:
        cur.execute("SELECT seq, entry_hash, prev_hash, member_id, action, payload, actor FROM club.audit_rows()")
        previous = "0" * 64
        count = 0
        for seq, digest, prev, member, action, payload, actor in cur:
            if prev != previous:
                return False, count
            # The database builds this digest from the same canonical fields.
            computed = hashlib.sha256(f"{prev}|{seq}|{member}|{action}|{payload}|{actor}".encode()).hexdigest()
            if not hmac.compare_digest(computed, digest):
                return False, count
            previous = digest
            count += 1
        return True, count

class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(hdr[6:], validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        username, sep, password = raw.partition(":")
        return bool(sep) and username == "admin" and hmac.compare_digest(password, ADMIN_SECRET)

    def reject(self, code, message):
        self.send_response(code)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if code == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="Club Manager Development"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(message.encode())

    def respond(self, body, status=200, mime="text/html"):
        body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            try:
                with db() as cn, cn.cursor() as cur:
                    cur.execute("SELECT 1")
                    assert cur.fetchone()[0] == 1
                self.respond('{"status":"ok","environment":"development"}', mime="application/json")
            except Exception:
                self.reject(503, "unhealthy")
            return
        if not self.authorized():
            self.reject(401, "Authentication required")
            return
        if self.path == "/admin/accounts":
            with db() as cn, cn.cursor() as cur:
                cur.execute("SELECT id,display_name,email,account_state,roles,permissions FROM club.list_committee_accounts()")
                accounts=cur.fetchall()
            rows="".join("<tr><td>"+esc(a[1])+"</td><td>"+esc(a[2])+"</td><td>"+esc(a[3])+"</td><td>"+esc(", ".join(a[4]) or "None")+"</td><td>"+esc(", ".join(a[5]) or "None")+"</td></tr>" for a in accounts)
            self.respond("""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Committee Access — Development</title><style>
            body{background:#101d30;color:#e8f1f5;font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}
            section{background:#1a3047;border:1px solid #425f70;border-radius:12px;padding:1.2rem;margin:1rem 0}
            input,button{padding:.7rem;border-radius:6px;margin:.3rem}label{display:inline-block}
            table{width:100%;border-collapse:collapse}td,th{padding:.7rem;border-bottom:1px solid #456;text-align:left}
            a{color:#92e5ef}.muted{color:#abc2d1}</style>
            <h1>General Committee · Accounts &amp; Access</h1><p><a href="/admin">Administration</a></p>
            <section><h2>Create committee account</h2>
            <p class="muted">Default: disabled · no roles · no permissions · cannot sign in.</p>
            <form method="post" action="/admin/accounts">
            <label>Name <input name="name" maxlength="120" required></label>
            <label>Email <input name="email" type="email" maxlength="254" required></label>
            <button type="submit">Create disabled account</button></form></section>
            <section><h2>Existing accounts</h2><table><thead><tr><th>Name</th><th>Email</th><th>State</th><th>Roles</th><th>Permissions</th></tr></thead><tbody>"""+rows+"""</tbody></table></section>
            <section><h2>Permission management</h2><p>Role and permission grants require separately authenticated, independent approval.
            They are intentionally unavailable in this development interface. Creating an account never grants access.</p>
            <p>Available roles: Membership Secretary, Treasurer, Commodore / Committee, System Administrator.</p>
            </section><p class="muted">Synthetic-data-only development interface. Do not enter real committee member details.</p></html>""")
            return
        if self.path == "/admin":
            with db() as cn, cn.cursor() as cur:
                cur.execute("SELECT club.admin_snapshot()")
                snapshot = cur.fetchone()[0]
            categories = "".join(
                f"<tr><td>{esc(x['category'])}</td><td>£{x['annual_pence']/100:.2f}</td><td>£{x['joining_pence']/100:.2f}</td></tr>"
                for x in snapshot["member_tariffs"])
            yard_rates = "".join(
                f"<tr><td>{esc(x['year'])}</td><td>{esc(x['asset_type'])}</td><td>{esc(x['basis'])}</td><td>£{x['pence_per_unit']/100:.2f}</td></tr>"
                for x in snapshot["yard_tariffs"]) or "<tr><td colspan='4'>No approved yard tariffs entered</td></tr>"
            html_body = f"""<!doctype html><html lang="en"><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Private Club Administration (Development)</title>
            <style>body{{background:#0d1727;color:#e2edf4;font:16px system-ui;max-width:1050px;margin:2rem auto;padding:0 1rem}}
            table{{border-collapse:collapse;width:100%;margin-bottom:1.5rem}}td,th{{padding:.7rem;border-bottom:1px solid #456;text-align:left}}
            section{{border:1px solid #456;border-radius:10px;padding:1rem;margin:1rem 0}}a{{color:#8df}}</style>
            <h1>Club Manager · Private Administration</h1>
            <p>Development preview · synthetic records only · <a href="/">Member register</a> · <a href="/audit">Audit</a> · <a href="/admin/accounts">Committee accounts</a></p>
            <section><h2>Operational diary</h2>
            <p>Yard assets: {snapshot['yard_assets']} · Approved mooring bookings: {snapshot['approved_mooring_bookings']}</p>
            <p>Pending mooring requests: {snapshot['pending_mooring_requests']} · Pending clubhouse requests: {snapshot['pending_facility_requests']}</p>
            <p>Bookings are controlled by database exclusion constraints. Officer approval workflows are not enabled in this preview.</p></section>
            <section><h2>Approved membership fees</h2>
            <table><tr><th>Category</th><th>Annual</th><th>Joining</th></tr>{categories}</table></section>
            <section><h2>Yard and trailer rates</h2>
            <table><tr><th>Year</th><th>Asset</th><th>Unit</th><th>Rate</th></tr>{yard_rates}</table>
            <p>Charges use measured length in metres or feet, including stored yard trailers. There is no seasonal or amenity-mooring waiver.</p></section>
            <p>No live finance operations or public access are enabled.</p></html>"""
            self.respond(html_body)
            return
        if self.path == "/audit":
            ok, count = audit_verified()
            self.respond(json.dumps({"chain_verified":ok,"events":count,"note":"local database checks only; not independently immutable"}), mime="application/json")
            return
        if self.path == "/":
            with db() as cn, cn.cursor() as cur:
                cur.execute("SELECT member_id,display_name,email,category,version FROM club.current_members ORDER BY display_name LIMIT 100")
                rows = cur.fetchall()
            table = "".join(f"<tr><td>{esc(mid)}</td><td>{esc(name)}</td><td>{esc(email)}</td><td>{esc(cat)}</td><td>{version}</td></tr>" for mid,name,email,cat,version in rows)
            body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
            <title>{TITLE}</title><style>body{{background:#0d1727;color:#dce7ee;font:16px system-ui;margin:3rem auto;max-width:1100px;padding:0 1rem}}
            h1{{color:#77d6db}}.panel{{background:#182940;padding:1.2rem;margin:1rem 0;border:1px solid #35516b;border-radius:12px}}
            table{{width:100%;border-collapse:collapse;overflow-wrap:anywhere}}td,th{{text-align:left;padding:.7rem;border-bottom:1px solid #35516b}}
            input,select,button{{padding:.55rem;margin:.3rem;background:#f3f9fb;color:#122235;border:0;border-radius:5px}}
            label{{display:inline-block}}small{{color:#a6b7c5}}a{{color:#7edce4}}</style>
            <h1>JNS Club Manager</h1><p>Offline-master development prototype · Synthetic data only</p>
            <section class="panel"><h2>Membership records ({len(rows)})</h2><table><thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Category</th><th>Version</th></tr></thead><tbody>{table}</tbody></table></section>
            <section class="panel"><h2>Add or revise a test member</h2>
            <form method="post" action="/member"><label>Member ID (blank for new) <input name="member_id" maxlength="36"></label>
            <label>Name <input name="name" required maxlength="120"></label><label>Email <input name="email" type="email" required maxlength="200"></label>
            <label>Category <select name="category"><option>Full</option><option>Family</option><option>Junior</option><option>Social</option></select></label>
            <button type="submit">Save new version</button></form><small>Each change is appended; previous versions remain in the event ledger. Testing only.</small></section>
            <section class="panel"><h2>Looking Glass</h2><p><a href="/audit">Verify local event hash chain</a></p>
            <small>This is not independent immutable evidence, a GDPR engine or a public deployment. No real member data permitted.</small></section></html>"""
            self.respond(body)
            return
        self.reject(404, "Not found")

    def do_POST(self):
        if not self.authorized():
            self.reject(401, "Authentication required")
            return
        if self.path not in ("/member", "/admin/accounts"):
            self.reject(404, "Not found")
            return
        # Only loopback clients can reach this service. Require browser Origin to match.
        origin = self.headers.get("Origin")
        if origin not in ("http://127.0.0.1:8765", "http://localhost:8765"):
            self.reject(403, "Invalid origin")
            return
        if self.path == "/admin/accounts":
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 1<=n<=2048:
                    raise ValueError("Invalid input size")
                form=urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"),keep_blank_values=True)
                name=form.get("name",[""])[0].strip()
                email=form.get("email",[""])[0].strip()
                with db() as cn, cn.cursor() as cur:
                    cur.execute("SELECT club.create_disabled_committee_account(%s,%s,%s)",(name,email,"local-dev-admin"))
                self.send_response(303)
                self.send_header("Location","/admin/accounts")
                self.send_header("Cache-Control","no-store")
                self.end_headers()
            except (ValueError,psycopg2.Error):
                self.reject(400,"Invalid or duplicate account. No access granted.")
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n < 1 or n > 4096:
                raise ValueError("invalid length")
            form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"), keep_blank_values=True)
            def field(k):
                return form.get(k, [""])[0].strip()
            mid, name, email, category = (field(k) for k in ("member_id","name","email","category"))
            if not name or not email or "@" not in email or len(name)>120 or len(email)>200 or category not in ("Full","Family","Junior","Social"):
                raise ValueError("invalid record")
            if mid and (len(mid)!=36 or not all(x in "0123456789abcdef-" for x in mid.lower())):
                raise ValueError("invalid member id")
            if not mid:
                import uuid
                mid = str(uuid.uuid4())
            with db() as cn, cn.cursor() as cur:
                cur.execute("SELECT club.append_member(%s,%s,%s,%s,%s)",(mid,name,email,category,"local-dev-admin"))
            self.send_response(303)
            self.send_header("Location","/")
            self.send_header("Cache-Control","no-store")
            self.end_headers()
        except (ValueError, psycopg2.Error):
            self.reject(400, "Invalid member record or database rejected change")

if __name__ == "__main__":
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    server.serve_forever()
