#!/usr/bin/env python3
"""JNS VM905 Lux manual-off V2: guarded in-place patch, dry-run by default.
Existing package, lights, helpers, Bedtime, PIR and security remain intact.
"""
import copy, datetime, hashlib, json, os, re, sys, tempfile
from pathlib import Path
import yaml

ROOT=Path('/config')
AUTO=ROOT/'automations.yaml'
PKG=ROOT/'packages/jns_lux_manual_off_v1.yaml'
DASH=ROOT/'dashboards/testing.yaml'
SHARED='1791918795028'
MARK='- title: Lighting Settings\n  path: lighting-settings\n  icon: mdi:weather-sunny\n  cards:\n'
TAG='JNS_LUX_MANUAL_OFF_V2'
EVENING="""{{ is_state('sun.sun','below_horizon')
 or (state_attr('sun.sun','next_setting') is not none
     and 0 <= as_timestamp(state_attr('sun.sun','next_setting')) - as_timestamp(now()) <= 9000)
 or (has_value('sensor.jns_lighting_effective_lux')
     and states('sensor.jns_lighting_effective_lux') | float(999999)
        < states('input_number.general_outdoor_lighting_on_lux') | float(2500)) }}"""
RECORD="""{% set old = trigger.event.data.get('old_state') %}
{% set new = trigger.event.data.get('new_state') %}
{% set eid = trigger.event.data.get('entity_id','') %}
{% set dev = device_id(eid) if eid else none %}
{% set ls = (labels(eid) | list) if eid else [] %}
{% set ls = ls + ((labels(dev) | list) if dev else []) %}
{% set last = states('input_text.jns_lighting_last_decision') %}
{% set last_obj = states.input_text.jns_lighting_last_decision
    if states.input_text.jns_lighting_last_decision is defined else none %}
{% set controller_off = last_obj is not none
  and (' ' ~ eid ~ ' OFF ') in last
  and (as_timestamp(now()) - as_timestamp(last_obj.last_changed)) >= 0
  and (as_timestamp(now()) - as_timestamp(last_obj.last_changed)) < 45 %}
{{ old is not none and new is not none
   and old.state == 'on' and new.state == 'off'
   and (new.context.user_id is not none
        or (new.context.parent_id is none and not controller_off))
   and ('lighting_lux_controlled' in ls or
        eid in ['switch.general_kitchen_worktop_light',
                'switch.general_kitchen_radiator_light'])
   and 'purpose_protected_it' not in ls
   and 'purpose_fan' not in ls
   and 'purpose_grow_light' not in ls
   and eid != 'switch.0xa4c13837e231806e' }}"""
UI="""  - type: markdown
    content: >-
      **Lux manual-OFF protection:** Switching a Lux-controlled light OFF
      during the evening excludes only that light until next sunrise.
      Bedtime and security automations are separate.
      Held-off entities: {% set v=states('input_text.jns_lux_off_tonight_entities') %}
      {{ v.split('|') | join(', ') if v not in ['','unknown','unavailable'] else 'None' }}.
  - type: entities
    title: Lux Manual Override
    show_header_toggle: false
    entities:
      - entity: input_text.jns_lux_off_tonight_entities
        name: Lights held off tonight
      - entity: input_boolean.jns_lux_manual_hold_all
        name: Pause all Lux lighting
      - entity: script.jns_lux_resume_all
        name: Resume Lux control
"""
def require(ok,msg):
 if not ok: raise RuntimeError(msg)
def sha(x):return hashlib.sha256(x).hexdigest()
def splice(raw,fn):
 text=raw.decode()
 data=yaml.safe_load(text)
 require(isinstance(data,list),'Unexpected automations root')
 matching=[a for a in data if str(a.get('id'))==SHARED]
 require(len(matching)==1,'Main Lux controller ID mismatch')
 require(TAG not in str(matching[0]),'V2 already installed')
 modified=copy.deepcopy(matching[0])
 fn(modified)
 fragments=list(re.finditer(r"(?m)^- id: ['\"]?"+SHARED+r"['\"]?[ \t]*$",text))
 require(len(fragments)==1,'Main Lux raw splice ambiguous')
 s=fragments[0].start(); f=re.search(r'(?m)^- id:',text[fragments[0].end():])
 e=fragments[0].end()+f.start() if f else len(text)
 body=yaml.safe_dump([modified],sort_keys=False,allow_unicode=True,width=160)
 result=(text[:s]+body+text[e:]).encode()
 parsed=yaml.safe_load(result)
 require(sum(str(a.get('id'))==SHARED for a in parsed)==1,'Main controller damaged')
 return result
