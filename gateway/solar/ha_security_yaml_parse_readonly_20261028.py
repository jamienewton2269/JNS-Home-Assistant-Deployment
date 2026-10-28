#!/usr/bin/env python3
"""Private YAML parse diagnostics of intended VM906 security package, no writes."""
import base64,json,os,runpy,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
TARGET=r'''
import base64,json,sys
try:
 import yaml
 raw=base64.b64decode(sys.argv[1],validate=True).decode()
 # Recognize HA !secret references without resolving or exposing values.
 class Loader(yaml.SafeLoader):pass
 Loader.add_constructor("!secret",lambda loader,node:"secret_reference")
 try:
  obj=yaml.load(raw,Loader=Loader)
  result={"parse_ok":True,"top_sections":sorted(obj.keys()) if isinstance(obj,dict) else [],
          "automations_count":len(obj.get("automation",[])) if isinstance(obj,dict) else None,
          "all_automations_initially_disabled":all(x.get("initial_state") is False for x in obj.get("automation",[])) if isinstance(obj,dict) else False}
 except yaml.YAMLError as e:
  mark=getattr(e,"problem_mark",None)
  result={"parse_ok":False,"error_type":e.__class__.__name__,
          "error_line":mark.line+1 if mark else None,
          "error_column":mark.column+1 if mark else None,
          "parser_problem":str(getattr(e,"problem",""))[:90],
          "parser_context":str(getattr(e,"context",""))[:90]}
  if mark:
   def shape(line):
    x=line.lstrip(" ");
    return {"indent":len(line)-len(x),"list":x.startswith("- "),"colon":":" in x,
            "section_key":x.split(":",1)[0] if len(line)-len(x)==0 and ":" in x else None}
   lines=raw.splitlines()
   result["line_shapes"]=[{"line":n+1,**shape(lines[n])} for n in range(max(0,mark.line-6),min(len(lines),mark.line+4))]
 print("JNS_SECURITY_YAML_PARSE_RESULT="+json.dumps(result,sort_keys=True))
except Exception as e:
 print("JNS_SECURITY_YAML_PARSE_RESULT="+json.dumps({"parse_ok":False,"error_type":e.__class__.__name__}))
'''
def ssh(host,args,timeout=38):
 try:r=subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return r.stdout if r.returncode==0 else None
def guest(host,vm,args):
 s=ssh(host,["qm","guest","exec",str(vm),"--",*args],38)
 if not s:return None
 try:j=json.loads(s)
 except ValueError:return None
 for _ in range(50):
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.4)
  s=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],16)
  if not s:break
  try:j=json.loads(s)
  except ValueError:break
 return None
def main():
 mod=runpy.run_path("gateway/solar/ha_security_native_config_stage_guarded_20261028.py")
 b64=base64.b64encode(mod["SOURCE"].encode()).decode()
 out=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+b64+"'))"])
 vals=[l.split("=",1)[1] for l in (out or "").splitlines() if l.startswith("JNS_PRIVATE_NATIVE_STAGE=")]
 if len(vals)!=1:
  print("JNS_SECURITY_YAML_PARSE_AUDIT=source_unavailable");return 1
 try:
  obj=json.loads(base64.b64decode(vals[0],validate=True))
  encoded=base64.b64encode(obj["yaml"].encode()).decode()
 except Exception:return 1
 code=base64.b64encode(TARGET.encode()).decode()
 j=guest("nodeb",905,["docker","exec","homeassistant","python3","-c",
                       "exec(__import__('base64').b64decode('"+code+"'))",encoded])
 if j and j.get("exitcode")==0:
  for line in str(j.get("out-data","")).splitlines():
   if line.startswith("JNS_SECURITY_YAML_PARSE_RESULT="):print(line)
 else:print("JNS_SECURITY_YAML_PARSE_RESULT=unavailable")
 print("JNS_NO_PRODUCTION_STATE_CHANGE=yes")
if __name__=="__main__":main()

# Check indentation-normalised cutover stage v2, 2026-10-28.
