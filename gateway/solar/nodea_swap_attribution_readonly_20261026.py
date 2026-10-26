#!/usr/bin/env python3
"""Private read-only live Node A swap attribution by process name/VMID.
No environment variables, commands, files or secret arguments are logged.
"""
import base64,shlex,subprocess
REMOTE=r'''
import os,re,json,time
rows=[]
for entry in os.scandir("/proc"):
 if not entry.name.isdigit():continue
 try:
  with open(entry.path+"/status") as f:
   data=f.read()
  name=re.search(r"^Name:\s*(.+)$",data,re.M)
  sw=re.search(r"^VmSwap:\s*(\d+)\s+kB",data,re.M)
  rss=re.search(r"^VmRSS:\s*(\d+)\s+kB",data,re.M)
  swap=int(sw.group(1)) if sw else 0
  if not swap:continue
  rec={"name":name.group(1)[:45] if name else "unknown",
       "swap_mib":round(swap/1024,1),
       "rss_mib":round((int(rss.group(1)) if rss else 0)/1024,1)}
  if rec["name"] in ("kvm","qemu-system-x86","qemu-system-x86_64"):
   with open(entry.path+"/cmdline","rb") as f:raw=f.read(250000).decode("utf-8","replace").replace("\x00"," ")
   m=re.search(r"(?:^|\s)-id\s+(\d+)(?:\s|$)",raw)
   if m:rec["vmid"]=int(m.group(1))
  rows.append(rec)
 except (OSError,PermissionError,UnicodeError):continue
rows.sort(key=lambda d:d["swap_mib"],reverse=True)
out={"utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
     "top_swapped_processes":rows[:22],
     "process_swap_total_mib":round(sum(x["swap_mib"] for x in rows),1)}
print("JNS_NODEA_SWAP_REPORT="+json.dumps(out,sort_keys=True))
'''
def main():
 b=base64.b64encode(REMOTE.encode()).decode()
 args=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea",shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+b+"'))"])]
 try:p=subprocess.run(args,capture_output=True,text=True,timeout=50)
 except (OSError,subprocess.TimeoutExpired):print("JNS_NODEA_SWAP_UNAVAILABLE=transport");return
 if p.returncode:print("JNS_NODEA_SWAP_UNAVAILABLE=remote_exit");return
 for line in p.stdout.splitlines():
  if line.startswith("JNS_NODEA_SWAP_REPORT="):print(line)
if __name__=="__main__":main()
