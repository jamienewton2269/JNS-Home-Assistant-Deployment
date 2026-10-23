#!/usr/bin/env python3
"""VEYRA provider-visual advert transition recogniser v0.7.1.

Learns user-labelled, low-resolution *image fingerprints* of real entrance
and exit graphics. Frames remain in RAM; only numeric features are stored.
Observation mode is default. No guessed break length or timed ad detection.
"""
from __future__ import annotations
import base64
from collections import deque
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import struct
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST,PORT="127.0.0.1",8774
WIDTH,HEIGHT=160,90
RATE=5
FRAME=WIDTH*HEIGHT
DB=Path(os.environ.get("VEYRA_ADVISION_DATA","/var/lib/veyra/advision-v071"))
FILE=DB/"profiles.json"
HERE=Path(__file__).resolve().parent
VALID_PROVIDERS=("itvx","iplayer","channel4","netflix","primevideo","disney")
LOCK=threading.RLock()
RING=deque(maxlen=100)
EVENTS=deque(maxlen=70)
PROFILES={p:{"in":[],"out":[]} for p in VALID_PROVIDERS}
PROVIDER="itvx"
MODE="observe"
PHASE="programme"
COUNTERS={"in":0,"out":0}
INDEX=0
LASTFRAME=0.0
CAPTURE_STATUS="starting"
SENT={"start":0,"end":0}
THRESH=0.83

def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def event(message):
    EVENTS.appendleft({"time":stamp(),"text":message})
    print(message,flush=True)

def features(frame):
    """Compact spatial luminance and gradient signature; stdlib only."""
    def roi(x0,y0,x1,y1):
        grid=[]
        for ry in range(8):
            row=[]
            for rx in range(9):
                x=x0+(x1-x0-1)*(rx*2+1)//18
                y=y0+(y1-y0-1)*(ry*2+1)//16
                row.append(frame[y*WIDTH+x])
            grid.append(row)
        h=0
        for row in grid:
            for i in range(8):
                h=(h<<1) | (1 if row[i]>row[i+1] else 0)
        return f"{h:016x}"
    blocks=[]
    # 8x4 blocks prevent a single smooth branded area matching unrelated scenes.
    for gy in range(4):
        for gx in range(8):
            x0,x1=gx*20,(gx+1)*20
            y0,y1=gy*22,min(90,(gy+1)*22)
            if gy==3:y1=90
            total=0
            for y in range(y0,y1,2):
                off=y*WIDTH
                for x in range(x0,x1,2):
                    total+=frame[off+x]
            n=((y1-y0+1)//2)*10
            blocks.append(int(total/max(1,n)))
    return {"hashes":[roi(0,0,WIDTH,HEIGHT),roi(28,10,132,77),roi(0,0,WIDTH,48)],
            "blocks":blocks}

def similarity(f,t):
    distances=[(int(a,16)^int(b,16)).bit_count()/64 for a,b in zip(f["hashes"],t["hashes"])]
    block=sum(abs(a-b) for a,b in zip(f["blocks"],t["blocks"]))/(len(f["blocks"])*255)
    # Whole-frame, central and top ROIs, combined with 32-bin spatial luma map.
    return round(max(0., 1.-(.24*distances[0]+.19*distances[1]+.14*distances[2]+.43*block)*2.0),4)

def best(framefeatures, role):
    return max((similarity(framefeatures,t) for t in PROFILES[PROVIDER][role]),default=0.)

def png_gray(frame):
    def chunk(tag,data):
        return struct.pack(">I",len(data))+tag+data+struct.pack(">I",zlib.crc32(tag+data)&0xffffffff)
    raw=b"".join(b"\x00"+frame[y*WIDTH:(y+1)*WIDTH] for y in range(HEIGHT))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",WIDTH,HEIGHT,8,0,0,0,0))+
            chunk(b"IDAT",zlib.compress(raw,level=2))+chunk(b"IEND",b""))

def load():
    global PROVIDER
    if not FILE.exists():return
    try:
        data=json.loads(FILE.read_text())
        for p in VALID_PROVIDERS:
            for role in ("in","out"):
                raw=data.get("profiles",{}).get(p,{}).get(role,[])
                PROFILES[p][role]=[x for x in raw if isinstance(x,dict) and len(x.get("hashes",[]))==3 and len(x.get("blocks",[]))==32][:40]
        name=data.get("provider","itvx")
        if name in VALID_PROVIDERS:PROVIDER=name
    except (OSError,ValueError) as exc:
        event("Could not load visual training: "+str(exc))

def save():
    DB.mkdir(parents=True,exist_ok=True)
    tmp=FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version":"0.7.1","provider":PROVIDER,"profiles":PROFILES},indent=1))
    os.chmod(tmp,0o600)
    tmp.replace(FILE)

