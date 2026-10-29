#!/usr/bin/env python3
"""Read-only authoritative JNS bathroom promotion gates, no secrets/no writes."""
import json,os,pathlib,sys
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

p=pathlib.Path("/usr/local/sbin/jns-gateway-exec")
paths=[
 "/usr/local/libexec/jns-heating-v035/root_owned_promotion.py",
 "/usr/local/libexec/jns-heating-v035/transaction.py",
 "/usr/local/libexec/jns-heating-v035/runtime_supervisor_check.sh",
 "/etc/jns/heating-v035",
]
out={"nodec_root_wrapper_exists":p.is_file(),
 "nodec_heating_privileged_code_installed":all(pathlib.Path(x).is_file() for x in paths[:3]),
 "nodec_heating_approval_directory_exists":pathlib.Path(paths[3]).is_dir(),
 "nodec_root_handler_hook_present":False}
if p.is_file() and p.stat().st_size<15000 and os.access(p,os.R_OK):
 try:
  out["nodec_root_handler_hook_present"]="ha_heating_v035_promote" in p.read_text()
 except (OSError,UnicodeError):pass
for label,argv in (("vm905",["qm","status","905"]),
                   ("core_info",["qm","guest","exec","905","--","ha","core","info","--raw-json"])):
 try:
  data=ssh_host("nodeb",argv)
  if label=="vm905":
   out["vm905_running"]="status: running" in data
  else:
   result=json.loads(data)
   if result.get("exited") and not result.get("exitcode"):
    val=json.loads(result.get("out-data") or "{}")
    info=val.get("data") or val
    out["ha_core_version"]=info.get("version")
    out["ha_core_api_port"]=info.get("port")
   else:
    out["core_info_pending_or_unavailable"]=True
 except Exception as exc:
  out[label+"_error"]=type(exc).__name__
print("JNS_BATHROOM_DEPLOY_READINESS",json.dumps(out,sort_keys=True))
