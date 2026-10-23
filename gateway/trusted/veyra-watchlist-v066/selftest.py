#!/usr/bin/env python3
"""Offline self-test for VEYRA watchlist v0.6.6. Uses a temporary DB and port."""
import http.client
import importlib.util
import json
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit
def run(stage):
    spec = importlib.util.spec_from_file_location("veyra_watchlist_test_server", stage/"server.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    with tempfile.TemporaryDirectory(prefix="veyra-watchlist-smoke-") as td:
        api.DB = Path(td)/"test.sqlite3"
        api.HERE = stage
        api.setup()
        s = api.ThreadingHTTPServer(("127.0.0.1", 0),api.API)
        s.daemon_threads = True
        thread = threading.Thread(target=s.serve_forever,daemon=True)
        thread.start()
        try:
            def call(method,path,obj=None,headers=None):
                c = http.client.HTTPConnection("127.0.0.1",s.server_port,timeout=5)
                h = {"Host":"127.0.0.1:8772","Origin":"http://127.0.0.1:8772"}
                if headers: h.update(headers)
                if obj is not None:
                    h["Content-Type"]="application/json"
                    payload=json.dumps(obj)
                else:
                    payload=None
                c.request(method,path,payload,h)
                r=c.getresponse()
                blob=r.read()
                t=r.getheader("Content-Type","")
                c.close()
                return r.status,json.loads(blob) if "application/json" in t else blob
            def expect(code,status,label):
                assert code==status,f"{label} expected {status} got {code}"
            code,res=call("GET","/api/health")
            expect(code,200,"health")
            assert res["ok"] and not res["automatic_watched_detection"]
            for path in ("/", "/app.js", "/app.css"):
                code,res=call("GET",path)
                expect(code,200,path)
                assert len(res)>500
            entry={"title":"Test programme", "media_type":"series","provider":"itvx",
                   "provider_url":"https://www.itv.com/watch/test","season":1,"episode":2,
                   "release_year":2026,"progress":0,"note":"Test only","catalogue_id":""}
            code,res=call("POST","/api/items",entry)
            expect(code,201,"add")
            id=res["id"]
            code,res=call("GET","/api/items")
            expect(code,200,"items")
            assert len(res["items"])==1
            assert res["items"][0]["title"]=="Test programme"
            code,res=call("PATCH","/api/items/"+id,{"progress":52})
            expect(code,200,"update progress")
            code,res=call("GET","/api/items")
            assert res["items"][0]["status"]=="watching" and res["items"][0]["progress"]==52
            code,res=call("POST","/api/items/"+id+"/complete",{"confirmed":False})
            expect(code,400,"reject unconfirmed watched")
            code,res=call("POST","/api/items/"+id+"/complete",{"confirmed":True})
            expect(code,200,"mark watched")
            code,res=call("GET","/api/items")
            assert res["items"][0]["status"]=="watched" and res["items"][0]["progress"]==100
            code,res=call("GET","/api/items/"+id+"/history")
            expect(code,200,"watch history")
            assert {e["event_type"] for e in res["events"]}>={"added","edit","complete"}
            code,res=call("PATCH","/api/items/"+id,{"title":"Tamper"})
            expect(code,400,"completed entry lock")
            bad=dict(entry,provider_url="javascript:alert(1)")
            code,res=call("POST","/api/items",bad)
            expect(code,400,"unsafe URL rejected")
            code,res=call("POST","/api/items",entry,{"Origin":"https://example.com"})
            expect(code,403,"external origin denied")
            code,res=call("POST","/api/items",entry,{"Host":"example.com"})
            expect(code,403,"DNS rebinding denied")
            code,res=call("POST","/api/items/"+id+"/archive",{"confirmed":True})
            expect(code,200,"archive")
            code,res=call("GET","/api/items")
            assert res["items"]==[]
            assert api.DB.exists()
            print("PASS: assets, local API, SQLite, progress, confirmed watched, history, archive, URL validation, Host and Origin protections.")
            print("PASS: test database was temporary; Veyra programme data untouched.")
        finally:
            s.shutdown()
            s.server_close()
            thread.join(timeout=3)
if __name__=="__main__":
    stage=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
    run(stage)
