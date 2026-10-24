#!/usr/bin/env python3
"""Root-owned JNS VM905 heating promotion gate. INSTALL MANUALLY AFTER REVIEW.

This program is designed to live at /usr/local/sbin/jns-heating-promote on
Node B, owned by root:root mode 0700 (not writable by github-runner).
It is NOT called by repository Actions workflows. Operator approval is a
root-owned, single-use file, created locally outside GitHub.
Never accepts a script, path, VM ID or arbitrary command from the caller.

It only *assesses* deployment readiness in --audit mode. Activation is
intentionally unavailable until the HA runtime restart/check rollback
controller has been implemented and separately reviewed.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

VMID="905"
APPROVAL=Path("/etc/jns/heating-v035-approval.json")
STAGE="v035-20261024T162546Z-43b0f6ec"
EXPECTED_CANDIDATE_SHA="43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c"
EXPECTED_SOURCE_SHA="44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8"

def check(value, msg):
    if not value: raise RuntimeError(msg)

def approval_audit():
    check(os.geteuid()==0, "root privileges required")
    check(APPROVAL.is_file() and not APPROVAL.is_symlink(), "operator approval absent")
    stat=APPROVAL.stat()
    check(stat.st_uid==0 and stat.st_mode & 0o077==0, "approval permissions invalid")
    content=json.loads(APPROVAL.read_text())
    check(set(content)=={"stage_id","candidate_sha256","intent","operator_window"},
          "unknown approval fields")
    check(content["stage_id"]==STAGE and content["candidate_sha256"]==EXPECTED_CANDIDATE_SHA,
          "candidate/approval mismatch")
    check(content["intent"]=="assess_only", "promotion is not yet authorised")
    check(isinstance(content["operator_window"],str) and content["operator_window"],
          "explicit operator window required")
    return {"approval":"assess_only","stage_id":STAGE}

def main():
    check(len(sys.argv)==2 and sys.argv[1]=="--audit", "only --audit is implemented")
    a=approval_audit()
    # No QGA executable/script injection: only fixed, read-only vm status.
    p=subprocess.run(["qm","status",VMID],check=True,text=True,capture_output=True,timeout=15)
    check("status: running" in p.stdout, "VM905 not running")
    print("JNS_HEATING_PROMOTION_LOCKED", json.dumps({**a,"vm":"905",
           "production_activation_enabled":False,"runtime_restart_enabled":False},sort_keys=True))

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("JNS_HEATING_GATE_BLOCKED",type(exc).__name__,str(exc)[:120])
        raise SystemExit(2)
