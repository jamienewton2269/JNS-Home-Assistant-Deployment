#!/usr/bin/env python3
"""
JNS Management Bridge

A deliberately small, dependency-free administrative bridge for systems you own.
It binds to loopback by default, requires a bearer token, only connects to
explicitly configured targets, limits command runtime/output, and writes an
audit record to journald/stdout without recording command text.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import shlex
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

CONFIG_PATH = Path(os.environ.get("JNS_BRIDGE_CONFIG", "/etc/jns-management-bridge/config.json"))
TOKEN_PATH = Path(os.environ.get("JNS_BRIDGE_TOKEN_FILE", "/etc/jns-management-bridge/token"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s jns-management-bridge %(message)s",
)
LOG = logging.getLogger("jns-management-bridge")


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg.get("targets"), dict) or not cfg["targets"]:
        raise RuntimeError("config must define at least one target")
    return cfg


CONFIG = load_config()
TOKEN = TOKEN_PATH.read_text(encoding="utf-8").strip()
if len(TOKEN) < 32:
    raise RuntimeError("access token is missing or too short")

HOST = str(CONFIG.get("listen_host", "127.0.0.1"))
PORT = int(CONFIG.get("listen_port", 8765))
TIMEOUT = int(CONFIG.get("command_timeout", 30))
MAX_OUTPUT = int(CONFIG.get("max_output_bytes", 200000))
MAX_COMMAND = int(CONFIG.get("max_command_chars", 8192))

PAGE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JNS Management Bridge</title>
<style>
body{font-family:system-ui,Segoe UI,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;background:#111;color:#eee}
h1{font-size:1.35rem} .row{display:flex;gap:.6rem;flex-wrap:wrap}
input,select,textarea,button{background:#1b1b1b;color:#eee;border:1px solid #555;border-radius:6px;padding:.65rem}
input{min-width:24rem} select{min-width:12rem} textarea{width:100%;min-height:8rem;font-family:ui-monospace,monospace}
button{cursor:pointer} pre{white-space:pre-wrap;background:#080808;border:1px solid #333;padding:1rem;min-height:12rem;overflow:auto}
small{color:#aaa}
</style>
</head>
<body>
<h1>JNS Management Bridge</h1>
<p><small>Token-authenticated administrative access to configured SSH targets.</small></p>
<div class="row">
<input id="token" type="password" autocomplete="off" placeholder="Access token">
<select id="target"><option>Load targets after entering token</option></select>
<button onclick="loadTargets()">Load targets</button>
</div>
<p><textarea id="command" spellcheck="false" placeholder="Command"></textarea></p>
<p><button onclick="runCommand()">Run</button></p>
<pre id="output">Ready.</pre>
<script>
async function api(path, options={}) {
  const token=document.getElementById('token').value;
  options.headers=Object.assign({}, options.headers||{}, {'Authorization':'Bearer '+token});
  const r=await fetch(path, options);
  const text=await r.text();
  let body;
  try { body=JSON.parse(text); } catch { body={error:text}; }
  if(!r.ok) throw new Error(body.error||('HTTP '+r.status));
  return body;
}
async function loadTargets(){
  const out=document.getElementById('output');
  try{
    const d=await api('/api/targets');
    const s=document.getElementById('target'); s.innerHTML='';
    for(const name of d.targets){ const o=document.createElement('option');o.value=name;o.textContent=name;s.appendChild(o); }
    out.textContent='Targets loaded.';
  }catch(e){out.textContent=String(e);}
}
async function runCommand(){
  const out=document.getElementById('output');
  out.textContent='Running...';
  try{
    const d=await api('/api/run',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({target:document.getElementById('target').value,command:document.getElementById('command').value})
    });
    out.textContent=(d.stdout||'')+(d.stderr ? '\n[stderr]\n'+d.stderr : '')+'\n\n[exit '+d.exit_code+', '+d.duration_ms+' ms]';
  }catch(e){out.textContent=String(e);}
}
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "JNSManagementBridge/0.1"

    def log_message(self, fmt: str, *args) -> None:
        LOG.info("http client=%s " + fmt, self.client_address[0], *args)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        supplied = auth[7:].strip()
        return hmac.compare_digest(supplied, TOKEN)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/health":
            self._json(200, {"ok": True})
            return
        if path == "/api/targets":
            if not self._authorized():
                self._json(401, {"error": "unauthorized"})
                return
            self._json(200, {"targets": sorted(CONFIG["targets"].keys())})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/run":
            self._json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20000:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            target_name = str(payload.get("target", ""))
            command = str(payload.get("command", ""))
        except Exception as exc:
            self._json(400, {"error": f"bad request: {exc}"})
            return

        if target_name not in CONFIG["targets"]:
            self._json(400, {"error": "unknown target"})
            return
        if not command.strip():
            self._json(400, {"error": "empty command"})
            return
        if len(command) > MAX_COMMAND:
            self._json(400, {"error": "command too long"})
            return

        target = CONFIG["targets"][target_name]
        mode = target.get("mode", "ssh")
        cmd_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()[:12]

        if mode == "local":
            argv = ["/bin/bash", "-lc", command]
        elif mode == "ssh":
            destination = str(target.get("destination", "")).strip()
            if not destination:
                self._json(500, {"error": "target missing destination"})
                return
            ssh = [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "ServerAliveInterval=10",
                "-o", "ServerAliveCountMax=2",
            ]
            identity_file = target.get("identity_file")
            if identity_file:
                ssh += ["-i", str(identity_file)]
            ssh += [destination, "--", "bash", "-lc", shlex.quote(command)]
            argv = ssh
        else:
            self._json(500, {"error": "unsupported target mode"})
            return

        started = time.monotonic()
        LOG.info("run start target=%s command_sha256=%s", target_name, cmd_hash)
        try:
            p = subprocess.run(
                argv,
                capture_output=True,
                text=False,
                timeout=TIMEOUT,
                check=False,
                env={**os.environ, "LC_ALL": "C.UTF-8"},
            )
            stdout = p.stdout[:MAX_OUTPUT].decode("utf-8", "replace")
            stderr = p.stderr[:MAX_OUTPUT].decode("utf-8", "replace")
            truncated = len(p.stdout) > MAX_OUTPUT or len(p.stderr) > MAX_OUTPUT
            elapsed = int((time.monotonic() - started) * 1000)
            LOG.info(
                "run finish target=%s command_sha256=%s exit=%s duration_ms=%s truncated=%s",
                target_name, cmd_hash, p.returncode, elapsed, truncated,
            )
            self._json(200, {
                "target": target_name,
                "exit_code": p.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration_ms": elapsed,
                "truncated": truncated,
            })
        except subprocess.TimeoutExpired:
            elapsed = int((time.monotonic() - started) * 1000)
            LOG.warning("run timeout target=%s command_sha256=%s duration_ms=%s", target_name, cmd_hash, elapsed)
            self._json(504, {"error": f"command timed out after {TIMEOUT}s"})
        except Exception as exc:
            LOG.exception("run failed target=%s command_sha256=%s", target_name, cmd_hash)
            self._json(500, {"error": str(exc)})


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    LOG.info("listening on http://%s:%s targets=%s", HOST, PORT, ",".join(sorted(CONFIG["targets"])))
    httpd.serve_forever()


if __name__ == "__main__":
    main()
