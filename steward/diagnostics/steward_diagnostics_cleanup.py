#!/usr/bin/env python3
"""Delete *acknowledged* report content from a private diagnostics repository. Git history remains."""
import argparse,datetime,json,pathlib,sys,urllib.request,urllib.error
REPO="jamienewton2269/JNS-Steward-Diagnostics"
TOKEN="/etc/jns-steward/github-diagnostics.token"
def call(path,token,method="GET",data=None):
 req=urllib.request.Request("https://api.github.com"+path,method=method,data=(json.dumps(data).encode() if data else None),
 headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"JNS-Steward/0.1","Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
def main():
 p=argparse.ArgumentParser();p.add_argument("--ack-dir",default="/var/lib/jns-steward/upload-acks");p.add_argument("--min-age-hours",type=int,default=48);a=p.parse_args()
 if a.min_age_hours<1:raise ValueError("min age must be >= 1h")
 tp=pathlib.Path(TOKEN)
 if tp.stat().st_mode & 0o077:raise RuntimeError("Token file must be mode 0600")
 token=tp.read_text().strip()
 if call("/repos/"+REPO,token).get("private") is not True:raise RuntimeError("Repository must remain private")
 now=datetime.datetime.now(datetime.timezone.utc)
 for f in pathlib.Path(a.ack_dir).glob("*.json"):
  ack=json.loads(f.read_text())
  if ack.get("repo")!=REPO or ack.get("status")!="reviewed":continue
  uploaded=datetime.datetime.strptime(ack["uploaded_at"],"%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
  if (now-uploaded).total_seconds()<a.min_age_hours*3600:continue
  path=ack["path"]
  if not path.startswith("inbox/") or ".." in path:continue
  data={"message":"housekeeping: remove reviewed diagnostics","sha":ack["sha"]}
  call("/repos/"+REPO+"/contents/"+path,token,method="DELETE",data=data)
  ack.update(status="removed_from_head",removed_at=now.isoformat(),history_warning="Old content remains in Git history")
  f.write_text(json.dumps(ack,indent=2)+"\n")
  print("Removed from branch head:",path)
if __name__=="__main__":
 try: main()
 except Exception as e:print(f"ERROR: {type(e).__name__}: {e}",file=sys.stderr);sys.exit(1)
