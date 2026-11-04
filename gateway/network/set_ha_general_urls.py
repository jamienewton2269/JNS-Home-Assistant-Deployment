#!/usr/bin/env python3
"""Set HA-General internal/external URLs through the established Node C -> Node B QGA path."""
import base64, datetime, json, os, shlex, subprocess, time

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=6"]
HOST = "nodeb"
VM = "905"
URL = "https://ha.jnsystems.xyz"

PATCH = r'''
from pathlib import Path
import datetime, hashlib, os, re, shutil, stat

root = Path("/config")
path = root / "configuration.yaml"
if not path.is_file() or path.is_symlink():
    raise SystemExit("REFUSE: configuration.yaml is missing or unsafe")
old = path.read_bytes()
if not 10 < len(old) < 1024 * 1024:
    raise SystemExit("REFUSE: unexpected configuration.yaml size")
text = old.decode("utf-8")
starts = list(re.finditer(r"(?m)^homeassistant\s*:\s*(?:#.*)?$", text))
if len(starts) != 1:
    raise SystemExit("REFUSE: expected exactly one top-level homeassistant block")

lines = text.splitlines(keepends=True)
start = next(i for i, line in enumerate(lines) if re.match(r"^homeassistant\s*:\s*(?:#.*)?(?:\r?\n)?$", line))
end = len(lines)
for i in range(start + 1, len(lines)):
    line = lines[i]
    if line.strip() and not line.startswith((" ", "\t", "#", "\r", "\n")):
        end = i
        break

block = lines[start + 1:end]
targets = {
    "internal_url": "  internal_url: \"https://ha.jnsystems.xyz\"\n",
    "external_url": "  external_url: \"https://ha.jnsystems.xyz\"\n",
}
seen = {}
for i, line in enumerate(block):
    m = re.match(r"^[ \t]+(internal_url|external_url)\s*:", line)
    if m:
        key = m.group(1)
        if key in seen:
            raise SystemExit("REFUSE: duplicate " + key)
        seen[key] = i
for key, value in targets.items():
    if key in seen:
        block[seen[key]] = value
for key in ("internal_url", "external_url"):
    if key not in seen:
        block.insert(0 if key == "internal_url" else 1, targets[key])

candidate = "".join(lines[:start + 1] + block + lines[end:])
if candidate == text:
    print("JNS_HA_URLS=already_configured")
    raise SystemExit(0)

backup_dir = root / ".jns_url_backups"
if backup_dir.is_symlink():
    raise SystemExit("REFUSE: unsafe backup directory")
backup_dir.mkdir(mode=0o700, exist_ok=True)
backup_dir.chmod(0o700)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = backup_dir / ("configuration.before-url-update-" + stamp + ".yaml")
with backup.open("xb") as f:
    f.write(old)
    f.flush()
    os.fsync(f.fileno())
backup.chmod(0o600)
if hashlib.sha256(backup.read_bytes()).digest() != hashlib.sha256(old).digest():
    raise SystemExit("REFUSE: backup verification failed")

tmp = path.with_name("configuration.yaml.jns-url-tmp")
if tmp.exists() or tmp.is_symlink():
    raise SystemExit("REFUSE: stale staging file")
try:
    with tmp.open("xb") as f:
        f.write(candidate.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
    if path.read_bytes() != old:
        raise SystemExit("REFUSE: concurrent configuration edit")
    os.replace(tmp, path)
finally:
    if tmp.exists():
        tmp.unlink()
print("JNS_HA_URLS=staged")
print("JNS_HA_URL_BACKUP=" + str(backup))
'''

VERIFY = r'''
from pathlib import Path
import re
text = Path("/config/configuration.yaml").read_text()
if len(re.findall(r"(?m)^homeassistant\s*:", text)) != 1:
    raise SystemExit(1)
for key in ("internal_url", "external_url"):
    pattern = r'(?m)^[ \t]+' + key + r'\s*:\s*["\']?https://ha\.jnsystems\.xyz["\']?\s*$'
    if not re.search(pattern, text):
        raise SystemExit(2)
print("JNS_HA_URL_VERIFY=passed")
'''

