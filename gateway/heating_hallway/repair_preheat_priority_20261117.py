#!/usr/bin/env python3
"""Fix HA-General morning preheat precedence, conservatively and atomically.

Target only the audited VM905 heating package. No secrets logged.
Never turn on the boiler or change thermostat helpers in this deployment.
"""
import hashlib, json, shlex, subprocess, sys, time
import yaml
HOST=["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
      "-o","HostKeyAlias=nodeb.home.arpa","-o","ConnectTimeout=7","root@10.10.110.12"]
ROOT="/mnt/data/supervisor/homeassistant/packages"
PATH=ROOT+"/jns_heating_predictive_schedule.yaml"
EXPECTED="82b15336bfcd1f7895094fbaead1a455fa59140fc04c3ad99a28e92fd534f5fc"
BACKUP=PATH+".pre-morning-priority-20261117.bak"
STAGE=PATH+".morning-priority-stage"

def run_guest(args,stdin=None,timeout=150):
    q=["qm","guest","exec","905"]
    if stdin is not None:
        q+=["--pass-stdin","1"]
    q+=["--"]+args
    r=subprocess.run(HOST+[shlex.join(q)],input=stdin,text=True,
                     capture_output=True,timeout=20)
    if r.returncode:
        raise RuntimeError("Node B transport failed: "+r.stderr[:250])
    try:j=json.loads(r.stdout)
    except Exception as exc:raise RuntimeError("Guest-agent output invalid") from exc
    for _ in range(max(1,timeout//2)):
        if j.get("exited"):break
        pid=j.get("pid")
        if not isinstance(pid,int):
            raise RuntimeError("Missing guest-agent process ID: "+repr(list(j)))
        time.sleep(2)
        x=subprocess.run(HOST+[shlex.join(["qm","guest","exec-status","905",str(pid)])],
                         capture_output=True,text=True,timeout=15)
        if x.returncode:raise RuntimeError("Guest status poll failed")
        j=json.loads(x.stdout)
    if not j.get("exited"):raise RuntimeError("Guest command timed out")
    if j.get("exitcode") != 0:
        raise RuntimeError("Guest command failed: "+str(j.get("err-data",""))[:300])
    if j.get("out-truncated"):raise RuntimeError("Guest output truncated")
    return j.get("out-data","")

def guest_shell(cmd,stdin=None,timeout=150):
    return run_guest(["/bin/sh","-c",cmd],stdin=stdin,timeout=timeout)

def change_once(contents,old,new,tag):
    n=contents.count(old)
    if n!=1:raise RuntimeError(tag+" unsafe unexpected matches: "+str(n))
    return contents.replace(old,new,1)

def main():
    raw=run_guest(["/bin/cat",PATH]).encode("latin1").decode("utf-8")
    h=hashlib.sha256(raw.encode()).hexdigest()
    if h!=EXPECTED:
        raise RuntimeError("Live schedule differs from inspected SHA; no changes made")
    before=yaml.safe_load(raw)
    target=next(a for a in before["automation"] if a.get("id")=="jns_heating_alarm_predictive_target_v1")
    desired=next(v["variables"]["desired"] for v in target["actions"] if isinstance(v,dict)
                 and "variables" in v and "desired" in v["variables"])
    # Move bedtime behind the MORNING comfort/prioritised preheat branches
    # while retaining explicit suspension, new manual holds and away/fireplace.
    bedtime="""            {% elif is_state('input_boolean.general_bedtime_mode','on') %}
              18
"""
    fireplace="""            {% elif is_state('binary_sensor.jns_fireplace_override_safe','on') %}
"""
    daytime="""            {% elif minutes_now | int >= 600 and minutes_now | int < 1140 %}
              {{ user_target }}
"""
    markers=("is_state('input_boolean.general_bedtime_mode','on')",
             "is_state('binary_sensor.jns_fireplace_override_safe','on')",
             "minutes_now | int >= 600 and minutes_now | int < 1140")
    if not all(marker in desired for marker in markers):
        raise RuntimeError("Live schedule lacks one of the expected branches")
    if not (desired.index(markers[0])<desired.index(markers[1])<desired.index(markers[2])):
        raise RuntimeError("Unexpected original priority order")
    fixed=change_once(raw,bedtime,"","bedtime removal")
    fixed=change_once(fixed,daytime,daytime+bedtime,"morning priority insertion")
    # Reject unrealistically short learning estimates (5-7 minutes for a
    # multi-degree temperature gap). Until five validated hallway cycles
    # exist, continue the 120-minute safe fallback.
    model_original="""          {% set learned = states('sensor.jns_hallway_adaptive_warmup_minutes') | int(120) %}
          {% if hall is not none and hall >= target - 0.2 %}
            0
          {% elif hall is not none and ready and 5 <= learned <= 360 and
                  state_attr('sensor.jns_hallway_adaptive_warmup_minutes','source_epoch') == 'hallway-precision-v1' %}
            {{ learned }}
          {% else %}
            120
          {% endif %}"""
    model_updated="""          {% set learned = states('sensor.jns_hallway_adaptive_warmup_minutes') | int(120) %}
          {% set cycles = states('input_number.jns_hallway_warmup_observations') | int(0) %}
          {% set minimum_plausible = [15, ((target - hall) * 12) | round(0, 'ceil') | int] | max if hall is not none else 120 %}
          {% if hall is not none and hall >= target - 0.2 %}
            0
          {% elif hall is not none and ready and cycles >= 5 and
                  minimum_plausible <= learned <= 360 and
                  state_attr('sensor.jns_hallway_adaptive_warmup_minutes','source_epoch') == 'hallway-precision-v1' %}
            {{ learned }}
          {% else %}
            120
          {% endif %}"""
    fixed=change_once(fixed,model_original,model_updated,"hallway warmup validation")
    # Ensure prediction explanation matches stricter actual gating.
    original_attribute="""            {% if state_attr('sensor.jns_hallway_adaptive_warmup_minutes','ready') == true
                  and state_attr('sensor.jns_hallway_adaptive_warmup_minutes','source_epoch') == 'hallway-precision-v1' %}"""
    updated_attribute="""            {% if state_attr('sensor.jns_hallway_adaptive_warmup_minutes','ready') == true
                  and states('input_number.jns_hallway_warmup_observations') | int(0) >= 5
                  and state_attr('sensor.jns_hallway_adaptive_warmup_minutes','source_epoch') == 'hallway-precision-v1' %}"""
    fixed=change_once(fixed,original_attribute,updated_attribute,"model evidence label")
    after=yaml.safe_load(fixed)
    assert len(after["automation"])==len(before["automation"])
    d=next(a for a in after["automation"] if a.get("id")=="jns_heating_alarm_predictive_target_v1")
    template=next(v["variables"]["desired"] for v in d["actions"] if "variables" in v and "desired" in v["variables"])
    expected=["jns_heating_automatic_override", "alarm == 'armed_away'",
              "alarm not in ['disarmed', 'armed_home']", "jns_heating_manual_setpoint_hold",
              "jns_fireplace_override_safe", "240 <= minutes_now",
              "minutes_now | int >= 600", "general_bedtime_mode"]
    indices=[template.index(a) for a in expected]
    if indices!=sorted(indices):
        raise RuntimeError("Heating priority regression")
    # Verify the original package has not changed since the read.
    if run_guest(["/usr/bin/sha256sum",PATH]).split()[0]!=h:
        raise RuntimeError("Concurrent change detected; abort")
    if guest_shell("test -e "+shlex.quote(BACKUP)+" && echo EXISTS || echo NEW").strip()!="NEW":
        raise RuntimeError("Backup path exists; refusing overwrite")
    guest_shell("cat > "+shlex.quote(STAGE),stdin=fixed)
    if run_guest(["/usr/bin/sha256sum",STAGE]).split()[0] != hashlib.sha256(fixed.encode()).hexdigest():
        raise RuntimeError("Staged checksum mismatch")
    guest_shell("cp -p "+shlex.quote(PATH)+" "+shlex.quote(BACKUP)+" && cp -p "+
                shlex.quote(STAGE)+" "+shlex.quote(PATH))
    print("PACKAGE_UPDATED_SHA256",hashlib.sha256(fixed.encode()).hexdigest()[:18])
    print("BACKUP_CREATED",BACKUP)
    print("PRIORITY_VALIDATED: manual > alarm > fireplace > morning comfort > bedtime")
    print("MODEL_VALIDATED: require five actual hallway cycles and plausible heating time")
    print("HA_CORE_CHECK_START")
    try:
        check=run_guest(["/bin/sh","-c","ha core check"],timeout=240)
        print("HA_CORE_CHECK_SUCCESS",check[-240:])
    except Exception:
        guest_shell("cp -p "+shlex.quote(BACKUP)+" "+shlex.quote(PATH))
        print("CONFIG_FAILED_ROLLED_BACK")
        raise
    print("SCHEDULE_READY_FOR_RESTART")
if __name__=="__main__":
    try:main()
    except Exception as e:print("REPAIR_FAILED",type(e).__name__,str(e)[:280]);sys.exit(1)
