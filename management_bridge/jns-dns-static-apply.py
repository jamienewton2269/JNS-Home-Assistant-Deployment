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
        rules.append(f"|{fqdn}^$dnsrewrite=NOERROR;A;{ip}")
        rules.append(f"|{ptr}^$dnsrewrite=NOERROR;PTR;{fqdn}.")
    return rules

def adguard_info(host):
    script=r'''set -Eeuo pipefail
cfg=""
for p in /opt/AdGuardHome/AdGuardHome.yaml /etc/AdGuardHome/AdGuardHome.yaml /var/lib/AdGuardHome/AdGuardHome.yaml; do
  if [ -f "$p" ]; then cfg="$p"; break; fi
done
[ -n "$cfg" ] || cfg="$(find /opt /etc /var/lib -maxdepth 4 -type f -name AdGuardHome.yaml 2>/dev/null | head -n1 || true)"
python3 - "$cfg" <<'PY'
import json,sys,subprocess,re
p=sys.argv[1]
out={
 "config":p,
 "filtering_enabled":None,
 "protection_enabled":None,
 "rewrites_enabled":None,
 "hostsfile_enabled":None,
 "user_rules_count":0,
 "http_address":None,
 "api":{}
}
if not p:
    print(json.dumps(out)); raise SystemExit

lines=open(p,encoding="utf-8").read().splitlines()

# Boolean flags and top-level user-rules count.
for line in lines:
    s=line.strip()
    for key in ("filtering_enabled","protection_enabled","rewrites_enabled","hostsfile_enabled"):
        if s.startswith(key+":"):
            v=s.split(":",1)[1].strip().lower()
            out[key]=v=="true"

start=None
for i,line in enumerate(lines):
    if line.startswith("user_rules:"):
        start=i+1
        break
if start is not None:
    for line in lines[start:]:
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if line.lstrip().startswith("- "):
            out["user_rules_count"]+=1

# Current schema: http: / address:.  Fall back to legacy bind_host/bind_port.
http_addr=None
for i,line in enumerate(lines):
    if line.startswith("http:"):
        base_indent=len(line)-len(line.lstrip())
        for sub in lines[i+1:]:
            if sub and not sub[0].isspace():
                break
            s=sub.strip()
            if s.startswith("address:"):
                http_addr=s.split(":",1)[1].strip().strip("'\"")
                break
        break
if not http_addr:
    bind_host=None; bind_port=None
    for line in lines:
        s=line.strip()
        if s.startswith("bind_host:"):
            bind_host=s.split(":",1)[1].strip().strip("'\"")
        elif s.startswith("bind_port:"):
            bind_port=s.split(":",1)[1].strip()
    if bind_port:
        http_addr=f"{bind_host or '0.0.0.0'}:{bind_port}"
out["http_address"]=http_addr

# Probe only unauthenticated local API accessibility.  Never print bodies except
# safe aggregate counts from known JSON responses.
port=None
if http_addr:
    m=re.search(r":(\d+)$",http_addr)
    if m:
        port=int(m.group(1))
if port:
    bases=[f"http://127.0.0.1:{port}",f"https://127.0.0.1:{port}"]
    for base in bases:
        scheme=base.split(":",1)[0]
        for ep in ("/control/status","/control/filtering/status","/control/rewrite/list"):
            tmp=f"/tmp/jns-agh-api-{scheme}-{ep.rsplit('/',1)[-1]}.json"
            cmd=["curl","-k","-sS","--max-time","3","-o",tmp,"-w","%{http_code}",base+ep]
            try:
                cp=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
                code=(cp.stdout or "").strip()
            except Exception:
                code="error"
            key=f"{scheme}:{ep}"
            out["api"][key]={"status":code}
            if code=="200" and ep in ("/control/filtering/status","/control/rewrite/list"):
                try:
                    data=json.load(open(tmp,encoding="utf-8"))
                    if ep.endswith("filtering/status"):
                        out["api"][key]["user_rules_count"]=len(data.get("user_rules") or [])
                        out["api"][key]["enabled"]=data.get("enabled")
                    elif isinstance(data,list):
                        out["api"][key]["rewrite_count"]=len(data)
                except Exception:
                    pass
            try:
                import os; os.unlink(tmp)
            except Exception:
                pass

print(json.dumps(out))
PY
'''
    p=ssh(host,script)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1]),p
    except Exception:
        return {"error":"unable to parse AdGuard diagnostics","stdout":p.stdout,"stderr":p.stderr},p

