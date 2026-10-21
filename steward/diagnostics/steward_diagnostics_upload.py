#!/usr/bin/env python3
"""JNS Steward report handoff. Sanitised inventory only; private GitHub repo required."""
import argparse,datetime,json,os,pathlib,re,sys,urllib.request,urllib.error,base64,hashlib
REPO="jamienewton2269/JNS-Steward-Diagnostics"
API="https://api.github.com"
TOKEN_FILE="/etc/jns-steward/github-diagnostics.token"
MAX_BYTES=400_000
SAFE_CHECKS={"cluster","vms","containers","storage","replication","filesystems","thin_pools","links","services_enabled","services_running","timers"}
SECRET=re.compile(r"(token|password|passwd|secret|private.key|authorization|api[_-]?key|credential|bearer|BEGIN .{0,30}PRIVATE KEY)",re.I)
def api(path,method="GET",data=None,token=None):
 req=urllib.request.Request(API+path,data=json.dumps(data).encode() if data is not None else None,method=method,
   headers={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Authorization":"Bearer "+token,"User-Agent":"JNS-Steward/0.1",**({"Content-Type":"application/json"} if data is not None else {})})
 with urllib.request.urlopen(req,timeout=15) as resp:return json.load(resp)
def private(token):
 info=api("/repos/"+REPO,token=token)
 if info.get("private") is not True:raise RuntimeError("Refusing to upload: destination is not private")
def token_read():
 p=pathlib.Path(TOKEN_FILE)
 if p.stat().st_mode & 0o077:raise RuntimeError("Token file must be mode 0600")
 token=p.read_text().strip()
 if not token:raise RuntimeError("Empty token")
 return token
def clean(infile):
 raw=json.loads(pathlib.Path(infile).read_text())
 if raw.get("mode")!="READ_ONLY" or raw.get("schema_version")!="0.1":raise RuntimeError("Unexpected input report type")
 checks={}
 for name,data in raw.get("checks",{}).items():
  if name not in SAFE_CHECKS:continue
  if name in {"services_enabled","services_running","timers"}:
   lines=[(s.split() or [""])[0] for s in data.get("lines",[]) if isinstance(s,str)]
  else:
   lines=data.get("lines",[])
  lines=[s[:220] for s in lines[:300] if isinstance(s,str) and not SECRET.search(s)]
  checks[name]={"status":data.get("status"),"exit_code":data.get("exit_code"),"lines":lines}
 host=re.sub(r"[^a-zA-Z0-9-]","",str(raw.get("host","unknown")))[:48]
 if not host:raise RuntimeError("Invalid hostname")
 result={"schema_version":"0.1-sanitized","source_utc":raw.get("utc"),"host":host,
         "checks":checks,"dns":{k:v for k,v in raw.get("dns",{}).items() if k in {"nodea","nodeb","nodec","ha-primary.home.arpa","ha-general.home.arpa","ha-security.home.arpa","mqtt.home.arpa"} and isinstance(v,list)},
         "provenance_sha256":hashlib.sha256(pathlib.Path(infile).read_bytes()).hexdigest(),
         "review_status":"pending","warning":"Infrastructure inventory. Access restricted. Sanitization does not imply public safety."}
 encoded=json.dumps(result,indent=2,sort_keys=True).encode()
 if len(encoded)>MAX_BYTES:raise RuntimeError("Sanitized report too large")
 return host,encoded
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--input",required=True);p.add_argument("--ack-dir",default="/var/lib/jns-steward/upload-acks")
 a=p.parse_args();token=token_read();private(token);host,content=clean(a.input)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 name=f"inbox/{host}/{stamp}-{hashlib.sha256(content).hexdigest()[:12]}.json"
 ack_dir=pathlib.Path(a.ack_dir);ack_dir.mkdir(parents=True,exist_ok=True)
 if ack_dir.is_symlink():raise RuntimeError("Refuse symlink ack dir")
 saved=api("/repos/"+REPO+"/contents/"+name,method="PUT",data={"message":"diagnostics: ingest sanitized host inventory","content":base64.b64encode(content).decode()},token=token)
 ack={"repo":REPO,"path":name,"sha":saved["content"]["sha"],"uploaded_at":stamp,"status":"uploaded_pending_review"}
 target=ack_dir/(stamp+"-"+host+".json")
 with target.open("x") as f:json.dump(ack,f,indent=2)
 print(json.dumps({"uploaded":name,"ack":str(target)}))
if __name__=="__main__":
 try:main()
 except Exception as e:print(f"ERROR: {type(e).__name__}: {e}",file=sys.stderr);sys.exit(1)
