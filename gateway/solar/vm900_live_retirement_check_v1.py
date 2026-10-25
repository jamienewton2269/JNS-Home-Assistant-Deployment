#!/usr/bin/env python3
"""Read-only immediate check for VM900 retirement state.
Runs from authorized Node C runner; prints no network identities or private configs.
"""
import json,subprocess,shlex,os
def run(host,script,timeout=28):
  try:
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
      "-o","ConnectTimeout=5",host,shlex.join(["bash","-c",script])],
      capture_output=True,text=True,timeout=timeout)
    if p.returncode:return {"status":"ssh_failed","code":p.returncode}
    return {"status":"ok","lines":p.stdout.splitlines()}
  except (OSError,subprocess.TimeoutExpired):
    return {"status":"ssh_timeout"}
def nodea():
    s=r'''
set -e
test "$(hostname -s)" = nodea || exit 69
qm status 900 | sed 's/^/VM900_/'
qm config 900 | awk '/^(onboot|memory|cores|agent):/ {gsub(/[[:space:]]/,""); print "VM900_CFG_"$0}'
if test -f /etc/pve/qemu-server/900.conf; then echo 'VM900_CONFIG_PRESENT=yes'; fi
if test -e /var/lib/jns-solar/ha900/evidence; then
 echo 'SERVICE_INVENTORY_SOURCE_PRESENT=yes'
fi
if qm status 900 | grep -q 'running'; then
 qm guest exec 900 -- docker ps --format '{{.Names}}' >/dev/null 2>&1 && echo 'VM900_DOCKER_READABLE=yes' || echo 'VM900_DOCKER_READABLE=no'
 qm guest exec 900 -- docker ps -q 2>/dev/null | grep -q '^[^[:space:]]' && echo 'VM900_RUNNING_CONTAINERS_PRESENT=yes' || echo 'VM900_RUNNING_CONTAINERS_PRESENT=unknown'
fi
'''
    return run("nodea",s)
def nodec():
  return {"status":"ok","host":os.uname().nodename.split(".")[0],
    "manifest_staged":(os.path.join(os.path.expanduser("~"),".local/share/jns-solar/ha900/evidence") and
                       os.path.isfile(os.path.expanduser("~/.local/share/jns-solar/ha900/evidence/vm900-services-77555d0defa1574c.json")))}
print("JNS_SOLAR_VM900_LIVE_STATUS_READONLY")
print("NODEA="+json.dumps(nodea(),sort_keys=True))
print("NODEC="+json.dumps(nodec(),sort_keys=True))
print("JNS_SOLAR_VM900_LIVE_STATUS_COMPLETE")
