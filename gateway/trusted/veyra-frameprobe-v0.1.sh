#!/usr/bin/env bash
# Veyra isolated Chrome presented-frame monitor v0.1.
# Collects timing counters only; no video/audio/URLs retained.
set -Eeuo pipefail
BASE=/opt/veyra/frameprobe-v01
EXT="$BASE/extension"
RUNNER=/opt/veyra/virtual-loopback-v01/runner.sh
BACK="$BASE/runner.before-frameprobe"
CAP=veyra-virtual-loopback-v01.service
VIEW=veyra-itvx-vnc-v01.service
RX=veyra-frameprobe-rx-v01.service
PORT=8877
[[ $EUID -eq 0 ]] || { echo 'Please run with sudo'; exit 2; }
(( $# == 1 )) || { echo "Usage: sudo bash $0 {preflight|install|activate|report|status|rollback}"; exit 2; }

preflight() {
  [[ -f "$RUNNER" ]] || { echo 'Missing virtual runner'; return 2; }
  bash -n "$RUNNER"
  grep -Fq -- '--user-data-dir=' "$RUNNER" || { echo 'No user-data-dir flag in runner'; return 2; }
  command -v systemd-run >/dev/null
  command -v python3 >/dev/null
  echo "Kiosk: $(systemctl is-active veyra-kiosk.service || true)"
  echo "Virtual Chrome/capture: $(systemctl is-active "$CAP" || true)"
  echo "VNC: $(systemctl is-active "$VIEW" || true)"
  echo "PASS: can configure separate virtual browser frame monitor"
}
install_files() {
  mkdir -p "$EXT"
  chmod 755 "$BASE" "$EXT"

  cat > "$EXT/manifest.json" <<'MANIFEST'
{
  "manifest_version": 3,
  "name": "Veyra Local Frame Monitor",
  "version": "0.1.0",
  "description": "Measures HTML5 video presentation timing locally without storing media.",
  "host_permissions": ["http://127.0.0.1:8877/*"],
  "background": {"service_worker": "worker.js"},
  "content_scripts": [
    {
      "matches": ["https://www.itv.com/*", "https://*.itv.com/*"],
      "js": ["probe.js"],
      "all_frames": true,
      "run_at": "document_idle"
    }
  ]
}
MANIFEST

  cat > "$EXT/worker.js" <<'WORKER'
"use strict";
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.kind !== "veyra-frame-stats") return false;
  if (!sender || !/^https:\/\/([a-z0-9-]+\.)*itv\.com\//i.test(sender.url || "")) return false;
  fetch("http://127.0.0.1:8877/metrics", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Veyra-Frameprobe": "v0.1"},
    body: JSON.stringify(msg.stats)
  }).then(() => sendResponse({ok:true})).catch(() => sendResponse({ok:false}));
  return true;
});
WORKER

  cat > "$EXT/probe.js" <<'PROBE'
