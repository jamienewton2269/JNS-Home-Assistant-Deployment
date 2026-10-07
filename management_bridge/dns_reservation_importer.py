#!/usr/bin/env python3
from __future__ import annotations
import csv, io, ipaddress, json, os, re, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST=os.environ.get("JNS_DNS_IMPORT_HOST","0.0.0.0")
PORT=int(os.environ.get("JNS_DNS_IMPORT_PORT","8770"))
PRIMARY=os.environ.get("JNS_DNS_PRIMARY","10.10.10.247")
SECONDARY=os.environ.get("JNS_DNS_SECONDARY","10.10.10.248")
DOMAIN=os.environ.get("JNS_DNS_DOMAIN","home.arpa")
APPLY="/usr/local/sbin/jns-dns-static-apply"

PAGE=r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JNS DNS Reservation Import</title><style>
body{font-family:system-ui,Segoe UI,sans-serif;background:#101318;color:#eef2f7;max-width:1250px;margin:2rem auto;padding:0 1rem}
.card{background:#171c24;border:1px solid #313846;border-radius:10px;padding:1rem;margin:1rem 0} button,input{background:#222936;color:#fff;border:1px solid #586174;border-radius:7px;padding:.65rem}
button{cursor:pointer} table{border-collapse:collapse;width:100%} th,td{border-bottom:1px solid #333b48;padding:.45rem;text-align:left} td input{width:92%}
.ok{color:#8ee6a1}.bad{color:#ff9292}.muted{color:#aeb8c7} pre{white-space:pre-wrap;background:#0b0e12;padding:1rem;border-radius:8px;max-height:22rem;overflow:auto}
</style></head><body>
<h1>DrayTek → DNS Static Reservation Import</h1>
<p class="muted">Node C management tool. Upload the DrayTek static MAC/IP export, review names, preview, then apply A + PTR records.</p>
<div class="card"><input id="file" type="file" accept=".csv,.txt,.conf,.log"><button onclick="loadFile()">Load file</button>
<span id="state" class="muted">No file loaded.</span></div>
<div class="card"><table><thead><tr><th>Use</th><th>MAC</th><th>IP</th><th>Hostname</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table></div>
<div class="card"><button onclick="preview()">Preview DNS changes</button> <button onclick="applyChanges()">Apply to primary DNS</button>
<pre id="out">Ready.</pre></div>
<script>
let parsed=[];
function normName(s){return (s||'').trim().toLowerCase().replace(/[^a-z0-9-]+/g,'-').replace(/^-+|-+$/g,'').slice(0,63)}
async function loadFile(){let f=document.getElementById('file').files[0]; if(!f)return; let text=await f.text();
 let r=await fetch('/api/parse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})}); let d=await r.json();
 parsed=d.records||[]; render(); document.getElementById('state').textContent=parsed.length+' reservations parsed';}
function render(){let b=document.getElementById('rows');b.innerHTML='';parsed.forEach((x,i)=>{let tr=document.createElement('tr');
 tr.innerHTML='<td><input type="checkbox" '+(x.use?'checked':'')+' onchange="parsed['+i+'].use=this.checked"></td>'+
 '<td>'+x.mac+'</td><td>'+x.ip+'</td><td><input value="'+(x.name||'')+'" oninput="parsed['+i+'].name=normName(this.value);this.value=parsed['+i+'].name"></td>'+
 '<td class="'+(x.valid?'ok':'bad')+'">'+(x.message||'OK')+'</td>';b.appendChild(tr);});}
async function api(path){let active=parsed.filter(x=>x.use).map(x=>({mac:x.mac,ip:x.ip,name:normName(x.name)}));
 let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({records:active})});let t=await r.text();let d;try{d=JSON.parse(t)}catch{d={error:t}}
 document.getElementById('out').textContent=JSON.stringify(d,null,2);return d}
function preview(){api('/api/preview')} function applyChanges(){if(confirm('Apply these reviewed DNS records to the primary DNS server?'))api('/api/apply')}
</script></body></html>"""

MAC=re.compile(r"(?i)\b([0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b")
IP=re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

def clean_name(s):
    s=re.sub(r"[^a-z0-9-]+","-",s.strip().lower()).strip("-")
    return s[:63]

def parse_text(text):
    out=[]; seen=set()
    for raw in text.splitlines():
        if not raw.strip(): continue
        m=MAC.search(raw); ips=IP.findall(raw)
        if not m or not ips: continue
        mac=m.group(0).replace("-",":").lower()
        ip=None
        for cand in ips:
            try:
                obj=ipaddress.ip_address(cand)
                if obj.version==4: ip=str(obj); break
            except ValueError: pass
        if not ip or (mac,ip) in seen: continue
        seen.add((mac,ip))
        remainder=raw.replace(m.group(0)," ").replace(ip," ")
        toks=[x.strip(" ,;|\t") for x in re.split(r"[,;|\t]+|\s{2,}",remainder) if x.strip(" ,;|\t")]
        name=clean_name(toks[-1]) if toks else ""
        if name in {"bind","enabled","static","lan","ip","mac","address"}: name=""
        valid=ipaddress.ip_address(ip).is_private
        out.append({"use":True,"mac":mac,"ip":ip,"name":name,"valid":valid,"message":"OK" if valid else "non-private IPv4"})
    return out

def validate(records):
    errs=[]; names=set(); ips=set(); clean=[]
    for i,r in enumerate(records):
        try: ip=str(ipaddress.ip_address(str(r.get("ip",""))))
        except ValueError: errs.append(f"row {i+1}: invalid IPv4"); continue
        name=clean_name(str(r.get("name","")))
        if not name: errs.append(f"{ip}: hostname required"); continue
        if name in names: errs.append(f"duplicate hostname: {name}")
        if ip in ips: errs.append(f"duplicate IP: {ip}")
        names.add(name); ips.add(ip)
        clean.append({"mac":str(r.get("mac","")).lower(),"ip":ip,"name":name,"fqdn":name+"."+DOMAIN})
    return clean,errs

def run_apply(records, commit):
    p=subprocess.run([APPLY,"apply" if commit else "preview",json.dumps(records,separators=(",",":"))],
        capture_output=True,text=True,timeout=60,check=False)
    try: data=json.loads(p.stdout or "{}")
    except Exception: data={"stdout":p.stdout,"stderr":p.stderr}
    data["exit_code"]=p.returncode
    if p.stderr: data["stderr"]=p.stderr
    return data

class H(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): print(time.strftime("%FT%T"),self.address_string(),fmt%args,flush=True)
    def sendj(self,code,obj):
        b=json.dumps(obj).encode();self.send_response(code);self.send_header("Content-Type","application/json");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if self.path=="/": b=PAGE.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
        elif self.path=="/health": self.sendj(200,{"ok":True,"primary":PRIMARY,"secondary":SECONDARY,"domain":DOMAIN})
        else:self.sendj(404,{"error":"not found"})
    def do_POST(self):
        try:
            n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n).decode())
            if self.path=="/api/parse": return self.sendj(200,{"records":parse_text(str(data.get("text","")))})
            records,errs=validate(data.get("records",[]))
            if errs:return self.sendj(400,{"ok":False,"errors":errs})
            if self.path=="/api/preview": return self.sendj(200,run_apply(records,False))
            if self.path=="/api/apply": return self.sendj(200,run_apply(records,True))
            self.sendj(404,{"error":"not found"})
        except Exception as e:self.sendj(500,{"error":str(e)})
if __name__=="__main__": ThreadingHTTPServer((HOST,PORT),H).serve_forever()
