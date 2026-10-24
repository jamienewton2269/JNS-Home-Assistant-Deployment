#!/usr/bin/env python3
"""Read-only VM900 HA automation extraction. Local JSON only, never upload unreviewed HA config."""
import base64,datetime,json,pathlib,subprocess,sys
GUEST=r'''
import json,pathlib,yaml
base=pathlib.Path("/config")
files=[base/"automations.yaml",base/"scripts.yaml"]
pkg=base/"packages"
if pkg.is_dir(): files.extend(sorted(pkg.rglob("*.yaml")))
def clean(v,k=""):
 if any(s in k.lower() for s in ("token","password","secret","credential","api_key","webhook_id","authorization","private_key")):return "[REDACTED]"
 if isinstance(v,dict):return {str(a):clean(b,str(a)) for a,b in v.items()}
 if isinstance(v,list):return [clean(a,k) for a in v]
 if isinstance(v,(int,float,bool,str)) or v is None:return v
 return str(v)
entries=[]; errors=[]
def append(t,obj,f):
 if isinstance(obj,dict): entries.append({"kind":t,"file":f,"definition":clean(obj)})
for p in files:
 if not p.is_file():continue
 name=str(p.relative_to(base))
 try: obj=yaml.safe_load(p.read_text()) or {}
 except Exception as e: errors.append(name+":"+type(e).__name__);continue
 if name=="automations.yaml":
  for item in obj if isinstance(obj,list) else []:append("automation",item,name)
 elif name=="scripts.yaml":
  if isinstance(obj,dict):
   for k,v in obj.items():
    if isinstance(v,dict):append("script",dict(v,script_id=k),name)
 elif isinstance(obj,dict):
  a=obj.get("automation",[])
  if isinstance(a,dict):a=list(a.values())
  for item in a if isinstance(a,list) else []:append("automation",item,name)
  s=obj.get("script",{})
  if isinstance(s,dict):
   for k,v in s.items():
    if isinstance(v,dict):append("script",dict(v,script_id=k),name)
print(json.dumps({"entries":entries,"errors":errors,"files_scanned":[str(p.relative_to(base)) for p in files if p.is_file()]}))
'''
def main():
 if subprocess.check_output(["hostname","-s"],text=True).strip()!="nodea":raise RuntimeError("Run on Node A only")
 payload=base64.b64encode(GUEST.encode()).decode()
 command="import base64;exec(base64.b64decode("+repr(payload)+"))"
 p=subprocess.run(["qm","guest","exec","900","--","docker","exec","homeassistant","python3","-c",command],capture_output=True,text=True,timeout=120)
 if p.returncode:raise RuntimeError(p.stderr[:300] or "qm guest exec failed")
 envelope=json.loads(p.stdout)
 if envelope.get("exitcode")!=0:raise RuntimeError("Guest execution failed: "+envelope.get("err-data","")[:300])
 info=json.loads(envelope["out-data"])
 report={"source":"nodea/VM900","extracted_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),**info}
 path=pathlib.Path("/root/vm900-automation-reference.json")
 if path.exists():raise RuntimeError("Preserve existing "+str(path)+"; rename it before another run")
 path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n");path.chmod(0o600)
 print("Saved:",path,"automation definitions:",sum(x["kind"]=="automation" for x in info["entries"]),"scripts:",sum(x["kind"]=="script" for x in info["entries"]))
 print("Review file for sensitive data and completeness before any transfer. VM900 unchanged.")
if __name__=="__main__":
 try:main()
 except Exception as e:print("ERROR:",e,file=sys.stderr);sys.exit(1)
