#!/usr/bin/env python3
from __future__ import annotations
import base64, ipaddress, json, os, subprocess, sys

PRIMARY=os.environ.get("JNS_DNS_PRIMARY","10.10.10.247")
SECONDARY=os.environ.get("JNS_DNS_SECONDARY","10.10.10.248")
DOMAIN=os.environ.get("JNS_DNS_DOMAIN","home.arpa")
SSH=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=accept-new"]

def ssh(host,script,input_data=None):
    return subprocess.run(
        SSH+["root@"+host,"bash","-s"],
        input=input_data if input_data is not None else script,
        text=True,capture_output=True,timeout=45
    )

def detect(host):
    script=r'''set -e
if systemctl is-active --quiet dnsmasq; then echo dnsmasq; exit; fi
if systemctl is-active --quiet named || systemctl is-active --quiet bind9; then echo bind; exit; fi
if systemctl is-active --quiet AdGuardHome; then echo adguardhome; exit; fi
if systemctl is-active --quiet unbound; then echo unbound; exit; fi
echo unknown
'''
    p=ssh(host,script)
    return (p.stdout.strip().splitlines() or ["unreachable"])[-1],p

def adguard_rules(records):
    rules=[]
    for r in records:
        fqdn=str(r["fqdn"]).rstrip(".").lower()
        ip=str(ipaddress.ip_address(r["ip"]))
        ptr=ipaddress.ip_address(ip).reverse_pointer
        rules.append(f"||{fqdn}^$dnsrewrite=NOERROR;A;{ip}")
        rules.append(f"||{ptr}^$dnsrewrite=NOERROR;PTR;{fqdn}.")
    return rules

def adguard_apply(host,records):
    payload=base64.b64encode(json.dumps(adguard_rules(records),separators=(",",":")).encode()).decode()
    script=r'''set -Eeuo pipefail
payload_b64="__PAYLOAD__"
cfg=""
for p in /opt/AdGuardHome/AdGuardHome.yaml /etc/AdGuardHome/AdGuardHome.yaml /var/lib/AdGuardHome/AdGuardHome.yaml; do
  if [ -f "$p" ]; then cfg="$p"; break; fi
done
if [ -z "$cfg" ]; then
  cfg="$(find /opt /etc /var/lib -maxdepth 4 -type f -name AdGuardHome.yaml 2>/dev/null | head -n1 || true)"
fi
if [ -z "$cfg" ] || [ ! -f "$cfg" ]; then
  echo '{"ok":false,"error":"AdGuardHome.yaml not found"}'
  exit 41
fi

backup="$cfg.jns-dns-$(date +%Y%m%dT%H%M%S).bak"
cp -a "$cfg" "$backup"
was_active=0
if systemctl is-active --quiet AdGuardHome; then was_active=1; fi

rollback() {
  cp -a "$backup" "$cfg" || true
  if [ "$was_active" -eq 1 ]; then systemctl start AdGuardHome || true; fi
}
trap rollback ERR

systemctl stop AdGuardHome
python3 - "$cfg" "$payload_b64" <<'PY'
import base64,json,re,sys
cfg,payload=sys.argv[1:]
rules=json.loads(base64.b64decode(payload).decode())
begin="# JNS_DNS_IMPORT_BEGIN"
end="# JNS_DNS_IMPORT_END"
with open(cfg,encoding="utf-8") as f:
    text=f.read()
lines=text.splitlines(True)

start=None
for i,line in enumerate(lines):
    if line.startswith("user_rules:"):
        start=i
        break

managed=["  "+begin+"\n"]
for rule in rules:
    managed.append("  - "+json.dumps(rule,ensure_ascii=True)+"\n")
managed.append("  "+end+"\n")

if start is None:
    if lines and not lines[-1].endswith("\n"):
        lines[-1]+="\n"
    if lines and lines[-1].strip():
        lines.append("\n")
    lines.append("user_rules:\n")
    lines.extend(managed)
else:
    head=lines[start].strip()
    inline=head[len("user_rules:"):].strip()
    if inline not in ("","[]"):
        raise SystemExit("Refusing to modify non-list inline user_rules value: "+inline)

    stop=start+1
    while stop < len(lines):
        line=lines[stop]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        stop+=1

    body=lines[start+1:stop]
    cleaned=[]
    inside=False
    for line in body:
        if line.strip()==begin:
            inside=True
            continue
        if line.strip()==end:
            inside=False
            continue
        if not inside:
            cleaned.append(line)

    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    newsec=["user_rules:\n"]+cleaned
    if cleaned:
        newsec.append("\n")
    newsec.extend(managed)
    lines=lines[:start]+newsec+lines[stop:]

newtext="".join(lines)
with open(cfg,"w",encoding="utf-8") as f:
    f.write(newtext)
PY

systemctl start AdGuardHome
systemctl is-active --quiet AdGuardHome
trap - ERR
printf '{"ok":true,"config":%s,"backup":%s,"rules":%s}\n'   "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$cfg")"   "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$backup")"   "$(python3 -c 'import base64,json,sys; print(len(json.loads(base64.b64decode(sys.argv[1]).decode())))' "$payload_b64")"
'''.replace("__PAYLOAD__",payload)
    return ssh(host,script)

