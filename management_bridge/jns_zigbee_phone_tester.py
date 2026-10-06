#!/usr/bin/env python3
"""
JNS Zigbee Phone Walk-Round Tester

Purpose
-------
Provides a simple, touch-friendly LAN web interface for physically verifying
Zigbee lighting after migration/recovery.

Workflow
--------
1. The page names the NEXT lamp/socket/lighting relay before anything is changed.
2. Tap "Start this device"; only that device is commanded ON.
3. The page waits indefinitely while you walk to the physical unit.
4. "Working" or "Not working" first commands the device OFF, records the result,
   then advances to the next device.
5. "Test again" repeats the same device without advancing.
6. "Skip" turns the current candidate OFF, records it as skipped, and advances.
7. "ALL OFF" is always available.

Safety
------
- The web app cannot submit arbitrary shell or MQTT commands.
- Device IEEE addresses come from this fixed internal list.
- State changes go through jns-zigbee-device-control.sh, whose own allow-list
  accepts only ON/OFF for approved lighting candidates.
- No permit-join, reset, remove, re-pair, interview, PAN or coordinator changes.
- Intended for trusted LAN use only; do not expose port 8091 to the Internet.

Run location
------------
Node C, normally managed as systemd unit jns-zigbee-phone-tester.service.

Documentation catalogue description
-----------------------------------
"Phone-friendly interactive Zigbee walk-round tester. Shows the next named
lamp/socket before testing, waits for manual Working/Not working confirmation,
records results, supports retest/skip and provides an emergency ALL OFF button."
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import subprocess
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

BIND = os.environ.get("JNS_ZIGBEE_WEB_BIND", "10.10.10.236")
PORT = int(os.environ.get("JNS_ZIGBEE_WEB_PORT", "8091"))
CONTROL = os.environ.get("JNS_ZIGBEE_CONTROL", "/usr/local/sbin/jns-zigbee-device-control.sh")
STATE_DIR = "/var/lib/jns-zigbee-phone-tester"
RESULTS_FILE = os.path.join(STATE_DIR, "results.json")
CSRF = secrets.token_urlsafe(24)
LOCK = threading.Lock()

DEVICES = [
    {"name":"Tripod colour bulb", "ieee":"0x003c84fffe1a695c", "type":"IKEA bulb", "note":"Historical name: Tripod"},
    {"name":"Front Door bulb", "ieee":"0x5c0272fffe400903", "type":"IKEA bulb", "note":"Confirmed priority fault"},
    {"name":"Hallway bulb", "ieee":"0x847127fffe2890a6", "type":"IKEA bulb", "note":"Confirmed priority fault"},
    {"name":"Living Room pendant", "ieee":"0x847127fffe28965b", "type":"IKEA bulb", "note":"Confirmed priority fault"},
    {"name":"Treehouse lamp candidate", "ieee":"0x84fd27fffe2bd920", "type":"IKEA bulb", "note":"Old registry called this Downstairs Toilet; physical location needs confirmation"},
    {"name":"Treehouse door light candidate", "ieee":"0x84fd27fffe6e0543", "type":"IKEA socket", "note":"Old registry name: Door; strong candidate for the treehouse door light"},
    {"name":"Snug corner light", "ieee":"0x84fd27fffe7040c9", "type":"IKEA socket", "note":"Witnessed working"},
    {"name":"Garage security light", "ieee":"0x84fd27fffe9ce438", "type":"IKEA socket", "note":"External/security-light candidate"},
    {"name":"Kitchen worktop", "ieee":"0x84fd27fffe9f52a4", "type":"IKEA socket", "note":"Witnessed working"},
    {"name":"Bathroom lighting relay candidate", "ieee":"0xa4c13814ea8c8452", "type":"Zigbee mains relay", "note":"Historical Bathroom1"},
    {"name":"Garage interior lights", "ieee":"0xa4c1382aab02d3bf", "type":"Zigbee mains relay", "note":"Check garage interior"},
    {"name":"Summerhouse wall lights", "ieee":"0xa4c13837acc3862a", "type":"Zigbee mains relay", "note":"Historical Summerhouse exterior lights"},
    {"name":"Downstairs WC light relay", "ieee":"0xa4c13837e231806e", "type":"Zigbee/Tuya-family mains relay", "note":"Physical WC light was witnessed working"},
    {"name":"Treehouse lamp / AwoX candidate", "ieee":"0xa4c13839b8995fbd", "type":"AwoX Zigbee bulb", "note":"Physical location needs confirmation"},
    {"name":"Garage wall lights", "ieee":"0xa4c138807ef50f3c", "type":"Zigbee mains relay", "note":"Check garage wall lights"},
    {"name":"Kitchen radiator light", "ieee":"0xa4c13888eb407dfa", "type":"Zigbee/Tuya-family mains relay", "note":"Witnessed working"},
    {"name":"Street lamp / external light", "ieee":"0xa4c1388ba234f2e3", "type":"Zigbee mains relay", "note":"Historical Street lamp"},
    {"name":"Front / dogs-run security light candidate", "ieee":"0xa4c138bda6ec8ea0", "type":"Zigbee mains relay", "note":"Check front security / dogs-run light"},
]

os.makedirs(STATE_DIR, exist_ok=True)

def load_results():
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}

def save_results(data):
    tmp = RESULTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, RESULTS_FILE)

def run_control(*args):
    p = subprocess.run([CONTROL, *args], text=True, capture_output=True, timeout=15)
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "controller failed").strip()
        raise RuntimeError(detail[-1000:])
    return (p.stdout or "").strip()

def now():
    return datetime.now(timezone.utc).isoformat()

def next_unclassified(results, after=-1):
    for i in range(after + 1, len(DEVICES)):
        if DEVICES[i]["ieee"] not in results:
            return i
    for i in range(0, after + 1):
        if DEVICES[i]["ieee"] not in results:
            return i
    return min(max(after + 1, 0), len(DEVICES) - 1) if DEVICES else 0

HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>JNS Zigbee Walk-Round Tester</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color-scheme:dark}
body{margin:0;background:#101317;color:#eef2f6}
main{max-width:720px;margin:auto;padding:16px}
h1{font-size:1.45rem;margin:.25rem 0 1rem}
.card{background:#1a2027;border:1px solid #35404c;border-radius:16px;padding:18px;margin:12px 0}
.kicker{font-size:.85rem;color:#9fb0c1;text-transform:uppercase;letter-spacing:.08em}
#name{font-size:1.8rem;font-weight:750;margin:.25rem 0}
.meta{color:#b8c5d1;line-height:1.45}
.note{margin-top:10px;padding:10px;border-radius:10px;background:#222b35}
.progress{font-weight:650}
button{width:100%;min-height:58px;margin:6px 0;border:0;border-radius:14px;font-size:1.05rem;font-weight:700;padding:12px}
.start{background:#d9e8ff;color:#07182d}
.good{background:#72d49a;color:#062515}
.bad{background:#ff8f8f;color:#351010}
.again{background:#e9c86b;color:#2b2205}
.skip{background:#8995a3;color:#101418}
.off{background:#ff5c5c;color:#210000}
.nav{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.small{min-height:48px;font-size:.95rem}
.status{min-height:1.5em;margin-top:10px;font-weight:650}
.on{color:#8eeaa9}.err{color:#ff9c9c}.muted{color:#96a5b4}
table{width:100%;border-collapse:collapse;font-size:.88rem}
td{padding:7px 4px;border-bottom:1px solid #303942;vertical-align:top}
.badge{font-weight:800}
footer{color:#81909e;font-size:.78rem;padding:14px 2px 30px}
</style>
</head>
<body><main>
<h1>JNS Zigbee Walk-Round Tester</h1>
<div class="card">
 <div class="progress" id="progress"></div>
 <div class="kicker">Next device to test</div>
 <div id="name">Loading...</div>
 <div class="meta" id="type"></div>
 <div class="meta" id="ieee"></div>
 <div class="note" id="note"></div>
 <div class="status muted" id="status">Nothing will switch until you tap Start this device.</div>
</div>

<div class="card">
 <button class="start" id="start">START THIS DEVICE - TURN ON</button>
 <button class="good" id="working">WORKING - TURN OFF &amp; NEXT</button>
 <button class="bad" id="failed">NOT WORKING - TURN OFF &amp; NEXT</button>
 <button class="again" id="again">TEST THIS DEVICE AGAIN</button>
 <button class="skip" id="skip">SKIP - TURN OFF &amp; NEXT</button>
 <button class="off" id="alloff">ALL TEST LIGHTS OFF</button>
 <div class="nav">
  <button class="skip small" id="prev">Previous</button>
  <button class="skip small" id="next">Next</button>
 </div>
</div>

<div class="card">
 <div class="kicker">Recorded results</div>
 <table id="results"></table>
</div>
<footer>LAN-only recovery tool. It does not reset, pair or remove Zigbee devices.</footer>
<script>
const CSRF="__CSRF__";
let state=null, index=0;

function esc(s){
 return String(s).replace(/[&<>"']/g,function(m){
   return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[m];
 });
}
async function api(action){
 const res=await fetch("/api/action",{
   method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({csrf:CSRF,action:action,index:index})
 });
 const data=await res.json();
 if(!res.ok) throw new Error(data.error||"request failed");
 return data;
}
async function refresh(prefer){
 const r=await fetch("/api/status");
 state=await r.json();
 if(Number.isInteger(prefer)) index=Math.max(0,Math.min(prefer,state.devices.length-1));
 else if(Number.isInteger(state.next_index)) index=state.next_index;
 render();
}
function render(){
 const d=state.devices[index], results=state.results||{};
 document.getElementById("progress").textContent="Device "+(index+1)+" of "+state.devices.length;
 document.getElementById("name").textContent=d.name;
 document.getElementById("type").textContent=d.type;
 document.getElementById("ieee").textContent=d.ieee;
 document.getElementById("note").textContent=d.note||"";
 let rows="";
 state.devices.forEach(function(x){
   const r=results[x.ieee];
   if(!r) return;
   const label=r.status==="working"?"Working":(r.status==="not_working"?"Not working":"Skipped");
   rows += "<tr><td>"+esc(x.name)+"</td><td class='badge'>"+esc(label)+"</td></tr>";
 });
 document.getElementById("results").innerHTML=rows||"<tr><td class='muted'>No confirmations recorded yet.</td></tr>";
}
async function act(a){
 const st=document.getElementById("status");
 st.className="status";
 st.textContent="Sending command...";
 Array.from(document.querySelectorAll("button")).forEach(function(b){b.disabled=true});
 try{
   const data=await api(a);
   if(a==="start"||a==="retest"){
     st.className="status on";
     st.textContent="Device commanded ON. Walk to it, then confirm below.";
     await refresh(index);
   }else if(a==="all_off"){
     st.className="status";
     st.textContent="ALL OFF command sent.";
     await refresh(index);
   }else{
     st.className="status";
     st.textContent="Result recorded. Next device ready.";
     await refresh(data.next_index);
   }
 }catch(e){
   st.className="status err";
   st.textContent=e.message;
 }finally{
   Array.from(document.querySelectorAll("button")).forEach(function(b){b.disabled=false});
 }
}
document.getElementById("start").onclick=function(){act("start")};
document.getElementById("working").onclick=function(){act("working")};
document.getElementById("failed").onclick=function(){act("not_working")};
document.getElementById("again").onclick=function(){act("retest")};
document.getElementById("skip").onclick=function(){act("skip")};
document.getElementById("alloff").onclick=function(){act("all_off")};
document.getElementById("prev").onclick=function(){index=Math.max(0,index-1);render()};
document.getElementById("next").onclick=function(){index=Math.min(state.devices.length-1,index+1);render()};
refresh();
</script>
</main></body></html>'''.replace("__CSRF__", CSRF)

class Handler(BaseHTTPRequestHandler):
    server_version = "JNSZigbeeTester/1.0"

    def _json(self, code, obj):
        body=json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/":
            body=HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path=="/api/status":
            with LOCK:
                results=load_results()
                nxt=next_unclassified(results)
            self._json(200,{"devices":DEVICES,"results":results,"next_index":nxt})
            return
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path!="/api/action":
            self.send_error(404)
            return
        try:
            length=int(self.headers.get("Content-Length","0"))
            data=json.loads(self.rfile.read(length) or b"{}")
            if not secrets.compare_digest(str(data.get("csrf","")),CSRF):
                self._json(403,{"error":"Invalid session token; reload the page."})
                return
            action=str(data.get("action",""))
            index=int(data.get("index",-1))
            if action=="all_off":
                with LOCK:
                    run_control("all-off")
                self._json(200,{"ok":True})
                return
            if not (0 <= index < len(DEVICES)):
                self._json(400,{"error":"Invalid device"})
                return
            d=DEVICES[index]
            with LOCK:
                if action in ("start","retest"):
                    run_control(d["ieee"],"ON")
                    self._json(200,{"ok":True,"device":d})
                    return
                if action in ("working","not_working","skip"):
                    run_control(d["ieee"],"OFF")
                    results=load_results()
                    results[d["ieee"]]={"status":action,"name":d["name"],"time":now()}
                    save_results(results)
                    nxt=next_unclassified(results,index)
                    self._json(200,{"ok":True,"next_index":nxt})
                    return
            self._json(400,{"error":"Unknown action"})
        except subprocess.TimeoutExpired:
            self._json(504,{"error":"Zigbee control command timed out"})
        except Exception as e:
            self._json(500,{"error":str(e)})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

if __name__=="__main__":
    print("JNS Zigbee Phone Tester listening on http://%s:%s/" % (BIND,PORT), flush=True)
    ThreadingHTTPServer((BIND,PORT),Handler).serve_forever()
