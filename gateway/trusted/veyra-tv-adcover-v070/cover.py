#!/usr/bin/env python3
"""VEYRA TV advert cover v0.7.0: manual, bounded Wayland overlay and targeted player mute."""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST, PORT = "127.0.0.1", 8773
STATE = Path("/run/veyra-adcover-v070")
MUTE_FILE = STATE / "prior-mutes.json"
PLAYER_PORT = "23570"
HTML = Path(__file__).with_name("index.html")
APP_LOCK = threading.RLock()
COVER = None
ENDS = 0.0
TOTAL = 0
MUTE_RESULT = "not attempted"
FONT = next((x for x in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                          "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf")
             if Path(x).is_file()), None)

def shell(cmd, timeout=4):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def service_live():
    return shell(["systemctl","is-active","--quiet","veyra-tv-v070.service"]).returncode == 0

def runtime():
    uid = subprocess.check_output(["id","-u","veyra"],text=True).strip()
    root = Path("/run/user") / uid
    sockets = sorted(p for p in root.glob("wayland-*") if p.is_socket())
    if not sockets:
        raise RuntimeError("No physical Wayland socket for Veyra")
    return str(root), sockets[0].name

def pulse(args):
    root,_ = runtime()
    return shell(["runuser","-u","veyra","--","env",f"XDG_RUNTIME_DIR={root}",
                  f"PULSE_SERVER=unix:{root}/pulse/native","pactl"]+args)

def player_pid_ok(pid):
    if type(pid) is not int or pid <= 0: return False
    try:
        cmd = (Path("/proc")/str(pid)/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")
        comm = (Path("/proc")/str(pid)/"comm").read_text().strip()
    except OSError:
        return False
    return comm == "ffplay" and "udp://127.0.0.1:"+PLAYER_PORT in cmd

def player_inputs():
    r = pulse(["list","sink-inputs"])
    if r.returncode != 0:
        raise RuntimeError("Unable to inspect Veyra audio sink inputs")
    found=[]
    for section in re.split(r"(?=Sink Input #\d+)",r.stdout):
        im=re.search(r"^Sink Input #(\d+)",section)
        pm=re.search(r'application\.process\.id\s*=\s*"(\d+)"',section)
        mm=re.search(r"^\s*Mute:\s*(yes|no)",section,re.M)
        if not (im and pm and mm):
            continue
        pid=int(pm.group(1))
        if player_pid_ok(pid):
            found.append(dict(index=int(im.group(1)),pid=pid,was_muted=mm.group(1)=="yes"))
    return found

def write_mute_state(rows):
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    p=MUTE_FILE.with_suffix(".tmp")
    p.write_text(json.dumps(rows))
    os.chmod(p,0o600)
    p.replace(MUTE_FILE)

def restore_audio():
    if not MUTE_FILE.exists():
        return
    try: rows=json.loads(MUTE_FILE.read_text())
    except (OSError,ValueError):rows=[]
    for row in rows:
        if player_pid_ok(row.get("pid")):
            pulse(["set-sink-input-mute",str(row["index"]),"1" if row["was_muted"] else "0"])
    MUTE_FILE.unlink(missing_ok=True)

def mute_player():
    global MUTE_RESULT
    try:
        rows=player_inputs()
        if not rows:
            MUTE_RESULT="No matching player audio stream found; audio may continue"
            return
        write_mute_state(rows)
        success=True
        for row in rows:
            if pulse(["set-sink-input-mute",str(row["index"]),"1"]).returncode != 0:
                success=False
        MUTE_RESULT="Muted Veyra player audio" if success else "Audio mute incomplete; check sound"
    except Exception as exc:
        MUTE_RESULT="Audio mute unavailable: "+str(exc)[:130]

def ffplay_graph(seconds):
    d=int(seconds)
    font=FONT
    labels=[
        f"drawtext=fontfile={font}:text=VEYRA:fontcolor=0x68EDDF:fontsize=38:x=(w-text_w)/2:y=180",
        f"drawtext=fontfile={font}:text=ADVERT BREAK:fontcolor=white:fontsize=66:x=(w-text_w)/2:y=272",
        f"drawtext=fontfile={font}:text=Your programme continues playing:fontcolor=0xB4CDE0:fontsize=27:x=(w-text_w)/2:y=397",
        f"drawtext=fontfile={font}:text=Estimated cover {d} seconds:fontcolor=0xAAC4D6:fontsize=23:x=(w-text_w)/2:y=610",
        f"drawtext=fontfile={font}:text=Use End Cover to return early:fontcolor=0xAAC4D6:fontsize=20:x=(w-text_w)/2:y=662",
    ]
    return (
        f"color=c=0x091826:s=1366x768:r=25:d={d},"
        "drawbox=x=120:y=555:w=1126:h=18:color=0x23394C:t=fill[bg];"
        f"color=c=0x39E8D2:s=1126x18:r=25:d={d}[fg];"
        f"[bg][fg]overlay=x='120-1126+1126*min(1,t/{d})':y=555:shortest=1,"
        "drawbox=x=0:y=535:w=120:h=45:color=0x091826:t=fill,"
        "drawbox=x=1246:y=535:w=120:h=45:color=0x091826:t=fill,"
        + ",".join(labels)
    )

def stop_cover():
    global COVER, ENDS, TOTAL, MUTE_RESULT
    with APP_LOCK:
        if COVER is not None:
            p=COVER
            if p.poll() is None:
                try: os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError: pass
                try:p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.wait(timeout=2)
            COVER=None
        restore_audio()
        ENDS=0.0
        TOTAL=0
        MUTE_RESULT="not active"

def start_cover(seconds,preview=False):
    global COVER, ENDS, TOTAL, MUTE_RESULT
    if not preview and not service_live():
        raise RuntimeError("Veyra TV player is not running. Use Preview for an 8-second screen test.")
    if not FONT:
        raise RuntimeError("No installed Veyra font found")
    with APP_LOCK:
        stop_cover()
        root,socket=runtime()
        graph=ffplay_graph(seconds)
        cmd=["runuser","-u","veyra","--","env",
             f"XDG_RUNTIME_DIR={root}",f"WAYLAND_DISPLAY={socket}",
             "SDL_VIDEODRIVER=wayland","SDL_AUDIODRIVER=dummy",
             "/usr/bin/ffplay","-hide_banner","-loglevel","error",
             "-autoexit","-fs","-noborder","-f","lavfi","-i",graph]
        log=open(STATE/"cover.log","ab",buffering=0)
        try:
            COVER=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,
                                   stdout=log,stderr=log,start_new_session=True)
        finally:
            log.close()
        ENDS=time.monotonic()+seconds
        TOTAL=seconds
        MUTE_RESULT="Preview only" if preview else "Awaiting player audio"
        if not preview:
            # Allow the cover to appear before muting Veyra's audio output.
            mute_player()

