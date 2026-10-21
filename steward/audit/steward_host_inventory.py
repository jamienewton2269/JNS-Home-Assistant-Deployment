#!/usr/bin/env python3
"""JNS Steward read-only host inventory v0.1. No service changes or secrets read."""
import argparse, datetime, json, re, shutil, socket, subprocess, sys
CHECKS = {
 "cluster": ["pvecm","status"], "vms": ["qm","list"], "containers": ["pct","list"],
 "storage": ["pvesm","status"], "replication": ["pvesr","status"],
 "filesystems": ["df","-hP"], "thin_pools": ["lvs","--noheadings","-o","vg_name,lv_name,lv_size,data_percent,metadata_percent"],
 "links": ["ip","-brief","link"],
 "services_enabled": ["systemctl","list-unit-files","--type=service","--state=enabled","--no-pager","--no-legend"],
 "services_running": ["systemctl","list-units","--type=service","--state=running","--no-pager","--no-legend"],
 "timers": ["systemctl","list-timers","--all","--no-pager","--no-legend"],
}
PAT = re.compile(r"guardian|lunar|steward|jns|mosquitto|zigbee|bluetooth|homeassistant|ha-|consul", re.I)
def run(cmd):
 if not shutil.which(cmd[0]): return {"status":"not_installed"}
 try:
  p=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=12)
  lines=p.stdout.splitlines()
  if cmd[0]=="systemctl": lines=[x for x in lines if PAT.search(x)]
  return {"status":"ok" if p.returncode==0 else "failed","exit_code":p.returncode,"lines":lines[:300],"stderr":p.stderr[:250]}
 except (OSError,subprocess.TimeoutExpired) as e: return {"status":"error","reason":type(e).__name__}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--out",help="Optional new local file; refuses overwrite"); a=ap.parse_args()
 report={"schema_version":"0.1","mode":"READ_ONLY","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"host":socket.gethostname(),"checks":{k:run(v) for k,v in CHECKS.items()},"dns":{}}
 for host in ("nodea","nodeb","nodec","ha-primary.home.arpa","ha-general.home.arpa","ha-security.home.arpa","mqtt.home.arpa"):
  try: report["dns"][host]=sorted({i[4][0] for i in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)})
  except socket.gaierror: report["dns"][host]=[]
 report["warnings"]=["Do not interpret absence from inventory as proof of safe retirement.","Review hostname/address information before sharing.","No promote, restart, repair or delete operations exist in this script."]
 data=json.dumps(report,indent=2)+"\n"
 if a.out:
  with open(a.out,"x",encoding="utf-8") as f:f.write(data)
  print("Saved "+a.out)
 else: sys.stdout.write(data)
if __name__=="__main__":main()
