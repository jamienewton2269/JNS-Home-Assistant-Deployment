#!/usr/bin/env python3
"""Safe VM906 host access verification from the existing Node C GitHub runner."""
import subprocess,os
def check(label,argv):
 try:
  p=subprocess.run(argv,text=True,capture_output=True,timeout=15)
  print(label,"rc",p.returncode,"stdout",p.stdout[-1400:],"stderr",p.stderr[-200:],flush=True)
 except Exception as e:print(label,"EXC",type(e).__name__,str(e)[:180],flush=True)
print("VM906_NODEC_LOCAL_CAPABILITIES",flush=True)
print("UID",os.getuid(),"PATH",os.environ.get("PATH","")[:180],flush=True)
for path in ("/usr/sbin/qm","/usr/bin/qm","/etc/pve","/usr/local/sbin/jns-gateway-exec"):
 print("EXISTS",path,os.path.exists(path),flush=True)
if os.path.isfile("/usr/sbin/qm"):
 check("QM_STATUS_UNPRIVILEGED",["/usr/sbin/qm","status","906"])
 check("QM_STATUS_SUDO_N",["sudo","-n","/usr/sbin/qm","status","906"])
check("GATEWAY_HELP_UNPRIVILEGED",["/bin/sh","-c","test -r /usr/local/sbin/jns-gateway-exec && echo readable || echo restricted"])
print("VM906_LOCAL_PROBE_DONE",flush=True)
