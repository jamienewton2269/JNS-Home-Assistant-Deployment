#!/usr/bin/env python3
"""Inspect supported HAOS SSH app API proxy through read-only QGA shell.
Does not log addon identifiers, credentials, IPs, headers or payload contents.
"""
import json,os,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SHELL=r'''
count=0
auth=false
flow=false
python=false
for addon in $(docker ps --format '{{.Names}}' | grep '^addon_.*ssh' || true); do
 count=$((count+1))
 code='if command -v curl >/dev/null && test -n "$SUPERVISOR_TOKEN"; then curl --silent --show-error --max-time 8 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/; else echo no; fi'
 status=$(docker exec "$addon" /bin/sh -c "$code" 2>/dev/null || true)
 if test "$status" = "200"; then
  auth=true
  more='curl --silent --max-time 8 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/config/config_entries/flow_handlers'
  resp=$(docker exec "$addon" /bin/sh -c "$more" 2>/dev/null || true)
  if test "$resp" = "200"; then flow=true; fi
  if docker exec "$addon" /bin/sh -c 'command -v python3 >/dev/null' >/dev/null 2>&1; then python=true; fi
  break
 fi
done
printf 'JNS_SECURITY_CORE_API_ROUTE={"ssh_app_candidates":%s,"supervisor_proxy_authenticated":%s,"config_flow_available":%s,"python3_available":%s}\n' "$count" "$auth" "$flow" "$python"
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 cmd=SSH+["nodeb",shlex.join(["qm","guest","exec","905","--","sh","-c",SHELL])]
 try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
 except (OSError,subprocess.TimeoutExpired):return 1
 if r.returncode:return 1
 try:j=json.loads(r.stdout)
 except ValueError:return 1
 for _ in range(65):
  if j.get("exited"):break
  if not j.get("pid"):return 1
  time.sleep(.4)
  st=subprocess.run(SSH+["nodeb",shlex.join(["qm","guest","exec-status","905",str(j["pid"])])],
                    capture_output=True,text=True,timeout=18)
  try:j=json.loads(st.stdout)
  except ValueError:return 1
 for line in str(j.get("out-data","")).splitlines():
  if line.startswith("JNS_SECURITY_CORE_API_ROUTE="):print(line,flush=True)
 print("JNS_SECURITY_API_ROUTE_READONLY=yes",flush=True)
 return 0 if j.get("exitcode")==0 else 1
if __name__=="__main__":raise SystemExit(main())
