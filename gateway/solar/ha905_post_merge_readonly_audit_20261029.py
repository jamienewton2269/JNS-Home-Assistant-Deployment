#!/usr/bin/env python3
"""JNS VM905-only post-merger assessment, read-only, redacted and non-disruptive.

Never touches source VMs, actuators, Home Assistant REST services or tokens.
Runs on the authorized Node C GitHub runner, through existing SSH/QGA.
Only coarse counts and booleans may leave the HA Core guest.
"""
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import time

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=6"]
VM = "905"
MARKER = "JNS_HA905_PRIVATE_HEALTH_SUMMARY="
INNER = r"""
import json,pathlib,re
from collections import Counter
root=pathlib.Path('/config')
storage=root/'.storage'
topics={'security':('security','alarm','doorbell','tamper'),
        'heating':('heat','therm','comfort'),
        'lighting':('lux','dusk','light'),
        'fans':('fan','humidity','bathroom','wc'),
        'cameras':('camera','onvif','webrtc','tapo'),
        'mobile':('mobile','notify','notification')}
interesting=('esphome','mqtt','mobile_app','onvif','mpd','wyoming','tuya_local',
             'tuya','hacs','lyric','matter','remote_homeassistant','hassio')
domains=('automation','alarm_control_panel','siren','binary_sensor','sensor',
         'climate','fan','light','camera','media_player','switch','input_boolean',
         'input_number','input_text','input_select','input_datetime','timer',
         'counter','script','notify','button','event')
def load(name):
 p=storage/name
 try:
  if p.is_symlink() or not p.is_file():return None
  return json.loads(p.read_text())
 except (OSError,ValueError,TypeError):return None
entries=load('core.config_entries')
entities=load('core.entity_registry')
devices=load('core.device_registry')
e=(entries or {}).get('data',{}).get('entries',[])
r=(entities or {}).get('data',{}).get('entities',[])
d=(devices or {}).get('data',{}).get('devices',[])
if not isinstance(e,list) or not isinstance(r,list) or not isinstance(d,list):
 raise SystemExit(71)
by_integration=Counter(str(x.get('domain')) for x in e if isinstance(x,dict) and not x.get('disabled_by'))
disabled=Counter(str(x.get('domain')) for x in e if isinstance(x,dict) and x.get('disabled_by'))
registered_ids={x.get('entity_id') for x in r if isinstance(x,dict) and isinstance(x.get('entity_id'),str)}
by_domain=Counter(s.split('.',1)[0] for s in registered_ids)
disabled_entities=Counter(str(x.get('entity_id','')).split('.',1)[0] for x in r
                          if isinstance(x,dict) and x.get('disabled_by'))
by_platform=Counter(str(x.get('platform')) for x in r if isinstance(x,dict))
cfg=root/'configuration.yaml'
try:
 cfg_text=cfg.read_text() if cfg.is_file() and not cfg.is_symlink() else ''
except OSError:cfg_text=''
packages=root/'packages'
pkg_files=[p for p in packages.glob('*.yaml') if p.is_file() and not p.is_symlink()] if packages.is_dir() and not packages.is_symlink() else []
alarm_packages=[p for p in pkg_files if any(k in p.stem.lower() for k in ('security','alarm'))]
alarm_declared=False
security_automation_initial_disabled_count=0
for p in alarm_packages:
 try:
  text=p.read_text(errors='replace')
  alarm_declared=alarm_declared or bool(re.search(r'(?m)^alarm_control_panel\s*:',text))
  security_automation_initial_disabled_count+=len(re.findall(r'(?m)^\s*initial_state\s*:\s*false\b',text))
 except OSError:pass
topic_counts={k:sum(any(w in p.stem.lower() for w in words) for p in pkg_files)
              for k,words in topics.items()}
storage_helpers=('input_boolean','input_number','input_select','input_text',
                 'input_datetime','timer','counter','schedule')
helper_files={x:bool((storage/x).is_file() and not (storage/x).is_symlink())
              for x in storage_helpers}
pattern=re.compile(r'\b(?:alarm_control_panel|automation|binary_sensor|button|camera|climate|cover|event|fan|input_boolean|input_datetime|input_number|input_select|input_text|light|lock|media_player|number|scene|script|select|sensor|siren|switch|timer)\.[a-z][a-z0-9_]*\b')
files=[root/x for x in ('automations.yaml','scripts.yaml','scenes.yaml','ui-lovelace.yaml')]
files.extend(pkg_files[:120])
files.extend([p for p in storage.glob('lovelace*') if p.is_file() and not p.is_symlink()][:35])
ref_counts={}
for group,selected in (('automations',files[:3]),('packages',pkg_files[:120]),
                       ('dashboards',files[3:4]+[p for p in storage.glob('lovelace*') if p.is_file() and not p.is_symlink()][:35])):
 refs=set()
 scanned=0
 for p in selected:
  try:
   if not p.is_file() or p.is_symlink() or p.stat().st_size>1600000:continue
   refs.update(pattern.findall(p.read_text(errors='replace')))
   scanned+=1
  except (OSError,UnicodeError):pass
 missing=refs-registered_ids
 ref_counts[group]={'files_scanned':scanned,'distinct_references':len(refs),
                    'not_in_registry_approx':len(missing),
                    'missing_by_domain':dict(sorted(Counter(x.split('.')[0] for x in missing).items()))}
# Log-tail aggregation: no raw messages or identifiers are allowed to leave VM905.
log=root/'home-assistant.log'
log_summary={'available':False}
try:
 if log.is_file() and not log.is_symlink():
  with log.open('rb') as f:
   f.seek(max(0,log.stat().st_size-1048576))
   raw=f.read(1048576).decode(errors='replace')
  lines=raw.splitlines()
  relevant=[s for s in lines if re.search(r'(?i)\b(error|warning|exception|failed)\b',s)]
  causes=Counter()
  for s in relevant:
   key=next((key for key,terms in topics.items()
            if any(t in s.lower() for t in terms)), 'other')
   causes[key]+=1
  log_summary={'available':True,'tail_kib':min(log.stat().st_size//1024,1024),
               'warning_error_lines':len(relevant),
               'topics':dict(sorted(causes.items()))}
except OSError:pass
out={'read_only':True,'registry_readable':entries is not None and entities is not None,
     'integration_count':len(e),'enabled_integrations':dict((k,by_integration[k]) for k in interesting if by_integration[k]),
     'disabled_integrations':dict((k,disabled[k]) for k in interesting if disabled[k]),
     'registered_entities':len(r),'registered_devices':len(d),
     'entity_domain_counts':{k:by_domain[k] for k in domains if by_domain[k]},
     'disabled_entity_domain_counts':{k:disabled_entities[k] for k in domains if disabled_entities[k]},
     'security_esphome_entities':by_platform['esphome'],
     'alarm_control_panel_registered':by_domain['alarm_control_panel']>0,
     'alarm_control_panel_declared_in_security_yaml':alarm_declared,
     'security_yaml_automations_initially_disabled':security_automation_initial_disabled_count,
     'yaml_packages':len(pkg_files),'package_topics_filename_only':topic_counts,
     'ui_helper_storage_presence':helper_files,
     'packages_configured':bool(re.search(r'(?m)^\s*packages\s*:\s*!include_dir_',cfg_text)),
     'reference_scan_not_runtime_states':ref_counts,
     'log_tail_counters_not_raw_logs':log_summary,
     'live_state_api_checked':False}
print('JNS_HA905_PRIVATE_HEALTH_SUMMARY='+json.dumps(out,sort_keys=True),flush=True)
"""