def dnsmasq_content(records):
    lines=["# Managed by JNS DrayTek DNS importer","# A + PTR records via dnsmasq host-record"]
    for r in records:
        lines.append("host-record=%s,%s"%(r["fqdn"],r["ip"]))
    return "\n".join(lines)+"\n"

def dnsmasq_apply(host,content):
    remote=r'''set -Eeuo pipefail
tmp=$(mktemp)
cat >"$tmp"
install -d -m 0755 /etc/dnsmasq.d
target=/etc/dnsmasq.d/jns-draytek-static.conf
backup="$target.jns-dns-$(date +%Y%m%dT%H%M%S).bak"
if [ -f "$target" ]; then cp -a "$target" "$backup"; fi
if [ -f "$target" ] && cmp -s "$tmp" "$target"; then
  rm -f "$tmp"
  echo '{"ok":true,"changed":false}'
  exit 0
fi
install -o root -g root -m 0644 "$tmp" "$target"
rm -f "$tmp"
if ! dnsmasq --test; then
  [ -f "$backup" ] && cp -a "$backup" "$target"
  exit 42
fi
systemctl reload dnsmasq || systemctl restart dnsmasq
echo '{"ok":true,"changed":true}'
'''
    return ssh(host,remote,content)

def apply_one(host,backend,records):
    if backend=="dnsmasq":
        content=dnsmasq_content(records)
        p=dnsmasq_apply(host,content)
        return p,{"managed_file":"/etc/dnsmasq.d/jns-draytek-static.conf","content":content}
    if backend=="adguardhome":
        p=adguard_apply(host,records)
        return p,{"rules":adguard_rules(records)}
    raise ValueError("unsupported backend")

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "preview"
    records=json.loads(sys.argv[2]) if len(sys.argv)>2 else []
    backend,p=detect(PRIMARY)
    result={"ok":False,"mode":mode,"primary":PRIMARY,"secondary":SECONDARY,"backend":backend,"records":len(records)}
    if p.returncode!=0:
        result["error"]="Cannot SSH to primary DNS from Node C"
        result["detail"]=p.stderr.strip()
        print(json.dumps(result))
        return 10

    supported={"dnsmasq","adguardhome"}
    if backend not in supported:
        result["error"]="Safe writer does not support the detected DNS backend; no DNS files were changed."
        result["next"]="Add a backend adapter after confirming the live DNS daemon/configuration."
        print(json.dumps(result))
        return 20

    if backend=="dnsmasq":
        result["managed_file"]="/etc/dnsmasq.d/jns-draytek-static.conf"
        result["content"]=dnsmasq_content(records)
    else:
        result["managed_rules"]=adguard_rules(records)
        result["managed_rule_count"]=len(result["managed_rules"])
        result["strategy"]="AdGuard Home user_rules managed block with automatic backup/rollback"

    if mode=="preview":
        result["ok"]=True
        print(json.dumps(result))
        return 0

    if mode!="apply":
        result["error"]="Unknown mode"
        print(json.dumps(result))
        return 2

    a,meta=apply_one(PRIMARY,backend,records)
    if a.returncode!=0:
        result["error"]="Primary apply failed"
        result["detail"]=(a.stderr or a.stdout).strip()
        print(json.dumps(result))
        return 30
    result["primary_applied"]=True
    result["primary_result"]=a.stdout.strip()
    result.update(meta)

    btype,bp=detect(SECONDARY)
    result["secondary_backend"]=btype
    if bp.returncode==0 and btype in supported:
        b,_=apply_one(SECONDARY,btype,records)
        result["secondary_applied"]=b.returncode==0
        if b.returncode!=0:
            result["secondary_error"]=(b.stderr or b.stdout).strip()
        else:
            result["secondary_result"]=b.stdout.strip()
    else:
        result["secondary_applied"]=False
        if bp.returncode!=0:
            result["secondary_error"]=bp.stderr.strip()
        elif btype not in supported:
            result["secondary_error"]="Unsupported secondary backend: "+btype

    result["ok"]=True
    print(json.dumps(result))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
