#!/usr/bin/env python3
import subprocess,json,time,shlex
SRC=r'''
import pathlib,json,urllib.request,urllib.parse,urllib.error
found=False
for raw in ["/data/addons/data/core_letsencrypt/options.json","/data/apps/data/core_letsencrypt/options.json"]:
    p=pathlib.Path(raw)
    if not p.is_file():continue
    data=json.loads(p.read_text())
    dns=data.get("dns",{})
    token=dns.get("cloudflare_api_token")
    print("CERTIFICATE_OPTIONS_FOUND",raw,"DNS_PROVIDER",dns.get("provider"),"DNS_TOKEN_PRESENT",bool(token))
    if not token:
        print("DNS_OPTION_FIELD_NAMES",sorted(dns))
        continue
    found=True
    for domain in ["jnsystems.xyz","sailing-uk.org"]:
        try:
            url="https://api.cloudflare.com/client/v4/zones?"+urllib.parse.urlencode({"name":domain})
            req=urllib.request.Request(url,headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
            result=json.load(urllib.request.urlopen(req,timeout=15))
            zones=result.get("result",[])
            print("DNS_ZONE_ACCESS",domain,result.get("success"),len(zones))
            for zone in zones:
                url="https://api.cloudflare.com/client/v4/zones/"+zone["id"]+"/dns_records?"+urllib.parse.urlencode({"type":"MX","name":domain})
                req=urllib.request.Request(url,headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
                records=json.load(urllib.request.urlopen(req,timeout=15))
                print("CURRENT_MX",domain,json.dumps([{"id":r["id"],"content":r["content"],"priority":r.get("priority"),"ttl":r["ttl"]} for r in records.get("result",[])]))
        except urllib.error.HTTPError as e:print("DNS_ZONE_ERROR",domain,"HTTP",e.code)
        except Exception as e:print("DNS_ZONE_ERROR",domain,type(e).__name__)
print("EXISTING_DNS_TOKEN_FOUND",found)
'''
cmd=["qm","guest","exec","905","--","docker","exec","hassio_supervisor","python3","-c",SRC]
def remote(args):
    r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","root@nodeb.home.arpa",shlex.join(args)],capture_output=True,text=True,timeout=60,check=True)
    return json.loads(r.stdout)
d=remote(cmd)
for _ in range(30):
    if d.get("exited"):break
    time.sleep(1)
    d=remote(["qm","guest","exec-status","905",str(d["pid"])])
print("GUEST_CHECK_EXIT",d.get("exitcode"))
print(d.get("out-data",""))
if d.get("exitcode")!=0:print(d.get("err-data","")[-1000:])