def run(argv, timeout=30):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None

def ssh(node, argv, timeout=35):
    return run(SSH + [node, shlex.join(argv)], timeout)

def guest(node, argv, timeout=110):
    p=ssh(node, ["qm","guest","exec",VM,"--timeout","180","--",*argv],45)
    if not p or p.returncode:return None
    try:j=json.loads(p.stdout)
    except (ValueError,TypeError):return None
    deadline=time.monotonic()+timeout
    while not j.get("exited") and time.monotonic()<deadline:
        if not j.get("pid"):return None
        time.sleep(.7)
        p=ssh(node,["qm","guest","exec-status",VM,str(j["pid"])],28)
        if not p or p.returncode:return None
        try:j=json.loads(p.stdout)
        except (ValueError,TypeError):return None
    return j if j.get("exited") and not j.get("out-truncated") else None

def running_hosts():
    matching=[]
    checked={}
    for node in ("nodea","nodeb"):
        state=ssh(node,["qm","status",VM],23)
        checked[node]="reachable" if state else "unreachable_or_unlisted"
        if not state or state.returncode or state.stdout.strip()!="status: running":continue
        cfg=ssh(node,["qm","config",VM],23)
        if not cfg or cfg.returncode:
            checked[node]="identity_unverified"
            continue
        m=re.search(r"(?m)^name:\s*([^\s]+)",cfg.stdout)
        if not m or not (m.group(1)=="ha-s2-general" or m.group(1).startswith("ha-general")):
            checked[node]="unknown_running_vm905_identity"
            continue
        checked[node]="verified_running_vm905"
        matching.append(node)
    return matching,checked

