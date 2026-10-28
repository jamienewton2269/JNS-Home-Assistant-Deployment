#!/usr/bin/env python3
"""LOCAL INTERACTIVE ROOT ONLY: grant ONE VM905 v0.3.6 maintenance attempt.

Never called by GitHub Actions or remote queued jobs. Does not restart Core,
install privileges, issue HA API tokens or touch a Home Assistant instance.
"""
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile
from datetime import datetime,timedelta,timezone
from v036_release_policy import STAGE,JOB_TYPE,OPERATION,CANDIDATE,approve

DEST=Path("/etc/jns/heating-v036")

def private_create(path,data):
    fd,name=tempfile.mkstemp(prefix=".jns-v036-",dir=DEST)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(data,f,sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if path.exists() or path.is_symlink():
            raise RuntimeError("existing local authority file; investigate before retry")
        os.link(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def main():
    if os.geteuid()!=0 or not sys.stdin.isatty():
        raise SystemExit("DENIED: interactive local root required")
    if sys.argv!=[sys.argv[0],"--approve-once"]:
        raise SystemExit("DENIED: fixed --approve-once operation only")
    if DEST.is_symlink() or not DEST.is_dir():
        raise SystemExit("DENIED: root-owned approval directory absent")
    s=DEST.stat()
    if s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700:
        raise SystemExit("DENIED: approval directory ownership or mode changed")
    if any((DEST/name).exists() for name in ("job.json","approval.json")):
        raise SystemExit("DENIED: existing job/permit; inspect and clean up manually")
    print("VM905 is the active HA-General heating node. A Home Assistant CORE")
    print("restart interrupts all HA-General automations. Check live heating,")
    print("VM906 security fallback, maintenance window and recovery access first.")
    answer=input("Type APPROVE VM905 V036 CORE RESTART AND ROLLBACK: ")
    if answer!="APPROVE VM905 V036 CORE RESTART AND ROLLBACK":
        raise SystemExit("DENIED: local consent absent")
    now=datetime.now(timezone.utc)
    job_id=now.strftime("%Y%m%dT%H%M%SZ")+"-heating-v036-"+secrets.token_hex(3)
    job={"job_id":job_id,"job_type":JOB_TYPE,"stage_id":STAGE}
    permit={"job_id":job_id,"operation":OPERATION,"stage_id":STAGE,
            "candidate_sha256":CANDIDATE["thermal.py"],
            "heating_outage_approved":True,"consolidation_quiet_approved":True,
            "expires_utc":(now+timedelta(minutes=8)).isoformat()}
    approve(job,permit,now)
    private_create(DEST/"job.json",job)
    private_create(DEST/"approval.json",permit)
    print("JNS_V036_ROOT_PERMIT_LOCAL_ONLY "+STAGE+" expires "+
          permit["expires_utc"])
    print("Never paste this directory, Home Assistant tokens or permits into GitHub.")

if __name__=="__main__":
    main()