def edit_controller(a):
 seq=[x for x in a['actions'] if isinstance(x,dict) and 'repeat' in x]
 require(len(seq)==1,'Expected exactly one Lux repeat')
 steps=seq[0]['repeat']['sequence']
 gate=[x for x in steps if isinstance(x,dict) and 'if' in x and 'then' in x]
 require(len(gate)==1,'Existing manual OFF gate not found')
 branches=gate[0]['then'][0]['choose']
 off=branches[0]['sequence']
 require(off[0].get('action')=='homeassistant.turn_off','Expected original Lux OFF action')
 require(off[1].get('action')=='input_text.set_value','Expected original Lux decision marker')
 require(off[1].get('target',{}).get('entity_id')=='input_text.jns_lighting_last_decision','Unexpected marker helper')
 # Predeclare controller-originated OFF before Zigbee/MQTT reports its state.
 off[0],off[1]=off[1],off[0]
 a['description']=str(a.get('description',''))+' '+TAG+': declare OFF intent before MQTT actuation.'
def main():
 old={p:p.read_bytes() for p in (AUTO,PKG,DASH)}
 package=yaml.safe_load(old[PKG])
 require(isinstance(package,dict) and len(package.get('automation',[]))==2,
         'Existing V1 package topology changed')
 capture=next((x for x in package['automation']
    if x.get('id')=='jns_lux_record_manual_off_tonight_v1'),None)
 require(capture is not None,'Missing original capture automation')
 require(TAG not in str(capture),'V2 already installed')
 con=capture['conditions']
 require(con[0].get('entity_id')=='sun.sun' and con[0].get('state')=='below_horizon',
         'Existing dusk-only capture condition changed')
 require('new.context.parent_id is none' in str(con[1]),'Existing event/context condition changed')
 con[0]={'condition':'template','value_template':EVENING}
 con[1]={'condition':'template','value_template':RECORD}
 capture['description']=str(capture.get('description',''))+' '+TAG+'; dusk-before-sunset and controller-OFF intent attribution.'
 pbytes=yaml.safe_dump(package,sort_keys=False,allow_unicode=True,width=160).encode()
 abytes=splice(old[AUTO],edit_controller)
 dash=old[DASH].decode()
 require(dash.count(MARK)==1,'Lighting Settings view marker missing or duplicated')
 require('Lux Manual Override' not in dash,'Lighting Settings already modified')
 dbytes=dash.replace(MARK,MARK+UI,1).encode()
 for p,b in ((PKG,pbytes),(AUTO,abytes),(DASH,dbytes)):
  require(yaml.safe_load(b) is not None,'YAML parse failed '+p.name)
 new={AUTO:abytes,PKG:pbytes,DASH:dbytes}
 report={'files':{str(p):{'before':sha(old[p]),'after':sha(new[p])} for p in new},
         'controller_off_intent_precedes_action':True,'captures_pre_sunset':True,
         'existing_helpers_retained':True,'dashboard':'lighting-settings','core_restart_required':False}
 print('JNS_LUX_V2_PLAN '+json.dumps(report,sort_keys=True),flush=True)
 if '--apply' not in sys.argv:return
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 backup=ROOT/'.jns-backups'/('lux-manual-off-v2-'+stamp)
 backup.mkdir(parents=True,exist_ok=False)
 for p,b in old.items():
  dest=backup/('testing.yaml' if p==DASH else ('jns_lux_manual_off_v1.yaml' if p==PKG else p.name))
  dest.write_bytes(b);require(dest.read_bytes()==b,'Backup verify failed')
 changed=[]
 try:
  for p,b in new.items():
   require(p.read_bytes()==old[p],'Concurrent edit detected '+str(p))
   fd,name=tempfile.mkstemp(prefix='.jns-lux-v2-',dir=p.parent)
   try:
    with os.fdopen(fd,'wb') as o:o.write(b);o.flush();os.fsync(o.fileno())
    st=p.stat();os.chown(name,st.st_uid,st.st_gid);os.chmod(name,st.st_mode&0o777)
    os.replace(name,p);changed.append(p)
   finally:
    if os.path.exists(name):os.unlink(name)
 except BaseException:
  for p in reversed(changed):
   if p.read_bytes()==new[p]:p.write_bytes(old[p])
  raise
 print('JNS_LUX_V2_APPLIED '+json.dumps({'backup':str(backup),'after_hashes':{str(p):sha(b) for p,b in new.items()},
  'before_hashes':{str(p):sha(b) for p,b in old.items()}}),flush=True)
try:main()
except Exception as ex:
 print('JNS_LUX_V2_BLOCKED '+json.dumps({'error_type':type(ex).__name__,'reason':str(ex)[:500]}),flush=True)
 sys.exit(2)
