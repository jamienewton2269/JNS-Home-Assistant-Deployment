#!/usr/bin/env python3
import subprocess,json,time,shlex,sys
SRC=r'''
import pathlib,json,urllib.request,urllib.parse,urllib.error,datetime
options=pathlib.Path("/data/apps/data/core_letsencrypt/options.json")
token=json.loads(options.read_text())["dns"]["cloudflare_api_token"]
def api(path,method="GET",body=None):
    req=urllib.request.Request("https://api.cloudflare.com/client/v4"+path,method=method,
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},
        data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req,timeout=20) as response:data=json.load(response)
    except urllib.error.HTTPError as exc:
        try:info=json.load(exc);errors=[{"code":x.get("code"),"message":x.get("message")} for x in info.get("errors",[])]
        except Exception:errors=[]
        raise RuntimeError(json.dumps({"HTTP":exc.code,"errors":errors}))
    if not data.get("success"):raise RuntimeError("Cloudflare API request unsuccessful")
    return data.get("result")
domain="jnsystems.xyz";target="jnsystems.freeddns.org"
zones=api("/zones?"+urllib.parse.urlencode({"name":domain}))
assert len(zones)==1,"Expected one authorized zone"
zone=zones[0]["id"]
path="/zones/"+zone+"/dns_records"
records=api(path+"?"+urllib.parse.urlencode({"type":"MX","name":domain,"per_page":100}))
assert all(r["type"]=="MX" and r["name"]==domain for r in records)
desired={"type":"MX","name":domain,"content":target,"priority":10,"ttl":300}
if len(records)==1 and records[0]["content"].rstrip(".")==target and records[0].get("priority")==10:
    print("MX_ALREADY_CONFIGURED",domain,target)
else:
    assert all(r["content"].endswith(".registrar-servers.com") or r["content"].rstrip(".")==target for r in records),"MX records changed unexpectedly; inspect before replacement"
    root=pathlib.Path("/data/jns-mail-mx-backups");root.mkdir(mode=0o700,exist_ok=True)
    backup=root/(domain+"-"+datetime.datetime.now().strftime("%Y%m%dT%H%M%S")+".json")
    backup.write_text(json.dumps({"domain":domain,"records":records},indent=2)+"\n");backup.chmod(0o600)
    api(path+"/batch","POST",{"deletes":[{"id":r["id"]} for r in records],"posts":[desired]})
    print("MX_CHANGED",domain,target,"priority=10 ttl=300","BACKUP",str(backup))
final=api(path+"?"+urllib.parse.urlencode({"type":"MX","name":domain}))
assert len(final)==1 and final[0]["content"].rstrip(".")==target and final[0].get("priority")==10
print("MX_API_VERIFIED",domain,json.dumps([{"content":r["content"],"priority":r.get("priority"),"ttl":r["ttl"]} for r in final]))
'''
def remote(args):
    r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","root@nodeb.home.arpa",shlex.join(args)],capture_output=True,text=True,timeout=60,check=True)
    return json.loads(r.stdout)
d=remote(["qm","guest","exec","905","--","docker","exec","hassio_supervisor","python3","-c",SRC])
for _ in range(40):
    if d.get("exited"):break
    time.sleep(1);d=remote(["qm","guest","exec-status","905",str(d["pid"])])
print(d.get("out-data",""))
if d.get("exitcode")!=0:
    print(d.get("err-data","")[-1800:]);sys.exit("MX update failed")