def cover_signal(action):
    # No direct player pause, seek, audio or browser intervention.
    data=json.dumps({"reason":"visual-bumper","provider":PROVIDER}).encode()
    req=urllib.request.Request("http://127.0.0.1:8773/api/vision/"+action,data=data,
       headers={"X-Veyra-Control":"ad-cover-v070","Content-Type":"application/json"},
       method="POST")
    try:
        with urllib.request.urlopen(req,timeout=2) as r:
            if r.status!=200:raise RuntimeError("HTTP "+str(r.status))
        SENT[action]+=1
        event("Veyra cover "+action+" accepted by display controller.")
        return True
    except Exception as exc:
        event("Veyra cover "+action+" unavailable: "+str(exc)[:100])
        return False

def observe(f):
    global PHASE
    sc_in,sc_out=best(f,"in"),best(f,"out")
    if sc_in>=THRESH and sc_out>=THRESH:
        COUNTERS["in"]=COUNTERS["out"]=0
        return sc_in,sc_out,"ambiguous"
    role="in" if PHASE=="programme" else "out"
    val=sc_in if role=="in" else sc_out
    if val>=THRESH:
        COUNTERS[role]+=1
        if COUNTERS[role]>=2:
            COUNTERS[role]=0
            if role=="in":
                PHASE="ad-break"
                event(PROVIDER+" "+role+" bumper identified ("+str(round(val,3))+"); ad break observed.")
                if MODE=="armed" and not cover_signal("start"):
                    # Fail open when the display controller declines the trigger.
                    PHASE="programme"
                    event("Cover start was not acknowledged; rearming the programme observer.")
            else:
                PHASE="programme"
                event(PROVIDER+" "+role+" bumper identified ("+str(round(val,3))+"); programme return observed.")
                if MODE=="armed":cover_signal("end")
    else:
        COUNTERS[role]=0
    return sc_in,sc_out,role

def capture():
    global INDEX,LASTFRAME,CAPTURE_STATUS,PHASE
    uid=str(os.getuid())
    # Service runs as veyra, same account used for Xvfb and the existing browser.
    cmd=["/usr/bin/ffmpeg","-hide_banner","-nostdin","-loglevel","error",
         "-f","x11grab","-framerate",str(RATE),"-video_size","1366x768",
         "-i",":92.0","-vf",f"scale={WIDTH}:{HEIGHT}:flags=fast_bilinear,format=gray",
         "-pix_fmt","gray","-an","-f","rawvideo","pipe:1"]
    while True:
        try:
            CAPTURE_STATUS="connecting :92"
            proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                  env={**os.environ,"DISPLAY":":92"},bufsize=FRAME*4)
            CAPTURE_STATUS="capturing"
            while True:
                raw=proc.stdout.read(FRAME)
                if len(raw)!=FRAME:break
                f=features(raw)
                with LOCK:
                    INDEX+=1
                    LASTFRAME=time.monotonic()
                    scores=observe(f)
                    RING.append({"id":INDEX,"time":stamp(),"raw":raw,"feat":f,"scores":scores})
            CAPTURE_STATUS="capture exited; retrying"
            with LOCK:
                if MODE=="armed" and PHASE=="ad-break":
                    event("Display sampling lost; fail open instead of covering indefinitely.")
                    cover_signal("end")
                    PHASE="programme"
            proc.terminate()
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:proc.kill()
        except Exception as exc:
            CAPTURE_STATUS="capture error: "+str(exc)[:100]
        time.sleep(3)