def run(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def ssh(args, timeout=35):
    p = run(SSH + [HOST, shlex.join(args)], timeout)
    if p.returncode:
        raise RuntimeError("SSH_FAILED")
    return p.stdout

def guest(args, timeout=180):
    data = json.loads(ssh(["qm", "guest", "exec", VM, "--", *args], min(timeout + 30, 360)))
    deadline = time.monotonic() + timeout
    while not data.get("exited"):
        if not data.get("pid") or time.monotonic() >= deadline:
            raise RuntimeError("GUEST_TIMEOUT")
        time.sleep(2)
        data = json.loads(ssh(["qm", "guest", "exec-status", VM, str(data["pid"])], 25))
    return data

def inside(source, timeout=60):
    payload = base64.b64encode(source.encode()).decode()
    return guest(["docker", "exec", "homeassistant", "python3", "-c",
                  "exec(__import__('base64').b64decode('" + payload + "'))"], timeout)

def restore(backup):
    code = """
from pathlib import Path
import os, shutil
p=Path('/config/configuration.yaml')
b=Path(%r)
if not b.is_file() or b.is_symlink() or p.is_symlink(): raise SystemExit(1)
t=p.with_name('configuration.yaml.jns-url-rollback')
if t.exists(): raise SystemExit(2)
shutil.copy2(b,t)
os.replace(t,p)
print('JNS_HA_URL_ROLLBACK=restored')
""" % backup
    result = inside(code)
    if result.get("exitcode") != 0:
        raise RuntimeError("CRITICAL_ROLLBACK_FAILED")

if os.uname().nodename.split(".")[0] != "nodec":
    raise SystemExit("REFUSE: wrong runner")
if ssh(["qm", "status", VM]).strip() != "status: running":
    raise SystemExit("REFUSE: VM905 is not running")
conf = ssh(["qm", "config", VM])
if "name: ha-s2-general" not in conf:
    raise SystemExit("REFUSE: VM905 identity mismatch")

old_start = guest(["docker", "inspect", "homeassistant", "--format", "{{.State.StartedAt}}"], 45).get("out-data", "").strip()
result = inside(PATCH)
output = result.get("out-data", "") or ""
if result.get("exitcode") != 0:
    raise SystemExit("PATCH_FAILED")
status = next((x for x in output.splitlines() if x.startswith("JNS_HA_URLS=")), "")
already = status == "JNS_HA_URLS=already_configured"
backup = next((x.split("=", 1)[1] for x in output.splitlines() if x.startswith("JNS_HA_URL_BACKUP=")), "")
if not already and not backup.startswith("/config/.jns_url_backups/"):
    raise SystemExit("MISSING_SAFE_BACKUP")
print(status)
check = guest(["ha", "core", "check"], 300)
if check.get("exitcode") != 0:
    if backup:
        restore(backup)
        raise SystemExit("CONFIG_CHECK_FAILED_ROLLED_BACK")
    raise SystemExit("CONFIG_CHECK_FAILED_NO_NEW_CHANGE")
verify = inside(VERIFY)
if verify.get("exitcode") != 0:
    if backup:
        restore(backup)
        raise SystemExit("VERIFY_FAILED_ROLLED_BACK")
    raise SystemExit("VERIFY_FAILED_NO_NEW_CHANGE")
print("JNS_HA_URL_CONFIG_CHECK=passed")
try:
    guest(["ha", "core", "restart"], 100)
    print("JNS_HA_URL_RESTART_COMMAND=accepted")
except Exception:
    # HAOS commonly drops the guest-exec command while Core restarts.
    print("JNS_HA_URL_RESTART_COMMAND=ambiguous_verifying_runtime")
deadline = time.monotonic() + 240
while time.monotonic() < deadline:
    try:
        now = guest(["docker", "inspect", "homeassistant", "--format", "{{.State.StartedAt}}"], 40).get("out-data", "").strip()
        if now and now != old_start:
            info = guest(["ha", "core", "info"], 60)
            if info.get("exitcode") == 0:
                print("JNS_HA_URL_UPDATE=complete")
                raise SystemExit(0)
    except Exception:
        pass
    time.sleep(5)
raise SystemExit("RESTART_HEALTH_UNVERIFIED")