(() => {
  "use strict";
  let active = null, token = 0, windowStart = 0, count = 0;
  let prevMedia = null, intervals = [], firstQuality = null, startPresented = 0;
  const round = (n, d = 1) => Math.round(n * Math.pow(10,d)) / Math.pow(10,d);
  const qget = v => {
    try { return v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : null; }
    catch (_) { return null; }
  };
  function deliver(stats) {
    try { chrome.runtime.sendMessage({kind: "veyra-frame-stats", stats}); }
    catch (_) {}
  }
  function reset(video) {
    active = video;
    token++;
    windowStart = performance.now();
    prevMedia = null;
    count = 0;
    intervals = [];
    firstQuality = video ? qget(video) : null;
    startPresented = 0;
    if (!video) return;
    if (typeof video.requestVideoFrameCallback !== "function") {
      deliver({state: "callback-unavailable", width:video.videoWidth, height:video.videoHeight});
      return;
    }
    const myToken = token;
    function frame(now, metadata) {
      if (myToken !== token || active !== video || !video.isConnected) return;
      count++;
      if (startPresented === 0) startPresented = metadata.presentedFrames || 0;
      if (prevMedia !== null) {
        const delta = (metadata.mediaTime - prevMedia) * 1000;
        if (delta > 1 && delta < 500) intervals.push(round(delta, 0));
      }
      prevMedia = metadata.mediaTime;
      if (now - windowStart >= 5000) {
        const elapsed = (now - windowStart) / 1000;
        const q = qget(video);
        const ordered = intervals.slice().sort((a,b)=>a-b);
        const median = ordered.length ? ordered[Math.floor(ordered.length/2)] : null;
        const byInterval = {};
        for (const n of intervals) byInterval[n] = (byInterval[n] || 0) + 1;
        deliver({
          state:video.paused ? "paused" : video.ended ? "ended" : "playing",
          width:video.videoWidth,
          height:video.videoHeight,
          callback_fps:round(count / elapsed, 2),
          media_interval_median_ms:median,
          media_intervals_ms:byInterval,
          callback_frames:count,
          dropped_frames_delta:q && firstQuality ? q.droppedVideoFrames-firstQuality.droppedVideoFrames : null,
          decoded_frames_delta:q && firstQuality ? q.totalVideoFrames-firstQuality.totalVideoFrames : null,
          elapsed_seconds:round(elapsed,2)
        });
        windowStart=now; count=0; intervals=[]; firstQuality=q;
      }
      video.requestVideoFrameCallback(frame);
    }
    video.requestVideoFrameCallback(frame);
  }
  function scan() {
    const candidates=[...document.querySelectorAll("video")].filter(v=>v.isConnected);
    candidates.sort((a,b)=>Number(!a.paused)-Number(!b.paused) ||
      (b.videoWidth*b.videoHeight)-(a.videoWidth*a.videoHeight));
    const chosen=candidates[0] || null;
    if (chosen !== active) reset(chosen);
  }
  setInterval(scan, 1000);
  scan();
})();
PROBE

  cat > "$BASE/receiver.py" <<'RECEIVER'
#!/usr/bin/env python3
"""Veyra frame statistics receiver. Bound only to loopback, stores metrics in RAM."""
import datetime
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

