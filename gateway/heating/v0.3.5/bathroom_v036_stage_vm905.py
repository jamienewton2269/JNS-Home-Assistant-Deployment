#!/usr/bin/env python3
"""One-shot backup-only 0.3.6 staging on VM905, authorized Node C -> Node B QGA.

The payload is fixed to reviewed repository files. This program explicitly
does not replace any active Home Assistant module or restart/reload Core.
"""
import base64,hashlib,json,pathlib,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

folder=pathlib.Path("gateway/heating/v0.3.5")
txn=(folder/"bathroom_v036_transaction.py").read_bytes()
manifest_template=b'{"domain":"jns_heating_zones","version":"0.3.4"}'
manifest=json.loads(manifest_template)
# The guest transaction must use the actual installed manifest, preserving all
# original metadata. This marker is replaced *inside* the guest only.
raw={}
for name,path in (
  ("coordinator.py","bathroom_extension/coordinator.py"),
  ("sensor.py","bathroom_extension/sensor.py"),
  ("thermal.py","thermal.py"),
  ("bathroom_reference.py","bathroom_reference.py"),
  ("bathroom_runtime.py","bathroom_runtime.py"),
):
 data=(folder/path).read_bytes()
 if not 0<len(data)<120_000:raise RuntimeError("invalid reviewed source bytes")
 compile(data,path,"exec")
 raw[name]=base64.b64encode(data).decode()
inner=(
    "import base64,hashlib,json,sys\n"
    "from pathlib import Path\n"
    "ns={'__name__':'_jns_bathroom_v036_staging'}\n"
    "exec(compile(base64.b64decode("+repr(base64.b64encode(txn).decode())+
    "),'<jns-confined-v036-transaction>','exec'),ns)\n"
    "candidate={k:base64.b64decode(v) for k,v in "+repr(raw)+".items()}\n"
    "current=(Path('/config/custom_components/jns_heating_zones/manifest.json')).read_bytes()\n"
    "candidate['manifest.json']=ns['candidate_manifest'](current)\n"
    "report=ns['stage']('/config',candidate)\n"
    "print('JNS_BATHROOM_V036_STAGE '+json.dumps(report,sort_keys=True))\n"
)
encoded=base64.b64encode(inner.encode()).decode()
command="exec(__import__('base64').b64decode('"+encoded+"'))"
response=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
    "docker","exec","homeassistant","python3","-c",command]))
end=time.monotonic()+100
while not response.get("exited"):
    if not isinstance(response.get("pid"),int) or time.monotonic()>end:
        raise RuntimeError("VM905 staging status uncertain; inspect before retry")
    time.sleep(1)
    response=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(response["pid"])]))
out=(response.get("out-data") or "").strip()
if response.get("exitcode")!=0 or not out.startswith("JNS_BATHROOM_V036_STAGE "):
    print("JNS_BATHROOM_V036_STAGE_BLOCKED",
          (response.get("err-data") or "")[-240:])
    raise SystemExit(2)
report=json.loads(out.split(" ",1)[1])
if report.get("state")!="staged" or report.get("new_integrations_active") is not False:
    raise RuntimeError("VM905 staged response did not prove live source unchanged")
print(out)
