#!/usr/bin/env python3
"""Read-only rendered display capture for JNS HA-Security VM906.
Private PNG artifact (not logs, not repository commit). Proxmox QEMU HMP
screendump captures framebuffer only; does not send keys/change VM state.
"""
import base64,os,shlex,subprocess,sys,pathlib
REMOTE=r'''
import os,pathlib,re,struct,subprocess,sys,zlib
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":sys.exit(65)
p=subprocess.run(["qm","status","906"],capture_output=True,text=True,timeout=10)
if p.returncode or p.stdout.strip()!="status: running":sys.exit(66)
q=subprocess.run(["qm","config","906"],capture_output=True,text=True,timeout=10)
if q.returncode or not re.search(r"^name:\s+ha-security\s*$",q.stdout,re.M):sys.exit(67)
d=pathlib.Path("/var/lib/jns-solar/ha-security-906")
d.mkdir(mode=0o700,parents=True,exist_ok=True)
os.chmod(d,0o700)
ppm=d/"read-only-console.ppm"
if ppm.is_symlink():sys.exit(68)
if ppm.exists():ppm.unlink()
cmd=["pvesh","create","/nodes/nodea/qemu/906/monitor","--command","screendump "+str(ppm)]
out=subprocess.run(cmd,capture_output=True,text=True,timeout=22)
if out.returncode or not ppm.is_file() or ppm.is_symlink():sys.exit(69)
raw=ppm.read_bytes()
ppm.unlink()
if len(raw)>15*1024**2 or not raw.startswith(b"P6"):sys.exit(70)
index=0
def token():
 global index
 while index<len(raw):
  if raw[index]==35:
   while index<len(raw) and raw[index]!=10:index+=1
  if index<len(raw) and raw[index] in b" \t\r\n":index+=1;continue
  break
 beg=index
 while index<len(raw) and raw[index] not in b" \t\r\n":index+=1
 return raw[beg:index]
if token()!=b"P6":sys.exit(71)
w=int(token());h=int(token());maxval=int(token())
if not(10<=w<=4096 and 10<=h<=2160 and maxval==255):sys.exit(72)
if raw[index:index+1] not in (b"\n",b" ",b"\r",b"\t"):sys.exit(73)
index+=1
rgb=raw[index:]
if len(rgb)!=(w*h*3):sys.exit(74)
def chunk(name,data):
 return struct.pack(">I",len(data))+name+data+struct.pack(">I",zlib.crc32(name+data)&0xffffffff)
scan=b"".join(b"\x00"+rgb[i*w*3:(i+1)*w*3] for i in range(h))
png=(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))+
 chunk(b"IDAT",zlib.compress(scan,8))+chunk(b"IEND",b""))
sys.stdout.buffer.write(png)
'''
def fail(s):
 print("JNS_VM906_CONSOLE_CAPTURE_BLOCKED="+s,flush=True)
 raise SystemExit(1)
def main():
 if os.uname().nodename.split(".")[0]!="nodec":fail("must_run_nodec")
 dest=pathlib.Path(os.environ.get("RUNNER_TEMP","/tmp"))/"jns-ha-security-console.png"
 if dest.exists():fail("screenshot_collision")
 encoded=base64.b64encode(REMOTE.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea",
 shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
 try:r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=40)
 except (OSError,subprocess.TimeoutExpired):fail("source_remote_timeout")
 if r.returncode or not r.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
  fail("source_hmp_screenshot_unavailable")
 dest.write_bytes(r.stdout)
 dest.chmod(0o600)
 print("JNS_VM906_DISPLAY_CAPTURE_SUCCEEDED=yes",flush=True)
 print("JNS_VM906_DISPLAY_CAPTURE_PRIVATE_ARTIFACT=yes",flush=True)
 print("JNS_VM906_DISPLAY_CAPTURE_BYTES="+str(len(r.stdout)),flush=True)
if __name__=="__main__":main()
