#!/usr/bin/env python3
from __future__ import annotations
import base64, ipaddress, json, os, subprocess, sys

PRIMARY=os.environ.get("JNS_DNS_PRIMARY","10.10.10.247")
SECONDARY=os.environ.get("JNS_DNS_SECONDARY","10.10.10.248")
DOMAIN=os.environ.get("JNS_DNS_DOMAIN","home.arpa")
SSH=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=accept-new"]

def ssh(host,script,args=None):
    cmd=SSH+["root@"+host,"bash","-s","--"]+(args or [])
    return subprocess.run(cmd,input=script,text=True,capture_output=True,timeout=45)

def detect(host):
    script=r'''set -e
if systemctl is-active --quiet dnsmasq; then echo dnsmasq; exit; fi
if systemctl is-active --quiet named || systemctl is-active --quiet bind9; then echo bind; exit; fi
if systemctl is-active --quiet AdGuardHome || systemctl is-active --quiet adguardhome; then echo adguardhome; exit; fi
if systemctl is-active --quiet unbound; then echo unbound; exit; fi
echo unknown
'''
    p=ssh(host,script)
    return (p.stdout.strip().splitlines() or ["unreachable"])[-1],p

def adguard_rules(records):
    rules=["! JNS DNS IMPORT BEGIN"]
    for r in records:
        ip=str(ipaddress.ip_address(r["ip"]))
        fqdn=r["fqdn"].rstrip(".")
        rev=".".join(reversed(ip.split(".")))+".in-addr.arpa"
        rules.append(f"||{fqdn}^$dnsrewrite=NOERROR;A;{ip}")
        rules.append(f"||{rev}^$dnsrewrite=NOERROR;PTR;{fqdn}.")
    rules.append("! JNS DNS IMPORT END")
    return rules

def apply_adguard(host,records,commit):
    rules=adguard_rules(records)
    result={"backend":"adguardhome","rules":rules,"records":len(records)}
    if not commit:
        result["ok"]=True
        result["mode"]="preview"
        return result
    payload=json.dumps({"rules":rules},separators=(",",":"))
    remote=r'''set -Eeuo pipefail
PAYLOAD="$(printf '%s' "$1" | base64 -d)"
svc=""
for s in AdGuardHome adguardhome; do
  if systemctl list-unit-files "$s.service" >/dev/null 2>&1 || systemctl is-active --quiet "$s"; then svc="$s"; break; fi
done
[ -n "$svc" ] || { echo "AdGuard Home service not found" >&2; exit 41; }
pid="$(systemctl show -p MainPID --value "$svc")"
[ "$pid" != "0" ] || { echo "AdGuard Home has no running PID" >&2; exit 42; }
exe="$(readlink -f "/proc/$pid/exe")"
workdir="$(dirname "$exe")"
config="$(tr '\0' '\n' <"/proc/$pid/cmdline" | awk 'p{print;exit} $0=="-c"||$0=="--config"{p=1}')"
[ -n "$config" ] || config="$workdir/AdGuardHome.yaml"
[ -f "$config" ] || { echo "AdGuard config not found: $config" >&2; exit 43; }
backup="$config.jns-dns.$(date +%Y%m%dT%H%M%S).bak"
tmp="$(mktemp)"
cp -a "$config" "$backup"
python3 - "$config" "$tmp" "$PAYLOAD" <<'PY'
import json,re,sys
src,tmp,payload=sys.argv[1:]
rules=json.loads(payload)["rules"]
lines=open(src,encoding="utf-8").read().splitlines(True)
start=None
for i,l in enumerate(lines):
    if re.match(r'^user_rules:\s*$',l):
        start=i;break
if start is None:
    if lines and not lines[-1].endswith("\n"): lines[-1]+="\n"
    lines.append("user_rules:\n")
    start=len(lines)-1
    end=len(lines)
else:
    end=start+1
    while end < len(lines):
        l=lines[end]
        if l.strip() and not l.startswith((" ","\t","#")):
            break
        end+=1
block=lines[start+1:end]
out=[]; skipping=False
for l in block:
    if "JNS DNS IMPORT BEGIN" in l:
        skipping=True; continue
    if "JNS DNS IMPORT END" in l:
        skipping=False; continue
    if not skipping: out.append(l)
managed=["  - "+json.dumps(x)+"\n" for x in rules]
new=lines[:start+1]+out+managed+lines[end:]
open(tmp,"w",encoding="utf-8").writelines(new)
PY
"$exe" --check-config -c "$tmp" -w "$workdir" >/dev/null
systemctl stop "$svc"
trap 'cp -a "$backup" "$config"; systemctl start "$svc" || true' ERR
install -o root -g root -m 0600 "$tmp" "$config"
systemctl start "$svc"
systemctl is-active --quiet "$svc"
trap - ERR
rm -f "$tmp"
printf 'service=%s\nconfig=%s\nbackup=%s\n' "$svc" "$config" "$backup"
'''
    payload_b64=base64.b64encode(payload.encode()).decode()
    p=ssh(host,remote,[payload_b64])
    result.update({"ok":p.returncode==0,"mode":"apply","host":host})
    if p.returncode==0:
        for line in p.stdout.splitlines():
            if "=" in line:
                k,v=line.split("=",1); result[k]=v
    else:
        result["error"]="AdGuard Home apply failed"
        result["detail"]=(p.stderr or p.stdout).strip()
    return result

