#!/usr/bin/env python3
from __future__ import annotations
import json, os, shlex, subprocess, sys, tempfile
PRIMARY=os.environ.get("JNS_DNS_PRIMARY","10.10.10.247")
SECONDARY=os.environ.get("JNS_DNS_SECONDARY","10.10.10.248")
DOMAIN=os.environ.get("JNS_DNS_DOMAIN","home.arpa")
SSH=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=accept-new"]
def ssh(host,script,input_data=None):
    return subprocess.run(SSH+["root@"+host,"bash","-s"],input=input_data or script,text=True,capture_output=True,timeout=30)
def detect(host):
    script=r'''set -e
if systemctl is-active --quiet dnsmasq; then echo dnsmasq; exit; fi
if systemctl is-active --quiet named || systemctl is-active --quiet bind9; then echo bind; exit; fi
if systemctl is-active --quiet AdGuardHome; then echo adguardhome; exit; fi
if systemctl is-active --quiet unbound; then echo unbound; exit; fi
echo unknown
'''
    p=ssh(host,script); return (p.stdout.strip().splitlines() or ["unreachable"])[-1],p
def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "preview"; records=json.loads(sys.argv[2]) if len(sys.argv)>2 else []
    backend,p=detect(PRIMARY)
    result={"ok":False,"mode":mode,"primary":PRIMARY,"secondary":SECONDARY,"backend":backend,"records":len(records)}
    if p.returncode!=0:
        result["error"]="Cannot SSH to primary DNS from Node C";result["detail"]=p.stderr.strip();print(json.dumps(result));return 10
    if backend!="dnsmasq":
        result["error"]="Safe writer currently supports dnsmasq only; no DNS files were changed."
        result["next"]="Add a backend adapter after confirming the live DNS daemon/configuration."
        print(json.dumps(result));return 20
    lines=["# Managed by JNS DrayTek DNS importer","# A + PTR records via dnsmasq host-record"]
    for r in records: lines.append("host-record=%s,%s"%(r["fqdn"],r["ip"]))
    content="\n".join(lines)+"\n"
    result["managed_file"]="/etc/dnsmasq.d/jns-draytek-static.conf";result["content"]=content
    if mode=="preview": result["ok"]=True;print(json.dumps(result));return 0
    remote=r'''set -Eeuo pipefail
tmp=$(mktemp)
cat >"$tmp"
install -d -m 0755 /etc/dnsmasq.d
if [ -f /etc/dnsmasq.d/jns-draytek-static.conf ]; then cp -a /etc/dnsmasq.d/jns-draytek-static.conf /etc/dnsmasq.d/jns-draytek-static.conf.bak; fi
install -o root -g root -m 0644 "$tmp" /etc/dnsmasq.d/jns-draytek-static.conf
rm -f "$tmp"
dnsmasq --test
systemctl reload dnsmasq || systemctl restart dnsmasq
'''
    a=ssh(PRIMARY,remote,content)
    if a.returncode!=0: result["error"]="Primary apply failed";result["detail"]=a.stderr.strip();print(json.dumps(result));return 30
    result["ok"]=True;result["primary_applied"]=True
    # Secondary: apply same managed file only if it is also dnsmasq and reachable.
    btype,bp=detect(SECONDARY)
    result["secondary_backend"]=btype
    if bp.returncode==0 and btype=="dnsmasq":
        b=ssh(SECONDARY,remote,content);result["secondary_applied"]=b.returncode==0
        if b.returncode!=0: result["secondary_error"]=b.stderr.strip()
    else: result["secondary_applied"]=False
    print(json.dumps(result));return 0
if __name__=="__main__": raise SystemExit(main())
