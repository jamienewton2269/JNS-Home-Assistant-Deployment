#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json,re,yaml
P=Path("/config")
autos=yaml.safe_load((P/"automations.yaml").read_text())
ctl=next(a for a in autos if str(a.get("id"))=="1791918795028")
print("JNS_LUX_CTL="+yaml.safe_dump(ctl,sort_keys=False,allow_unicode=True,width=180),flush=True)
for fp in [P/"configuration.yaml",*sorted((P/"packages").glob("*.yaml"))]:
    if not fp.is_file(): continue
    txt=fp.read_text(errors="replace")
    if "outdoor_raining" in txt:
        print("JNS_RAIN_SOURCE "+fp.name+"\n"+txt[:20000],flush=True)
'''
enc=base64.b64encode(SRC.encode()).decode()
code="exec(__import__('base64').b64decode("+repr(enc)+"))"
def ssh(argv):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],
                  capture_output=True,text=True,timeout=40)
 if p.returncode: raise RuntimeError(p.stderr[-500:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code]);pid=d.get("pid")
for _ in range(80):
 if d.get("exited"):break
 time.sleep(.5); d=ssh(["qm","guest","exec-status","905",str(pid)])
print(d.get("out-data") or "")
if d.get("exitcode")!=0: raise SystemExit(d.get("exitcode") or 2)