def apply_dnsmasq(host,records,commit):
    lines=["# Managed by JNS DrayTek DNS importer","# A + PTR records via dnsmasq host-record"]
    for r in records:
        lines.append("host-record=%s,%s"%(r["fqdn"],r["ip"]))
    content="\n".join(lines)+"\n"
    result={"backend":"dnsmasq","managed_file":"/etc/dnsmasq.d/jns-draytek-static.conf",
            "content":content,"records":len(records)}
    if not commit:
        result.update({"ok":True,"mode":"preview"}); return result
    remote=r'''set -Eeuo pipefail
tmp=$(mktemp)
printf '%s' "$1" | base64 -d >"$tmp"
install -d -m 0755 /etc/dnsmasq.d
backup=""
if [ -f /etc/dnsmasq.d/jns-draytek-static.conf ]; then
  backup=/etc/dnsmasq.d/jns-draytek-static.conf.bak.$(date +%Y%m%dT%H%M%S)
  cp -a /etc/dnsmasq.d/jns-draytek-static.conf "$backup"
fi
install -o root -g root -m 0644 "$tmp" /etc/dnsmasq.d/jns-draytek-static.conf
rm -f "$tmp"
dnsmasq --test
systemctl reload dnsmasq || systemctl restart dnsmasq
printf 'backup=%s\n' "$backup"
'''
    content_b64=base64.b64encode(content.encode()).decode()
    p=ssh(host,remote,[content_b64])
    result.update({"ok":p.returncode==0,"mode":"apply","host":host})
    if p.returncode!=0:
        result["error"]="dnsmasq apply failed"; result["detail"]=(p.stderr or p.stdout).strip()
    return result

def backend_apply(host,backend,records,commit):
    if backend=="adguardhome": return apply_adguard(host,records,commit)
    if backend=="dnsmasq": return apply_dnsmasq(host,records,commit)
    return {"ok":False,"backend":backend,"error":"No safe writer for this DNS backend."}

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "preview"
    records=json.loads(sys.argv[2]) if len(sys.argv)>2 else []
    backend,p=detect(PRIMARY)
    result={"ok":False,"mode":mode,"primary":PRIMARY,"secondary":SECONDARY,
            "backend":backend,"records":len(records)}
    if p.returncode!=0:
        result["error"]="Cannot SSH to primary DNS from Node C"
        result["detail"]=p.stderr.strip()
        print(json.dumps(result)); return 10

    primary=backend_apply(PRIMARY,backend,records,mode=="apply")
    result["primary_result"]=primary
    if not primary.get("ok"):
        result["error"]=primary.get("error","Primary DNS operation failed")
        print(json.dumps(result)); return 20 if mode=="preview" else 30

    result["ok"]=True
    if mode=="preview":
        print(json.dumps(result)); return 0

    result["primary_applied"]=True
    btype,bp=detect(SECONDARY)
    result["secondary_backend"]=btype
    if bp.returncode==0 and btype==backend:
        secondary=backend_apply(SECONDARY,btype,records,True)
        result["secondary_result"]=secondary
        result["secondary_applied"]=bool(secondary.get("ok"))
    else:
        result["secondary_applied"]=False
        result["secondary_note"]="Secondary unreachable or backend differs; primary left valid and active."
    print(json.dumps(result))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
