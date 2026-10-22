#!/usr/bin/env python3
"""Read-only guest-purpose inventory using existing private GitHub upload schema."""
import datetime,json,re,subprocess,socket,sys
def cmd(args,timeout=6):
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,stdin=subprocess.DEVNULL)
  return p.stdout.splitlines() if p.returncode==0 else []
 except (OSError,subprocess.TimeoutExpired): return []
def ids(command):
 return [int(m.group(1)) for line in cmd(command) if (m:=re.match(r"^\s*(\d+)\s+",line))][1:] if False else [
 int(m.group(1)) for line in cmd(command)[1:] if (m:=re.match(r"^\s*(\d+)\s+",line))]
def val(lines,key):
 for line in lines:
  if line.startswith(key+":"):return line.split(":",1)[1].strip()
 return ""
out=[]
for typ,listing,status,config in [
 ("VM",["qm","list"],"qm","qm"),("CT",["pct","list"],"pct","pct")]:
 for ident in ids(listing):
  cfg=cmd([config,"config",str(ident)])
  state=val(cmd([status,"status",str(ident)]),"status") or "unknown"
  name=val(cfg,"name") if typ=="VM" else val(cfg,"hostname")
  memory=val(cfg,"memory")
  onboot=val(cfg,"onboot")
  # Never export MAC addresses, IPs, secrets, guest full configs or process arguments.
  line=f"{typ} {ident} state={state} name={name[:64]} memoryMiB={memory} onboot={onboot}"
  if typ=="CT" and state=="running":
   units=cmd(["timeout","5","pct","exec",str(ident),"--","systemctl","list-units","--type=service","--state=running","--no-legend","--plain","--no-pager"],timeout=7)
   names=[]
   for item in units:
    m=re.match(r"^\s*([a-zA-Z0-9_.@-]+\.service)\s",item)
    if m:names.append(m.group(1))
   line+=" services="+",".join(names[:35])
  out.append(line[:600])
report={"schema_version":"0.1","mode":"READ_ONLY","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"host":socket.gethostname(),"checks":{"guest_purpose":{"status":"ok","exit_code":0,"lines":out}}}
if len(sys.argv)!=3 or sys.argv[1]!="--out":raise SystemExit("usage: script --out NEW_REPORT_PATH")
with open(sys.argv[2],"x") as f:json.dump(report,f,indent=2)
print("Guest audit ready",sys.argv[2],len(out),"guests")