last = None
allowed = ("state","width","height","callback_fps",
           "media_interval_median_ms","media_intervals_ms",
           "callback_frames","dropped_frames_delta","decoded_frames_delta",
           "elapsed_seconds")
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass
    def send_json(self, code, obj):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"receiver":"ready", "sample_received":last is not None})
        if self.path == "/report":
            return self.send_json(200, last or {"receiver":"ready", "sample":"none",
                                               "hint":"Play ITVX in virtual Chrome; ensure extension loaded"})
        self.send_json(404, {"error":"not found"})
    def do_POST(self):
        global last
        if self.path != "/metrics" or self.headers.get("X-Veyra-Frameprobe") != "v0.1":
            return self.send_json(403, {"error":"not permitted"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 2 <= n <= 4096:
                return self.send_json(413, {"error":"invalid length"})
            data = json.loads(self.rfile.read(n))
            if not isinstance(data,dict):
                raise ValueError("not object")
            data = {k:data[k] for k in allowed if k in data}
            data["received_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            last = data
            self.send_json(200, {"ok":True})
        except (ValueError,UnicodeDecodeError,json.JSONDecodeError):
            self.send_json(400, {"error":"invalid stats"})
if __name__=="__main__":
    HTTPServer(("127.0.0.1", 8877), Handler).serve_forever()
RECEIVER
  chmod 644 "$EXT"/* "$BASE/receiver.py"
  python3 -m py_compile "$BASE/receiver.py"
  echo "Installed local frame monitor extension and receiver under $BASE"
}

patch_runner() {
  python3 - "$RUNNER" "$BACK" "$EXT" <<'PY'
from pathlib import Path
import os, shutil, sys
p,backup,ext=map(Path,sys.argv[1:])
text=p.read_text()
flag="--load-extension="+str(ext)
if flag in text:
    print("Virtual Chrome runner already configured.")
    raise SystemExit(0)
if "--load-extension=" in text:
    raise SystemExit("Existing extension launch flag present; refusing to override.")
if text.count("--user-data-dir=")!=1 or "profile" not in text:
    raise SystemExit("Virtual Chrome runner format unrecognised: no changes.")
if not backup.exists():
    shutil.copy2(p,backup)
# Respect whether the user-data-dir option was quoted as a whole argument.
if '"--user-data-dir=' in text:
    updated=text.replace('"--user-data-dir=', '"'+flag+'" "--user-data-dir=',1)
elif "'--user-data-dir=" in text:
    updated=text.replace("'--user-data-dir=", "'"+flag+"' '--user-data-dir=",1)
else:
    updated=text.replace("--user-data-dir=", flag+" --user-data-dir=",1)
tmp=p.with_name(p.name+".frameprobe.tmp")
try:
    tmp.write_text(updated)
    stat=p.stat()
    os.chmod(tmp, stat.st_mode & 0o7777)
    os.chown(tmp, stat.st_uid, stat.st_gid)
    import subprocess
    subprocess.run(["bash","-n",str(tmp)],check=True)
    os.replace(tmp,p)
finally:
    tmp.unlink(missing_ok=True)
print("Virtual Chrome runner updated, backed up as",backup)
PY
}
start_receiver() {
  if systemctl is-active --quiet "$RX"; then return; fi
  systemctl reset-failed "$RX" >/dev/null 2>&1 || true
  systemd-run --quiet --collect --unit=veyra-frameprobe-rx-v01 \
    --property=User=veyra --property=Group=veyra \
    /usr/bin/python3 "$BASE/receiver.py"
  sleep 1
  curl -fsS "http://127.0.0.1:$PORT/health"
  echo
}
restart_virtual() {
  for unit in veyra-live-av-v052.service veyra-live-av-v051.service; do
    if systemctl is-active --quiet "$unit"; then
      echo "ERROR: Player $unit is active; let it finish or stop before virtual browser restart."
      return 3
    fi
  done
  echo 'Restarting virtual Chrome and VNC ONLY. Physical kiosk and provider profile untouched.'
  systemctl stop "$VIEW" 2>/dev/null || true
  systemctl stop "$CAP" 2>/dev/null || true
  systemctl reset-failed "$CAP" >/dev/null 2>&1 || true
  systemd-run --quiet --collect --unit=veyra-virtual-loopback-v01 \
    -p User=veyra -p Group=veyra \
    -p WorkingDirectory=/opt/veyra/virtual-loopback-v01 \
    -p KillMode=control-group -- "$RUNNER"
  sleep 4
  [[ -S /tmp/.X11-unix/X92 ]] || { echo 'Virtual X92 display not available; inspect capture logs'; return 4; }
  systemctl reset-failed "$VIEW" >/dev/null 2>&1 || true
  systemd-run --quiet --collect --unit=veyra-itvx-vnc-v01 \
    -p User=veyra -p Group=veyra -p KillMode=control-group -- \
    /usr/bin/x11vnc -display :92 -localhost -rfbport 5902 -forever -shared -nopw -noxdamage -quiet
  echo 'Virtual Chrome restarted. Reconnect VNC to 127.0.0.1:5902.'
}
case "$1" in
  preflight) preflight ;;
  install)
    preflight
    install_files
    patch_runner
    echo 'INSTALLED ONLY. Run activate to restart virtual Chrome and begin measuring.' ;;
  activate)
    [[ -f "$EXT/manifest.json" ]] || { echo 'Run install first'; exit 2; }
    start_receiver
    restart_virtual
    echo 'Monitor activated. Resume ITVX playback and run report after 10 seconds.' ;;
  report)
    curl -fsS "http://127.0.0.1:$PORT/report" | python3 -m json.tool ;;
  status)
    echo "Receiver: $(systemctl is-active "$RX" || true)"
    echo "Capture: $(systemctl is-active "$CAP" || true)"
    echo "VNC: $(systemctl is-active "$VIEW" || true)"
    curl -fsS "http://127.0.0.1:$PORT/health" || true
    echo ;;
  rollback)
    [[ -f "$BACK" ]] || { echo 'Backup not found; no changes'; exit 2; }
    for unit in veyra-live-av-v052.service veyra-live-av-v051.service; do
      systemctl is-active --quiet "$unit" && { echo 'Stop active video player first'; exit 3; }
    done
    cp -p "$BACK" "$RUNNER"
    bash -n "$RUNNER"
    restart_virtual
    systemctl stop "$RX" 2>/dev/null || true
    echo 'Frameprobe disabled, virtual runner restored. No provider profile deleted.' ;;
  *) echo "Usage: sudo bash $0 {preflight|install|activate|report|status|rollback}";exit 2 ;;
esac