class API(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,data):
        body=json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(body)
    def guard(self):
        if self.headers.get("Host") not in ("127.0.0.1:8774","localhost:8774"):
            self.reply(403,{"error":"Local origin only"});return False
        origin=self.headers.get("Origin")
        if origin not in (None,"http://127.0.0.1:8774","http://localhost:8774"):
            self.reply(403,{"error":"Cross-origin denied"});return False
        return True
    def do_GET(self):
        if not self.guard():return
        path=urllib.parse.urlsplit(self.path).path
        if path in ("/","/index.html","/app.js","/style.css"):
            name={"/":"index.html","/index.html":"index.html","/app.js":"app.js","/style.css":"style.css"}[path]
            try:content=(HERE/name).read_bytes()
            except OSError:return self.reply(500,{"error":"UI missing"})
            self.send_response(200)
            self.send_header("Content-Type",{"index.html":"text/html","app.js":"application/javascript","style.css":"text/css"}[name])
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'")
            self.end_headers();self.wfile.write(content);return
        if path=="/api/state":
            with LOCK:
                item=RING[-1] if RING else None
                f=item["feat"] if item else None
                return self.reply(200,{"mode":MODE,"provider":PROVIDER,"phase":PHASE,"capture":CAPTURE_STATUS,
                  "fresh":bool(item and time.monotonic()-LASTFRAME<4),
                  "frames":INDEX,"templates":{k:len(v) for k,v in PROFILES[PROVIDER].items()},
                  "scores":{"entrance":best(f,"in") if f else 0,"exit":best(f,"out") if f else 0},
                  "events":list(EVENTS)[:18],"threshold":THRESH,
                  "cover_commands":SENT,"no_assumed_break_duration":True})
        if path=="/api/frames":
            with LOCK:
                # Sample 1 frame/second over the last ~16 seconds. Only thumbnails in the HTTP response.
                chosen=list(RING)[::-RATE][:16]
                result=[{"id":e["id"],"time":e["time"],"image":"data:image/png;base64,"+
                  base64.b64encode(png_gray(e["raw"])).decode()} for e in chosen]
            return self.reply(200,{"frames":result})
        self.reply(404,{"error":"Not found"})
    def do_POST(self):
        if not self.guard():return
        if self.headers.get("X-Veyra-Visual")!="labelled-by-operator":
            return self.reply(403,{"error":"Operator control header required"})
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n<=0 or n>1500:raise ValueError("Invalid body length")
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict):raise ValueError("JSON object required")
            path=urllib.parse.urlsplit(self.path).path
            global PROVIDER,MODE,PHASE
            with LOCK:
                if path=="/api/provider":
                    p=data.get("provider")
                    if p not in VALID_PROVIDERS:raise ValueError("Unsupported provider")
                    MODE="observe";PROVIDER=p;PHASE="programme";COUNTERS.update({"in":0,"out":0})
                    save();event("Selected provider "+p+"; observation mode.")
                elif path=="/api/teach":
                    role=data.get("role");fid=data.get("frame_id")
                    if role not in ("in","out") or type(fid) is not int:raise ValueError("Invalid labelled bumper")
                    source=next((x for x in RING if x["id"]==fid),None)
                    if source is None:raise ValueError("Frame expired from rolling memory; refresh gallery")
                    pool=PROFILES[PROVIDER][role]
                    if len(pool)>=40:raise ValueError("Template limit reached")
                    if any(similarity(source["feat"],sample)>.995 for sample in pool):
                        raise ValueError("This visual is already stored as a training example")
                    pool.append(source["feat"])
                    save()
                    event("Operator taught "+PROVIDER+" "+role+" bumper from frame "+str(fid))
                elif path=="/api/mode":
                    choice=data.get("mode")
                    if choice not in ("observe","armed"):raise ValueError("Invalid mode")
                    if choice=="armed":
                        if any(len(PROFILES[PROVIDER][k])<2 for k in ("in","out")):
                            raise ValueError("At least 2 actual, labelled entry and 2 exit images required")
                        score=max(similarity(a,b) for a in PROFILES[PROVIDER]["in"] for b in PROFILES[PROVIDER]["out"])
                        if score>=THRESH:
                            raise ValueError("Entrance/exit images overlap visually; cannot safely distinguish them")
                    MODE=choice;PHASE="programme";COUNTERS.update({"in":0,"out":0})
                    event("Detector mode "+MODE+" selected by operator.")
                elif path=="/api/reset-phase":
                    PHASE="programme";COUNTERS.update({"in":0,"out":0});event("Observer manually reset to programme state.")
                else:return self.reply(404,{"error":"Not found"})
            self.reply(200,{"ok":True})
        except (ValueError,KeyError) as exc:self.reply(400,{"error":str(exc)})
        except Exception as exc:
            event("Detector controller error "+type(exc).__name__)
            self.reply(500,{"error":"Internal controller error"})

def selftest():
    a=bytes([0 if x<80 else 240 for y in range(90) for x in range(160)])
    b=bytes([240 if x<80 else 0 for y in range(90) for x in range(160)])
    c=bytes([0 if x<80 else 240 for y in range(90) for x in range(160)])
    fa,fb,fc=features(a),features(b),features(c)
    assert similarity(fa,fc)==1
    assert similarity(fa,fb)<THRESH
    assert png_gray(a).startswith(b"\x89PNG\r\n\x1a\n")
    print("PASS: visual descriptors distinguish distinct transitions; PNG thumbnails in RAM only.")

def main():
    if "--selftest" in os.sys.argv:return selftest()
    DB.mkdir(parents=True,exist_ok=True)
    load()
    event("Started provider visual detector in OBSERVATION mode; no fixed advert timings.")
    threading.Thread(target=capture,daemon=True).start()
    server=ThreadingHTTPServer((HOST,PORT),API)
    server.serve_forever()

if __name__=="__main__":main()
