#!/usr/bin/env python3
"""Diagnose HA905 core check failures WITHOUT modifying VM or leaking credentials."""
import json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
def ssh(host,args,timeout=32):
 try:return subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def guest(args,limit=250):
 p=ssh("nodeb",["qm","guest","exec","905","--timeout","180","--",*args],215)
 if not p or p.returncode:
  return {"guest_exec_request_failed":True}
 try:j=json.loads(p.stdout)
 except ValueError:return {"guest_exec_response_invalid":True}
 end=time.monotonic()+limit
 while not j.get("exited") and time.monotonic()<end:
  if not j.get("pid"):return {"guest_exec_missing_pid":True}
  time.sleep(1)
  p=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],25)
  if not p or p.returncode:return {"guest_exec_poll_failed":True}
  try:j=json.loads(p.stdout)
  except ValueError:return {"guest_exec_poll_invalid":True}
 return j if j.get("exited") else {"guest_exec_timeout":True}
def scrub(s):
 lines=[]
 for line in str(s).splitlines():
  if len(lines)>=20:break
  if not line.strip():continue
  # Preserve only error categories, keys or YAML package path; never emit
  # freeform config values, secrets, access tokens, MACs, device hostnames.
  low=line.lower()
  kind=next((k for k in ("invalid config","failed config","error:","warning:","not found","could not","syntax error","required key","duplicate","secret","not allowed","dependency","failed","invalid","yaml","package","automation") if k in low),"message")
  safe=(line.replace("/config/packages/jns_ha_security_native_cutover_20261028_v2.yaml","SECURITY_NATIVE_PACKAGE")
          .replace("/config","CONFIG"))
  safe=re.sub(r"(?i)(password|token|psk|secret|api.key|authorization)(\s*[:=]\s*)[^\s,;]+",r"\1\2[REDACTED]",safe)
  safe=re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b","[IP]",safe)
  safe=re.sub(r"\b[0-9a-fA-F]{32,}\b","[HEX]",safe)
  if any(x in low for x in ("password:","token:","psk:","api_key:")):safe="[REDACTED_SECRET_LINE]"
  lines.append({"kind":kind,"snippet":safe[:170]})
 return lines
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 a=ssh("nodea",["qm","status","906"],20)
 b=ssh("nodeb",["qm","status","905"],20)
 t=ssh("nodea",["systemctl","is-active","jns-ha906-recovery-20261028.timer"],16)
 print("JNS_CORECHECK_SAFE_STATUS="+json.dumps({
    "source_vm906_status":a.stdout.strip() if a and a.returncode==0 else "unknown",
    "target_vm905_status":b.stdout.strip() if b and b.returncode==0 else "unknown",
    "source_recovery_timer_active":bool(t and t.returncode==0 and t.stdout.strip()=="active"),
    },sort_keys=True),flush=True)
 if not a or a.stdout.strip()!="status: running":return 3
 begin=time.monotonic()
 j=guest(["ha","core","check"])
 info={"exitcode":j.get("exitcode"),"elapsed_seconds":round(time.monotonic()-begin,1),
       "out_truncated":j.get("out-truncated"),"err_truncated":j.get("err-truncated"),
       "envelope_flags":[k for k,v in j.items() if (k.startswith("guest_exec_") or k.endswith("_failed")) and v]}
 for kind in ("out-data","err-data"):
  info[kind+"_evidence"]=scrub(j.get(kind,""))
 print("JNS_CORECHECK_CLASSIFIED="+json.dumps(info,sort_keys=True),flush=True)
 return 0
if __name__=="__main__":sys.exit(main())