def main():
    if "--selftest" in sys.argv:
        compile(INNER, "ha905_guest_readonly", "exec")
        assert re.search(r"(?m)^name:\s*([^\s]+)","name: ha-general")
        assert len(set(("nodea","nodeb")))==2
        assert "vm906" not in INNER and "qm start" not in INNER and "services/" not in INNER
        print("JNS_HA905_AUDIT_OFFLINE_STATIC=pass")
        return 0
    if os.uname().nodename.split(".")[0]!="nodec":
        print("JNS_HA905_AUDIT_BLOCKED=runner_identity")
        return 1
    hosts,checked=running_hosts()
    if len(hosts)!=1:
        print("JNS_HA905_AUDIT_BLOCKED="+("multiple_active_hosts" if len(hosts)>1 else "no_verified_active_vm905"))
        print("JNS_HA905_AUDIT_HOST_STATE="+json.dumps(checked,sort_keys=True))
        return 1
    host=hosts[0]
    out={"source":"live_guest_read_only","vm":905,"active_proxmox_host":host}
    info=guest(host,["ha","core","info"],95)
    out["core_cli_info_ok"]=bool(info and info.get("exitcode")==0)
    b64=base64.b64encode(INNER.encode()).decode("ascii")
    inner=guest(host,["docker","exec","homeassistant","python3","-c",
                      "exec(__import__('base64').b64decode("+repr(b64)+"))"],120)
    if not inner or inner.get("exitcode")!=0:
        code=("qga_transport_or_truncation" if inner is None else
              "guest_python_exit_"+str(inner.get("exitcode","unknown")))
        if inner:
            err=str(inner.get("err-data") or "")
            detail=next((key for key in ("SyntaxError","NameError","TypeError","ValueError",
                                        "KeyError","OSError","PermissionError","JSONDecodeError")
                         if key in err), "unclassified")
            code+="_"+detail
        print("JNS_HA905_AUDIT_BLOCKED=core_registry_read_unavailable")
        print("JNS_HA905_AUDIT_DIAGNOSTIC="+code)
        print("JNS_HA905_AUDIT_META="+json.dumps(out,sort_keys=True))
        return 1
    rows=[x[len(MARKER):] for x in str(inner.get("out-data") or "").splitlines() if x.startswith(MARKER)]
    try:
        if len(rows)!=1:raise ValueError("missing")
        summary=json.loads(rows[0])
        if not summary.get("read_only") or not summary.get("registry_readable"):raise ValueError("invalid")
    except (ValueError,TypeError,AttributeError):
        print("JNS_HA905_AUDIT_BLOCKED=summary_not_verified")
        return 1
    out["findings"]=summary
    # Core syntax verification and bounded Docker log read: both are read-only.
    # Raw logs may contain private details; categorise in memory and emit counts only.
    core_check=guest(host,["ha","core","check"],175)
    out["core_config_validation"]=( "unverified_transport" if core_check is None else
                                     "passed" if core_check.get("exitcode")==0 else
                                     "failed_exit_"+str(core_check.get("exitcode","unknown")) )
    logs=guest(host,["docker","logs","--tail","120","homeassistant"],75)
    if logs and logs.get("exitcode")==0:
        raw=str(logs.get("out-data") or "")+"\n"+str(logs.get("err-data") or "")
        lines=[s for s in raw.splitlines() if re.search(r"(?i)\b(error|warning|exception|failed)\b",s)]
        topics={"security":("alarm","esphome","doorbell","tamper"),
                "heating":("heat","climate","thermostat"),
                "lighting":("light","lux","zigbee"),
                "network":("mqtt","connection","unavailable"),
                "camera":("camera","onvif","stream"),
                "automation":("automation","template"),
                "mobile":("notify","mobile_app","notification")}
        counts={k:0 for k in topics}
        other=0
        for line in lines:
            t=line.lower()
            label=next((k for k,words in topics.items() if any(w in t for w in words)),None)
            if label:counts[label]+=1
            else:other+=1
        severity={"error":0,"warning":0,"critical":0}
        signature_names=("TemplateError","UndefinedError","TimeoutError",
                         "ConnectionError","ConfigEntryNotReady","HomeAssistantError",
                         "Failed to call service","not found","unavailable",
                         "already running","already configured","failed to connect")
        signatures={key:sum(key.lower() in line.lower() for line in lines) for key in signature_names}
        for line in lines:
            upper=line.upper()
            for level in severity:
                if re.search(r"\b"+level.upper()+r"\b",upper):
                    severity[level]+=1
        # Group fixed, documented logger families; never print raw logger IDs.
        allowed_components=frozenset(("automation","template","esphome","mqtt","light",
            "binary_sensor","sensor","recorder","mobile_app","climate","alarm_control_panel",
            "script","camera","onvif","tuya","tuya_local","hassio","media_player",
            "websocket_api","http","frontend","input_boolean","input_number",
            "input_datetime","input_select","switch","fan","timer","device_tracker"))
        origin_counts={}
        for line in lines:
            m=re.search(r"\\[([^\\]]{1,110})\\]",line)
            # Accept only Home Assistant module logs, never a user-defined ID.
            domain="unknown"
            if m:
                value=m.group(1)
                if value.startswith("homeassistant.components."):
                    parts=value.split(".")
                    domain=parts[2] if len(parts)>2 and parts[2] in allowed_components else "other_ha_component"
                elif value.startswith("custom_components."):
                    domain="custom_component"
                elif value.startswith("homeassistant."):
                    domain="homeassistant_core"
                else:
                    domain="other_logger"
            origin_counts[domain]=origin_counts.get(domain,0)+1
        out["core_docker_log_tail_error_warning_counts"]={"total":len(lines),
                "severity_keyword_count":severity,
                "allowlisted_error_signatures":{k:v for k,v in signatures.items() if v},
                "source_component_counts":dict(sorted(origin_counts.items())),
                "traceback_lines":sum("Traceback" in line for line in raw.splitlines()),
                "by_topic":{k:v for k,v in counts.items() if v},
                "other":other,"raw_logs_exposed":False}
    else:
        out["core_docker_log_tail_error_warning_counts"]={"available":False}
    print("JNS_HA905_POST_MERGER_READONLY_AUDIT="+json.dumps(out,sort_keys=True),flush=True)
    print("JNS_HA905_PHYSICAL_OUTPUTS_UNCHANGED=yes",flush=True)
    return 0 if out["core_cli_info_ok"] else 1

if __name__=="__main__":raise SystemExit(main())
