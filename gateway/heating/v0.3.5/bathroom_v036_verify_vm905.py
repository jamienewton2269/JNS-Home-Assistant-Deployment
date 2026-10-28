#!/usr/bin/env python3
"""Independent read-only attestation of VM905 private bathroom stage 0.3.6."""
import base64,json,pathlib,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
STAGE="v036-20261028T103734Z-a6babd0e"
CODE=pathlib.Path("gateway/heating/v0.3.5/bathroom_v036_transaction.py").read_bytes()
inner=(
 "import base64,json\n"
 "ns={'__name__':'_jns_bathroom_verify'}\n"
 "exec(compile(base64.b64decode("+repr(base64.b64encode(CODE).decode())+
 "),'<fixed-v036-check>','exec'),ns)\n"
 "out=ns['verify']('/config',"+repr(STAGE)+")\n"
 "print('JNS_BATHROOM_V036_INTEGRITY '+json.dumps(out,sort_keys=True))\n"
)
cmd="exec(__import__('base64').b64decode('"+base64.b64encode(inner.encode()).decode()+"'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",cmd]))
deadline=time.monotonic()+100
while not r.get("exited"):
 if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
  raise RuntimeError("VM905 stage verification timed out")
 time.sleep(1)
 r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
out=(r.get("out-data") or "").strip()
if r.get("exitcode")!=0 or not out.startswith("JNS_BATHROOM_V036_INTEGRITY "):
 print("JNS_BATHROOM_V036_VERIFY_BLOCKED",(r.get("err-data") or "")[-260:])
 raise SystemExit(2)
state=json.loads(out.split(" ",1)[1])
if not (state.get("stage_id")==STAGE and state.get("state")=="staged"
        and state.get("active_files_sha256_verified")
        and state.get("existing_history_preserved")
        and state.get("core_restarted") is False):
 raise RuntimeError("stage integrity gate not passed")
print(out)
