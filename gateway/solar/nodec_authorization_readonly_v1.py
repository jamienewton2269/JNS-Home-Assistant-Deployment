#!/usr/bin/env python3
"""Read-only summarize Node C runner's existing sudo grant scope, no sudo commands executed."""
import json,subprocess
try:
 p=subprocess.run(["sudo","-n","-l"],capture_output=True,text=True,timeout=12)
 s=p.stdout if p.returncode==0 else ""
 except_bad=False
except (OSError,subprocess.TimeoutExpired):
 s="";except_bad=True;p=None
names=("ALL","jns-gateway-exec","/usr/bin/install","/usr/bin/python3",
 "/usr/bin/bash","/bin/bash","/usr/bin/systemctl","/bin/systemctl",
 "/usr/sbin/pct","/usr/bin/rsync","/usr/bin/cp","/usr/bin/mv",
 "/usr/bin/tar","/usr/local/sbin/")
out={"status":"ok" if p is not None and p.returncode==0 else "unavailable",
     "declared_matching_command_categories":[],
     "nopasswd_present":"NOPASSWD:" in s,
     "nodec_runner_has_all_grant":any("NOPASSWD: ALL" in row or "NOPASSWD: (ALL)" in row for row in s.splitlines())}
for key in names:
 if key in s:out["declared_matching_command_categories"].append(key)
print("NODEC_ROOT_DEPLOY_GATES="+json.dumps(out,sort_keys=True))