def state():
    with APP_LOCK:
        active=COVER is not None and COVER.poll() is None and ENDS>time.monotonic()
        remain=max(0,int(ENDS-time.monotonic()+.999)) if active else 0
        hdmi=Path("/sys/class/drm/card0-HDMI-A-1/status")
        return dict(active=active,remaining=remain,total=TOTAL if active else 0,
                    player=service_live(),mute=MUTE_RESULT,hdmi=(hdmi.read_text().strip() if hdmi.exists() else "unknown"),
                    automatic_detection=False,break_length_verified=False)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): print(fmt%args,flush=True)
    def guard(self):
        if self.headers.get("Host") not in ("127.0.0.1:8773","localhost:8773"):
            self.reply(403,{"error":"Only Veyra's local address is allowed"})
            return False
        origin=self.headers.get("Origin")
        if origin and origin not in ("http://127.0.0.1:8773","http://localhost:8773"):
            self.reply(403,{"error":"Cross-origin control denied"})
            return False
        return True
    def head(self,status,typ):
        self.send_response(status)
        self.send_header("Content-Type",typ)
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Content-Security-Policy",
          "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
          "img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
    def reply(self,status,data):
        blob=json.dumps(data).encode("utf8")
        self.head(status,"application/json; charset=utf-8")
        self.wfile.write(blob)
    def do_GET(self):
        if not self.guard():return
        if self.path=="/":
            self.head(200,"text/html; charset=utf-8")
            self.wfile.write(HTML.read_bytes())
        elif self.path=="/api/status":
            self.reply(200,state())
        else:self.reply(404,{"error":"Not found"})
    def do_POST(self):
        if not self.guard():return
        if self.headers.get("X-Veyra-Control")!="ad-cover-v070":
            return self.reply(403,{"error":"Control header required"})
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<=n<=200:
                raise ValueError("Invalid request length")
            data=json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(data,dict):
                raise ValueError("JSON object required")
            if self.path=="/api/end":
                stop_cover()
            elif self.path=="/api/preview":
                start_cover(8,preview=True)
            elif self.path=="/api/start":
                d=data.get("seconds")
                if type(d) is not int or d not in (30,60,90,120,180):
                    raise ValueError("Use 30, 60, 90, 120 or 180 seconds")
                start_cover(d)
            else:return self.reply(404,{"error":"Unknown control"})
            self.reply(200,state())
        except (ValueError,RuntimeError) as e:
            self.reply(400,{"error":str(e)})
        except Exception as e:
            print("Cover error",repr(e),flush=True)
            self.reply(500,{"error":"Cover controller failed"})

def keeper():
    while True:
        time.sleep(.25)
        with APP_LOCK:
            if COVER is not None and (COVER.poll() is not None or time.monotonic()>=ENDS):
                stop_cover()

def recover():
    try:restore_audio()
    except Exception as e:print("Recovery warning:",e)
    print("Prior audio mute state restored if player still running.")

def main():
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not FONT:raise SystemExit("Need DejaVu or Liberation font for cover")
    # On restart recover any targeted sink-input mute saved before a crash.
    recover()
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    threading.Thread(target=keeper,daemon=True).start()
    print(f"VEYRA advert cover on http://{HOST}:{PORT}/",flush=True)
    try:server.serve_forever(poll_interval=.25)
    finally:
        stop_cover()
        server.server_close()

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="recover":recover()
    else:main()