def adguard_apply(host,records):
    payload=base64.b64encode(json.dumps(adguard_rules(records),separators=(",",":")).encode()).decode()
    script=r'''set -Eeuo pipefail
payload_b64="__PAYLOAD__"
validation_host="__HOST__"
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
candidate="$cfg.jns-dns-candidate.$$"
cp -a "$cfg" "$backup"
cp -a "$cfg" "$candidate"
was_active=0
if systemctl is-active --quiet AdGuardHome; then was_active=1; fi

rollback() {
  rm -f "$candidate" || true
  if [ "$was_active" -eq 1 ]; then systemctl stop AdGuardHome || true; fi
  cp -a "$backup" "$cfg" || true
  if [ "$was_active" -eq 1 ]; then systemctl start AdGuardHome || true; fi
}
trap rollback ERR

python3 - "$candidate" "$payload_b64" <<'PY'
import base64,json,sys
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

with open(cfg,"w",encoding="utf-8") as f:
    f.write("".join(lines))
PY

if cmp -s "$candidate" "$cfg"; then
  rm -f "$candidate" "$backup"
  trap - ERR
  printf '{"ok":true,"changed":false,"config":%s,"rules":%s}\n'     "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$cfg")"     "$(python3 -c 'import base64,json,sys; print(len(json.loads(base64.b64decode(sys.argv[1]).decode())))' "$payload_b64")"
  exit 0
fi

systemctl stop AdGuardHome
if ! cmp -s "$backup" "$cfg"; then
  echo "AdGuard configuration changed concurrently; refusing to overwrite" >&2
  systemctl start AdGuardHome || true
  rm -f "$candidate"
  trap - ERR
  exit 43
fi

cat "$candidate" >"$cfg"
rm -f "$candidate"
systemctl start AdGuardHome
systemctl is-active --quiet AdGuardHome

ready=0
for _ in $(seq 1 30); do
  if ss -lnt 2>/dev/null | awk '$4 ~ /:53$/ {found=1} END {exit !found}'; then
    ready=1
    break
  fi
  sleep 0.5
done
if [ "$ready" -ne 1 ]; then
  echo "AdGuard Home became active but TCP/53 did not become ready" >&2
  false
fi

python3 - "$payload_b64" "$validation_host" <<'PY'
import base64,json,socket,struct,sys,time
rules=json.loads(base64.b64decode(sys.argv[1]).decode())
server=sys.argv[2]

def enc(name):
    return b"".join(bytes([len(p)])+p.encode() for p in name.rstrip(".").split("."))+b"\\0"

def read_name(data,off):
    labels=[]; end=None; seen=set()
    while True:
        if off in seen:
            raise RuntimeError("DNS compression loop")
        seen.add(off)
        n=data[off]
        if n==0:
            off+=1
            if end is None: end=off
            break
        if n & 0xC0 == 0xC0:
            ptr=((n & 0x3F)<<8)|data[off+1]
            if end is None: end=off+2
            off=ptr
            continue
        off+=1
        labels.append(data[off:off+n].decode())
        off+=n
    return ".".join(labels),end

def query(name,qtype):
    pkt=struct.pack("!HHHHHH",0x4A50,0x0100,1,0,0,0)+enc(name)+struct.pack("!HH",qtype,1)
    last=None
    for _ in range(8):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.settimeout(1)
        try:
            s.sendto(pkt,(server,53))
            data,_=s.recvfrom(4096)
            _,flags,qd,an,_,_=struct.unpack("!HHHHHH",data[:12])
            if flags & 0xF:
                return []
            off=12
            for _ in range(qd):
                _,off=read_name(data,off)
                off+=4
            out=[]
            for _ in range(an):
                _,off=read_name(data,off)
                typ,cls,ttl,rdlen=struct.unpack("!HHIH",data[off:off+10])
                off+=10
                rstart=off
                if typ==1 and rdlen==4:
                    out.append(socket.inet_ntoa(data[rstart:rstart+4]))
                elif typ==12:
                    val,_=read_name(data,rstart)
                    out.append(val.rstrip("."))
                off=rstart+rdlen
            return out
        except Exception as e:
            last=e
            time.sleep(0.25)
        finally:
            s.close()
    raise RuntimeError(f"DNS query failed for {name}: {last}")

for rule in rules:
    prefix,rest=rule.split("^$dnsrewrite=NOERROR;",1)
    name=prefix[2:] if prefix.startswith("||") else prefix[1:]
    rrtype,value=rest.split(";",1)
    qtype={"A":1,"PTR":12}[rrtype]
    expected=value.rstrip(".")
    answers=[x.rstrip(".") for x in query(name,qtype)]
    if expected not in answers:
        raise RuntimeError(f"{rrtype} validation failed for {name}: expected {expected}, got {answers}")
print(f"validated_rules={len(rules)}")
PY

trap - ERR
printf '{"ok":true,"changed":true,"config":%s,"backup":%s,"rules":%s}\n'   "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$cfg")"   "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$backup")"   "$(python3 -c 'import base64,json,sys; print(len(json.loads(base64.b64decode(sys.argv[1]).decode())))' "$payload_b64")"
'''.replace("__PAYLOAD__",payload).replace("__HOST__",host)
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
  rm -f "$tmp" "$backup"
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
        result["strategy"]="AdGuard Home user_rules managed block with backup, rollback and idempotent compare"
        info,_=adguard_info(PRIMARY)
        result["adguard"]=info

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
