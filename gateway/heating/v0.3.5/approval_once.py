#!/usr/bin/env python3
"""One-time LOCAL-ROOT maintenance approval for JNS heating v0.3.5.

Not a GitHub workflow and NEVER run by github-runner.
"""
from datetime import datetime,timedelta,timezone
import argparse,json,os,re
from pathlib import Path
import stat
import sys
import tempfile
from promotion_policy import STAGE_ID,CANDIDATE_SHA,APPROVAL_OPERATION
from root_owned_promotion import APPROVAL

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--confirm-heating-outage",action="store_true")
    parser.add_argument("--job-id",required=True)
    args=parser.parse_args()
    if not args.confirm_heating_outage or os.geteuid()!=0:
        raise SystemExit("Denied: local root maintenance acknowledgement required")
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-heating-v035-[0-9a-f]{6}",args.job_id):
        raise SystemExit("Denied: immutable job identifier invalid")
    if not sys.stdin.isatty():
        raise SystemExit("Denied: interactive local root approval required")
    response=input("Type APPROVE VM905 HEATING RESTART to permit one restart: ")
    if response!="APPROVE VM905 HEATING RESTART":
        raise SystemExit("Denied: maintenance confirmation not provided")
    parent=APPROVAL.parent
    if not parent.exists() or parent.is_symlink():
        raise SystemExit("Denied: root-private approval directory not installed")
    metadata=parent.stat()
    if metadata.st_uid!=0 or stat.S_IMODE(metadata.st_mode)!=0o700:
        raise SystemExit("Denied: approval directory must be root-owned 0700")
    if APPROVAL.exists():
        raise SystemExit("Denied: existing approval must be manually reviewed")
    expires=datetime.now(timezone.utc)+timedelta(minutes=10)
    record={
        "operation":APPROVAL_OPERATION,"stage_id":STAGE_ID,"job_id":args.job_id,
        "candidate_sha":CANDIDATE_SHA,
        "expires_utc":expires.isoformat(),
        "heating_outage_approved":True,
    }
    fd,name=tempfile.mkstemp(prefix=".jns-heating-approval-",dir=parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(record,f,sort_keys=True)
            f.write("\n")
            f.flush();os.fsync(f.fileno())
        if APPROVAL.exists():
            raise RuntimeError("concurrent local approval")
        os.rename(name,APPROVAL)
    finally:
        if os.path.exists(name):os.unlink(name)
    print("JNS_HEATING_LOCAL_APPROVAL_CREATED",STAGE_ID,"expires",expires.isoformat())

if __name__=="__main__":
    main()
