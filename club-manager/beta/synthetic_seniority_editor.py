#!/usr/bin/env python3
"""Isolated, loopback-only CRUD acceptance UI for synthetic member seniority records.
Never connect this test application to CT101 or a real membership database.
Requires python3-psycopg2 and a disposable PostgreSQL database with migrations.
"""
import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
import psycopg2

DSN = os.environ.get("BSC_SYNTHETIC_DSN", "")
TOKEN = os.environ.get("BSC_SYNTHETIC_TOKEN", "")
if not DSN or len(TOKEN) < 24 or "club_manager" in DSN.lower():
    raise SystemExit("Set BSC_SYNTHETIC_DSN for a disposable database and a >=24-character BSC_SYNTHETIC_TOKEN")
def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def respond(self, code, text):
        data=text.encode()
        self.send_response(code)
        for k,v in {"Content-Type":"text/html; charset=utf-8","Content-Length":str(len(data)),
                    "Cache-Control":"no-store","X-Content-Type-Options":"nosniff",
                    "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"}.items():
            self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def authorized(self):
        return self.headers.get("Authorization","") == "Bearer "+TOKEN
    def do_GET(self):
        if self.path!="/" or not self.authorized():return self.respond(403,"Access denied")
        with psycopg2.connect(DSN) as db:
            with db.cursor() as c:
                c.execute("""SELECT m.id,m.joined_on,m.category,m.status,s.seniority_suspended
                FROM club.member_profiles m JOIN club.member_mooring_seniority s ON s.member_id=m.id
                ORDER BY m.joined_on NULLS LAST,m.id LIMIT 200""")
                members=c.fetchall()
                c.execute("SELECT id,title,held_on FROM club.working_parties ORDER BY held_on DESC LIMIT 50")
                parties=c.fetchall()
                c.execute("""SELECT a.member_id,p.title,a.status,a.recorded_at FROM club.working_party_attendance a
                JOIN club.working_parties p ON p.id=a.party_id ORDER BY a.recorded_at DESC LIMIT 50""")
                attendance=c.fetchall()
        body="<h1>BSC synthetic membership administration</h1><p>Isolated test database only. No real member records.</p>"
        body+="<h2>Members and seniority</h2><table border=1><tr><th>Member UUID</th><th>Joined</th><th>Category</th><th>Status</th><th>Seniority suspended</th></tr>"
        for row in members:body+="<tr>"+"".join("<td>"+esc(v)+"</td>" for v in row)+"</tr>"
        body+="</table><h2>Update joining date</h2><form method=post action=/join><input name=member_id placeholder='Member UUID' required><input type=date name=joined_on required><button>Save</button></form>"
        body+="<h2>Working party</h2><form method=post action=/party><input name=title placeholder=Title required><input type=date name=held_on required><button>Create</button></form>"
        body+="<ul>"+"".join("<li>"+esc(p[0])+" — "+esc(p[1])+" — "+esc(p[2])+"</li>" for p in parties)+"</ul>"
        body+="<h2>Record attendance</h2><form method=post action=/attendance><input name=party_id placeholder='Party UUID' required><input name=member_id placeholder='Member UUID' required><select name=status><option>attended</option><option>excused</option><option>absent</option><option>declined</option></select><input name=recorded_by placeholder='Synthetic officer' required><button>Record</button></form>"
        body+="<ul>"+"".join("<li>"+esc(x)+"</li>" for x in attendance)+"</ul>"
        body+="<h2>Seniority decision</h2><form method=post action=/decision><input name=member_id placeholder='Member UUID' required><select name=decision><option>suspend</option><option>reinstate</option></select><input type=date name=effective_from required><input type=date name=effective_until><input name=reason placeholder=Reason required><input name=authorised_by placeholder='Synthetic officer' required><button>Record decision</button></form>"
        self.respond(200,"<!doctype html><html lang=en><meta charset=utf-8><title>BSC Synthetic Test</title><body>"+body+"</body></html>")
    def do_POST(self):
        # A local synthetic test tool, not an officer-authenticated production API.
        if not self.authorized() or self.headers.get("Origin") or self.headers.get("Sec-Fetch-Site") not in (None,"same-origin"):
            return self.respond(403,"Access denied")
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=4096:raise ValueError("Invalid request length")
            form=parse_qs(self.rfile.read(n).decode(),strict_parsing=True)
            def val(k):return form.get(k,[""])[0].strip()
            with psycopg2.connect(DSN) as db:
                with db.cursor() as c:
                    if self.path=="/join":
                        c.execute("UPDATE club.member_profiles SET joined_on=%s WHERE id=%s::uuid",(val("joined_on"),val("member_id")))
                        if c.rowcount!=1:raise ValueError("Member not found")
                    elif self.path=="/party":
                        c.execute("INSERT INTO club.working_parties(title,held_on) VALUES(%s,%s)",(val("title"),val("held_on")))
                    elif self.path=="/attendance":
                        c.execute("""INSERT INTO club.working_party_attendance(party_id,member_id,status,recorded_by)
                        VALUES(%s::uuid,%s::uuid,%s,%s)""",(val("party_id"),val("member_id"),val("status"),val("recorded_by")))
                    elif self.path=="/decision":
                        c.execute("""INSERT INTO club.seniority_decisions(member_id,decision,effective_from,effective_until,reason,authorised_by)
                        VALUES(%s::uuid,%s,%s,NULLIF(%s,'')::date,%s,%s)""",
                        (val("member_id"),val("decision"),val("effective_from"),val("effective_until"),val("reason"),val("authorised_by")))
                    else: return self.respond(404,"Unknown operation")
            self.send_response(303);self.send_header("Location","/");self.end_headers()
        except (ValueError,psycopg2.Error) as e:
            self.respond(400,"Invalid synthetic test operation; check record IDs, dates and database permissions")
if __name__=="__main__":
    print("Synthetic CRUD UI listening on 127.0.0.1:8877; requires Authorization bearer token")
    ThreadingHTTPServer(("127.0.0.1",8877),Handler).serve_forever()
