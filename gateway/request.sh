#!/usr/bin/env bash
set -euo pipefail
WEBROOT=/home/github-runner/steward-web
mkdir -p "$WEBROOT/docs"

cat > "$WEBROOT/index.html" <<'JNSINDEX'
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Home Assistant Steward Documentation</title>
<style>body{font-family:Arial,Helvetica,sans-serif;margin:48px auto;max-width:900px;line-height:1.55;padding:0 22px}h1{margin-bottom:.2em}.card{border:1px solid #bbb;border-radius:10px;padding:20px;margin:22px 0}a{font-size:1.15em;font-weight:700}code{font-family:Consolas,"Courier New",monospace}</style>
</head><body>
<h1>Home Assistant Steward Documentation</h1>
<p>Canonical local documentation library for Home Assistant, Natural Automation, Steward, deployment, recovery and supporting infrastructure.</p>
<div class="card">
<a href="/docs/">Open Home Assistant documentation library</a>
<p>The document library automatically lists files stored in <code>/home/github-runner/steward-web/docs/</code>, so future documentation appears without editing this page.</p>
</div>
<p><strong>Host:</strong> Node C &nbsp; <strong>Port:</strong> 8090</p>
</body></html>
JNSINDEX

cat > "$WEBROOT/docs/JNS_NodeC_SSH_Gateway_Instructions.html" <<'JNSGUIDE'
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JNS Node C SSH Gateway Setup</title>
<style>body{font-family:Arial,Helvetica,sans-serif;margin:40px auto;max-width:980px;line-height:1.55;padding:0 20px}h1,h2{margin-top:1.4em}.warn{border:1px solid #b66;padding:14px 16px;border-radius:8px;margin:16px 0;font-weight:600}pre{background:#f3f3f3;border:1px solid #ddd;border-radius:8px;padding:14px;overflow-x:auto;white-space:pre-wrap}code{font-family:Consolas,"Courier New",monospace}</style>
</head><body>
<h1>JNS Node C → Node A / Node B SSH Access Setup</h1>
<p><strong>Purpose:</strong> Create a dedicated SSH key for the GitHub runner account on Node C and authorize it on Node A and Node B.</p>
<div class="warn">Do not copy or share the private key. Only the public key file ending in <code>.pub</code> should be copied between your own machines.</div>
<h2>Step 1 — Create the SSH key on Node C</h2>
<pre><code>sudo -u github-runner -H ssh-keygen -t ed25519 -f /home/github-runner/.ssh/id_ed25519 -N ""</code></pre>
<pre><code>sudo -u github-runner -H cat /home/github-runner/.ssh/id_ed25519.pub</code></pre>
<h2>Step 2 — Add the public key to Node A</h2>
<pre><code>mkdir -p /root/.ssh
chmod 700 /root/.ssh
echo 'PASTE_THE_PUBLIC_KEY_HERE' &gt;&gt; /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys</code></pre>
<h2>Step 3 — Add the public key to Node B</h2>
<pre><code>mkdir -p /root/.ssh
chmod 700 /root/.ssh
echo 'PASTE_THE_PUBLIC_KEY_HERE' &gt;&gt; /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys</code></pre>
<h2>Step 4 — Optional manual test from Node C</h2>
<pre><code>sudo -u github-runner -H ssh -o BatchMode=yes root@10.10.10.225 'hostname; whoami; pveversion | head -1'</code></pre>
<pre><code>sudo -u github-runner -H ssh -o BatchMode=yes root@10.10.10.235 'hostname; whoami; pveversion | head -1'</code></pre>
<p>Once the public key has been added to both nodes, return to ChatGPT and say <code>key added to A and B</code>.</p>
</body></html>
JNSGUIDE

if [ -f "$WEBROOT/http.pid" ]; then
  oldpid="$(cat "$WEBROOT/http.pid" 2>/dev/null || true)"
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    kill "$oldpid" || true
    sleep 1
  fi
fi

nohup python3 -m http.server 8090 --bind 0.0.0.0 --directory "$WEBROOT" > "$WEBROOT/http.log" 2>&1 &
echo $! > "$WEBROOT/http.pid"
sleep 1

echo "=== STEWARD DOCUMENTATION HOST ==="
echo "webroot=$WEBROOT"
echo "pid=$(cat "$WEBROOT/http.pid")"
echo "url=http://10.10.10.236:8090/"
echo
echo "files:"
find "$WEBROOT" -maxdepth 2 -type f -printf '%P\n' | sort
echo
echo "listener:"
ss -ltnp 2>/dev/null | grep ':8090 ' || true
echo
echo "http test:"
python3 - <<'PY'
import urllib.request
for u in ["http://127.0.0.1:8090/","http://127.0.0.1:8090/docs/JNS_NodeC_SSH_Gateway_Instructions.html"]:
    with urllib.request.urlopen(u, timeout=3) as r:
        print(r.status, u, r.headers.get("Content-Type"))
PY
