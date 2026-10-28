#!/usr/bin/env python3
"""Manually approved Node C exclusive controller handover.

This is NOT a push-triggered script. No permanent source retirement.
If a stage fails after VM906 stopped, run the guarded exclusive-owner recovery.
"""
import os
import pathlib
import re
import subprocess
import sys

ROOT=pathlib.Path(__file__).parent
RECOVERY=pathlib.Path.home()/".local/share/jns-security-failback-20261028/auto_failback.py"
STEPS=[
 ("source_stop_with_two_timers","ha_security_vm906_guarded_stop_20261028.py",180),
 ("native_alarm_package_load","ha_security_native_load_after_stop_20261028.py",340),
 ("native_esphome_enrolment","ha906_to_905_esphome_enrol_guarded_20261028.py",460),
]
def emit(k,v):
 print("JNS_OPERATOR_HANDOVER_"+k+"="+str(v),flush=True)
def run(py,timeout):
 try:return subprocess.run(["python3",str(py)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def status_from_stdout(label,text):
 prefixes=("JNS_VM906_STOP_","JNS_VM906_FAILBACK_INTERLOCK=",
           "JNS_SECURITY_NATIVE_LOAD_","JNS_ENROL_",
           "JNS_HA906_SAFE_AUTO_FAILBACK_")
 for line in text.splitlines():
  if line.startswith(prefixes) and len(line)<1200 and not re.search(
    r"(?i)(noise_psk|password|bearer|token|private_blob|enrolment.json.*=)",line):
   print(line,flush=True)
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  emit("BLOCKED","wrong_runner");return 1
 if os.environ.get("JNS_ONSITE_OPERATOR_CONFIRMED")!="true":
  emit("BLOCKED","onsite_operator_confirmation_missing");return 1
 if os.environ.get("JNS_EMERGENCY_VM905_SUSPEND_APPROVED")!="true":
  emit("BLOCKED","emergency_exclusive_fencing_not_authorised");return 1
 if not RECOVERY.is_file() or RECOVERY.is_symlink():
  emit("BLOCKED","validated_recovery_not_installed");return 1
 prepared=ROOT/"ha906_nodec_auto_failback_20261028.py"
 if RECOVERY.read_bytes()!=prepared.read_bytes():
  emit("BLOCKED","recovery_source_hash_mismatch");return 1
 chk=run(RECOVERY,35) if False else None
 try:
  p=subprocess.run(["python3",str(RECOVERY),"--check"],capture_output=True,text=True,timeout=105)
 except (OSError,subprocess.TimeoutExpired):p=None
 if not p or p.returncode:
  emit("BLOCKED","recovery_gate_preflight_failed");return 1
 emit("PREFLIGHT","recovery_identity_and_target_access_passed")
 successful=False
 try:
  for label,name,timeout in STEPS:
   emit("STAGE",label)
   result=run(ROOT/name,timeout)
   if result:status_from_stdout(label,result.stdout)
   if not result or result.returncode:
    emit("BLOCKED",label+"_failed")
    return 1
   emit("STAGE_OK",label)
  successful=True
  emit("RESULT","VM905_ESPHome_enrolled_awaiting_physical_approval")
  return 0
 finally:
  if not successful:
   # Do not try to recover a running source or create a second owner.
   # The restore script itself checks source and target identity/state.
   try:
    rollback=subprocess.run(["python3",str(RECOVERY),"--restore"],
                          capture_output=True,text=True,timeout=255)
   except (OSError,subprocess.TimeoutExpired):rollback=None
   if rollback:
    status_from_stdout("rollback",rollback.stdout)
   emit("ROLLBACK",("exclusive_source_restored_or_still_live"
                    if rollback and rollback.returncode==0
                    else "NOT_CONFIRMED_OPERATOR_INTERVENTION_REQUIRED"))
if __name__=="__main__":sys.exit(main())
