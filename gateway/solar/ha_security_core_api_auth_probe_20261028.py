#!/usr/bin/env python3
"""Read-only Core API authentication route probe inside HAOS.
HTTP status only, no credentials or response data.
"""
import base64,json,os,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
INNER=r'''
import json,os,urllib.request,urllib.error
token=os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN") or ""
out={}
for name,url in (("supervisor_info","http://supervisor/info"),
                 ("core_proxy","http://supervisor/core/api/"),
                 ("core_direct","http://homeassistant:8123/api/")):
 try:
  req=urllib.request.Request(url,headers={"Authorization":"Bearer "+token} if token else {})
  with urllib.request.urlopen(req,timeout=4) as r:status=r.status
 except urllib.error.HTTPError as e:status=e.code
 except Exception:status="unavailable"
 out[name]=status
print("JNS_CORE_AUTH_ROUTE="+json.dumps({"token_present":bool(token),"statuses":out},sort_keys=True))
'''
SHELL=r'''
for kind in homeassistant hassio_supervisor; do
 if docker ps --format '{{.Names}}' | grep -Fxq "$kind"; then
  docker exec "$kind" python3 -c "exec(__import__('base64').b64decode('CODE'))" 2>/dev/null |
    sed "s/^JNS_CORE_AUTH_ROUTE=/JNS_CORE_AUTH_ROUTE_$kind=/"
 fi
done
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 shell=SHELL.replace("CODE",base64.b64encode(INNER.encode()).decode())
 cmd=SSH+["nodeb",shlex.join(["qm","guest","exec","905","--","sh","-c",shell])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=70)
 except (OSError,subprocess.TimeoutExpired):return 1
 if p.returncode:return 1
 try:j=json.loads(p.stdout)
 except ValueError:return 1
 for _ in range(70):
  if j.get("exited"):break
  if not j.get("pid"):return 1
  time.sleep(.5)
  q=subprocess.run(SSH+["nodeb",shlex.join(["qm","guest","exec-status","905",str(j["pid"])])],
                  capture_output=True,text=True,timeout=22)
  try:j=json.loads(q.stdout)
  except ValueError:return 1
 for line in str(j.get("out-data","")).splitlines():
  if line.startswith("JNS_CORE_AUTH_ROUTE_"):print(line,flush=True)
 print("JNS_CORE_API_AUTH_PROBE_READONLY=yes",flush=True)
 return 0 if j.get("exitcode")==0 else 1
if __name__=="__main__":raise SystemExit(main())
