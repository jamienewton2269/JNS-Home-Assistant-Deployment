#!/usr/bin/env python3
"""Read-only HAOS observer diagnosis for restored Node A VM906.
Observer logs and HTML are scanned privately on Node A and NEVER printed.
Only boolean categories/response codes returned to GitHub Actions.
"""
import base64,json,shlex,subprocess
REMOTE=r'''
import json,re,subprocess,urllib.request,urllib.error,ssl,socket,time
HOST="ha-security.home.arpa"
root="http://"+HOST+":4357"
d={"source":"nodea-to-ha-security-observer"}
for path,key in [("/ping","ping"),("/","home"),("/logs","logs")]:
 try:
  req=urllib.request.Request(root+path,headers={"User-Agent":"JNS-Steward-readonly-diagnostic"})
  with urllib.request.urlopen(req,timeout=7) as response:
   raw=response.read(524288)
   d[key+"_http"]=response.status
   d[key+"_bytes"]=len(raw)
   d[key+"_content_type"]=response.headers.get("Content-Type","").split(";",1)[0]
  text=raw.decode("utf-8","replace")
  if key=="home":
   patterns={"supervisor_connected":r"Supervisor.{0,90}Connected",
             "supervisor_disconnected":r"Supervisor.{0,90}Disconnected",
             "supervisor_unhealthy":r"Supervisor.{0,90}(Unhealthy|Failed|Not running)",
             "generic_error":r"Error|not connected|unable to connect",
             "observer_page":r"Home Assistant Observer|Supervisor"}
   d["observer_home_flags"]={k:bool(re.search(v,text,re.I|re.S)) for k,v in patterns.items()}
  if key=="logs":
   patterns={
     "supervisor_unavailable":r"supervisor.*(unavailable|cannot connect|connection refused|disconnected|timeout)",
     "supervisor_boot":r"supervisor.*(start|boot|initializ)",
     "dns_issue":r"DNS.*(fail|error|timeout|connection|lookup)",
     "docker_issue":r"docker.*(error|fail|not running|cannot connect)",
     "disk_readonly":r"read-only file system|I/O error|filesystem.*error",
     "network_issue":r"network.*(fail|error|unreachable)",
     "core_failed":r"(core|homeassistant).*(crash|fail|error|unhealthy)",
     "critical":r"panic|fatal|critical",
   }
   d["observer_log_flags"]={k:bool(re.search(v,text,re.I)) for k,v in patterns.items()}
   d["observer_logs_lines"]=len(text.splitlines())
 except urllib.error.HTTPError as e:
  d[key+"_http"]=e.code
 except Exception as e:
  d[key+"_error_class"]=type(e).__name__
# Non-mutating SSH host-key-verified check only; no key acceptance.
try:
 q=subprocess.run(["ssh","-o","BatchMode=yes",
                    "-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=4",
                    "root@"+HOST,"ha","core","info"],capture_output=True,text=True,timeout=9)
 d["haos_ssh_existing_key_auth_ok"]=q.returncode==0
 if q.returncode==0:
  raw=q.stdout.lower()
  d["haos_core_info_running"]=bool(re.search(r"^\\s*state:\\s*running",raw,re.M))
  d["haos_core_info_stopped"]=bool(re.search(r"^\\s*state:\\s*stopped",raw,re.M))
except (OSError,subprocess.TimeoutExpired):
 d["haos_ssh_existing_key_auth_ok"]=False
print("VM906_OBSERVER_DIAGNOSTIC="+json.dumps(d,sort_keys=True))
'''
def main():
 code=base64.b64encode(REMOTE.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea",
      shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+code+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=55)
 except (OSError,subprocess.TimeoutExpired):
  print("VM906_OBSERVER_DIAGNOSTIC_BLOCKED=transport_timeout");return
 if p.returncode:
  print("VM906_OBSERVER_DIAGNOSTIC_BLOCKED=remote_failure_rc_"+str(p.returncode));return
 for line in p.stdout.splitlines():
  if line.startswith("VM906_OBSERVER_DIAGNOSTIC="):print(line)
print("VM906_OBSERVER_DIAGNOSTIC_START")
main()
print("VM906_OBSERVER_DIAGNOSTIC_FINISH")
