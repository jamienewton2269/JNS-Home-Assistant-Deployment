#!/usr/bin/env python3
"""Read-only HAOS host layout. Output only allowlisted paths + booleans."""
import json,os,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SH=r'''
for p in \
 / /mnt /mnt/data /mnt/data/supervisor /mnt/data/supervisor/addons \
 /mnt/data/supervisor/addons/local /mnt/data/supervisor/local_apps \
 /data /data/supervisor /data/supervisor/addons /data/supervisor/addons/local \
 /data/supervisor/local_apps /addons /addons/local /config /root \
 /usr/share/hassio /usr/share/hassio/addons /usr/share/hassio/addons/local \
 /usr/share/hassio/local_apps /var/lib/docker /media; do
 if test -d "$p"; then printf 'JNS_HAOS_DIR_OK=%s\n' "$p"; fi
done
for p in /mnt/data /data /usr/share/hassio /addons; do
 if test -L "$p"; then printf 'JNS_HAOS_SYMLINK=%s\n' "$p"; fi
done
if command -v findmnt >/dev/null; then
 for p in /mnt/data /data /; do
  if findmnt -n -T "$p" >/dev/null 2>&1; then printf 'JNS_HAOS_MOUNT_LOOKUP_OK=%s\n' "$p"; fi
 done
fi
if test -f /etc/os-release; then
 if grep -q '^ID=haos' /etc/os-release; then echo JNS_HAOS_HOST_ID_MATCH=yes; else echo JNS_HAOS_HOST_ID_MATCH=unknown; fi
fi
if ha --help 2>/dev/null | grep -qw addons; then echo JNS_HAOS_CLI_AVAILABLE=yes; fi
'''
def run(host,args,timeout=30):
 try:return subprocess.run(SSH+[host,shlex.join(args)],text=True,capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 raw=run("nodeb",["qm","guest","exec","905","--","sh","-c",SH],36)
 if not raw or raw.returncode:
  print("JNS_HA905_PATH_DISCOVERY_BLOCKED=qga_transport");return 1
 try:j=json.loads(raw.stdout)
 except ValueError:return 1
 until=time.monotonic()+35
 while not j.get("exited") and time.monotonic()<until:
  if not j.get("pid"):return 1
  time.sleep(.4)
  p=run("nodeb",["qm","guest","exec-status","905",str(j["pid"])],20)
  if not p or p.returncode:return 1
  try:j=json.loads(p.stdout)
  except ValueError:return 1
 if not j.get("exited") or j.get("exitcode")!=0:return 1
 for line in str(j.get("out-data","")).splitlines():
  if line.startswith("JNS_HAOS_"):print(line,flush=True)
 print("JNS_HAOS_PATH_DISCOVERY_READ_ONLY=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
