#!/usr/bin/env python3
"""Guarded VM905 Garden Features + Back Door patch. Run inside Core via QGA.
Only edits exact identified automation blocks, one doorbell package, one
dashboard and creates one JNS package. Full local backups/rollback.
"""
import base64,copy,datetime,hashlib,json,os,re,shutil,sys,tempfile
from pathlib import Path
import yaml
ROOT=Path('/config')
A=ROOT/'automations.yaml'
D=ROOT/'packages/jns_doorbell_security_lighting.yaml'
UI=ROOT/'dashboards/testing.yaml'
P=ROOT/'packages/jns_garden_features_backdoor.yaml'
FEATURE='switch.0x84fd27fffe5fa5bd'
DOG='switch.0x84fd27fffe9ce438'
PORCH='switch.0xa4c138bda6ec8ea0'
LOCK='input_boolean.jns_water_feature_maintenance'
DOOR_TIMER='timer.jns_backdoor_dogs_run'
GARDEN_ID='1791834164199'
PIR_ID='1792086505206'
DOORBELL_ID='jns_doorbell_security_release_20261020'
PACKAGE=yaml.safe_load(base64.b64decode('PACKAGE_B64').decode())
PACKAGE_TEXT=base64.b64decode('PACKAGE_B64')
assert isinstance(PACKAGE,dict)
assert PACKAGE['timer'].get('jns_backdoor_dogs_run')
assert PACKAGE['input_boolean'].get('jns_water_feature_maintenance')

def check(condition,message):
    if not condition: raise ValueError(message)

def sha(b): return hashlib.sha256(b).hexdigest()

def patch_automation(data,automation_id,modifier):
    text=data.decode('utf-8')
    original=yaml.safe_load(text)
    check(isinstance(original,list),'automations list missing')
    positions=[i for i,a in enumerate(original) if str(a.get('id'))==automation_id]
    check(len(positions)==1,'automation id missing or repeated: '+automation_id)
    expected=copy.deepcopy(original)
    modifier(expected[positions[0]])
    mark=re.compile(r"(?m)^- id: ['\"]?"+re.escape(automation_id)+r"['\"]?[ \t]*$")
    matches=list(mark.finditer(text))
    check(len(matches)==1,'automation raw block ambiguous: '+automation_id)
    first=matches[0]; nxt=re.search(r'(?m)^- id:',text[first.end():])
    end=(first.end()+nxt.start()) if nxt else len(text)
    rendered=yaml.safe_dump([expected[positions[0]]],sort_keys=False,allow_unicode=True,width=180)
    new=(text[:first.start()]+rendered+text[end:]).encode('utf-8')
    check(yaml.safe_load(new)==expected,'semantic mismatch after automations splice: '+automation_id)
    return new

def update_garden(a):
    check(a.get('alias')=='Garden - Water Feature - Daily Schedule','wrong garden schedule')
    tr=a.get('triggers',[])
    check(any(x.get('id')=='start' for x in tr),'garden daily start missing')
    check(not any(x.get('id')=='maintenance_on' for x in tr),'already modified')
    tr.extend([
      {'trigger':'state','entity_id':LOCK,'to':'on','id':'maintenance_on'},
      {'trigger':'state','entity_id':LOCK,'from':'on','to':'off','id':'maintenance_off'}
    ])
    choices=a['actions'][0]['choose']
    check(len(choices)==2,'garden choice count changed')
    check(any(x.get('id')=='start' for x in tr),'missing trigger')
    # If maintenance is active, this branch precedes the usual schedule.
    choices.insert(0,{
      'conditions':[{'condition':'state','entity_id':LOCK,'state':'on'}],
      'sequence':[{'action':'switch.turn_off','target':{'entity_id':FEATURE}}]
    })
    resume=choices[2]
    trigger_condition=next((x for x in resume['conditions'] if x.get('condition')=='trigger'),None)
    check(trigger_condition is not None,'garden resume condition missing')
    ids=trigger_condition.get('id',[])
    check(isinstance(ids,list) and 'resume' in ids,'garden resume ids missing')
    ids.append('maintenance_off')
    resume['conditions'].append({'condition':'state','entity_id':LOCK,'state':'off'})

def update_pir(a):
    check(a.get('alias')=='External Security Lights - Porch PIR','wrong PIR')
    def visit(node):
        if isinstance(node,list):
            for i,c in enumerate(node):
                if isinstance(c,dict) and c.get('action')=='homeassistant.turn_off' and c.get('target',{}).get('entity_id')=='{{ security_lights }}':
                    node[i:i+1]=[
                     {'if':[{'condition':'template','value_template':"{{ not is_state('timer.jns_doorbell_security_lighting','active') and not is_state('timer.jns_welcome_home','active') }}"}],
                      'then':[{'action':'switch.turn_off','target':{'entity_id':PORCH}}]},
                     {'if':[{'condition':'template','value_template':"{{ not is_state('timer.jns_backdoor_dogs_run','active') and not is_state('timer.jns_doorbell_security_lighting','active') and not is_state('timer.jns_welcome_home','active') }}"}],
                      'then':[{'action':'switch.turn_off','target':{'entity_id':DOG}}]}
                    ]
                    return 1
                found=visit(c)
                if found: return found
        elif isinstance(node,dict):
            for child in node.values():
                found=visit(child)
                if found:return found
        return 0
    check(visit(a)==1,'PIR dual-light off action absent')

def update_doorbell(data):
    before=copy.deepcopy(data)
    arr=data.get('automation',[])
    matches=[x for x in arr if str(x.get('id'))==DOORBELL_ID]
    check(len(matches)==1,'doorbell release missing')
    a=matches[0]
    found=0
    for action in a.get('actions',[]):
        if not isinstance(action,dict) or 'if' not in action:continue
        seq=action.get('then',[])
        if any(x.get('target',{}).get('entity_id')==DOG and x.get('action')=='homeassistant.turn_off' for x in seq):
            cond=action['if']
            check(len(cond)==1 and cond[0].get('condition')=='template','unexpected doorbell gate')
            value=cond[0]['value_template']
            check('jns_doorbell_preexisting_garage_security' in value and 'jns_backdoor_dogs_run' not in value,'unexpected doorbell condition')
            cond[0]['value_template']="{{ is_state('input_boolean.jns_doorbell_preexisting_garage_security','off') and not is_state('timer.jns_backdoor_dogs_run','active') and not is_state('timer.jns_welcome_home','active') }}"
            found+=1
    check(found==1,'doorbell light release not unique')
    check(len(before['automation'])==len(data['automation']),'doorbell automation removed')
    return yaml.safe_dump(data,sort_keys=False,allow_unicode=True,width=180).encode()

def patch_dashboard(data):
    text=data.decode()
    block=("    - type: tile\n"
       "      entity: "+FEATURE+"\n"
       "      name: Rear Garden Water Feature\n"
       "      tap_action:\n"
       "        action: toggle\n"
       "      hold_action:\n"
       "        action: more-info\n")
    check(text.count(block)==1,'water feature old lighting card changed')
    text=text.replace(block,'',1)
    marker="- title: Lighting Settings\n  path: lighting-settings\n  icon: mdi:weather-sunny\n  cards:\n"
    check(text.count(marker)==1,'lighting-settings view not unique')
    newview=(
      "- title: Garden Features\n"
      "  path: garden-features\n"
      "  icon: mdi:fountain\n"
      "  cards:\n"
      "  - type: markdown\n"
      "    content: >-\n"
      "      Rear Garden Water Feature is an ornamental garden feature with lighting,\n"
      "      not a general-purpose light. Normal schedule: 09:00-23:00, subject to the\n"
      "      existing alarm armed-away rule. Enable Maintenance Lockout to stop it\n"
      "      and prevent automatic operation. Always isolate electrical power before\n"
      "      hands-on maintenance.\n"
      "  - type: tile\n"
      "    entity: "+LOCK+"\n"
      "    name: Maintenance Lockout (ON = disabled)\n"
      "    icon: mdi:lock\n"
      "    tap_action:\n"
      "      action: toggle\n"
      "  - type: conditional\n"
      "    conditions:\n"
      "    - entity: "+LOCK+"\n"
      "      state: 'off'\n"
      "    card:\n"
      "      type: tile\n"
      "      entity: "+FEATURE+"\n"
      "      name: Rear Garden Water Feature\n"
      "      tap_action:\n"
      "        action: toggle\n"
      "  - type: conditional\n"
      "    conditions:\n"
      "    - entity: "+LOCK+"\n"
      "      state: 'on'\n"
      "    card:\n"
      "      type: markdown\n"
      "      content: '**MAINTENANCE LOCKOUT ACTIVE** - feature switching is disabled.'\n"
    )
    lighting=(
      "  - type: entities\n"
      "    title: Back Door - Dogs Run Security Lighting\n"
      "    show_header_toggle: false\n"
      "    entities:\n"
      "    - entity: input_number.jns_backdoor_dogs_run_minutes\n"
      "      name: Back door ON duration (minutes)\n"
      "    - entity: timer.jns_backdoor_dogs_run\n"
      "      name: Active back-door timer\n"
      "    - entity: binary_sensor.backdoor_contact_sensor_door\n"
      "      name: Back door sensor (Tuya, local migration pending)\n"
    )
    text=text.replace(marker,newview+marker+lighting,1)
    parsed=yaml.safe_load(text)
    check(isinstance(parsed,dict) and isinstance(parsed.get('views'),list),'dashboard failed YAML validation')
    names=[x.get('path') for x in parsed['views']]
    check(names.count('garden-features')==1 and names.count('lighting-settings')==1,'view path count')
    check('jns_backdoor_dogs_run_minutes' in text,'slider absent')
    check(text.count('      entity: '+FEATURE)==1,'water feature control appears outside separate page')
    return text.encode('utf-8')

def compose():
    existing={p:p.read_bytes() for p in (A,D,UI)}
    check(not P.exists(),'new JNS package already exists: refuse overwrite')
    patched={}
    first=patch_automation(existing[A],GARDEN_ID,update_garden)
    patched[A]=patch_automation(first,PIR_ID,update_pir)
    before=yaml.safe_load(existing[D]); patched[D]=update_doorbell(copy.deepcopy(before))
    check(yaml.safe_load(patched[D]) is not None,'bad doorbell YAML')
    patched[UI]=patch_dashboard(existing[UI])
    patched[P]=PACKAGE_TEXT
    check(yaml.safe_load(patched[P])==PACKAGE,'package parse mismatch')
    return existing,patched

def write_atomic(path,content,old=None):
    if old is not None:check(path.read_bytes()==old,'concurrent edit: '+path.name)
    elif path.exists():raise ValueError('unexpected package exists')
    fd,temp=tempfile.mkstemp(prefix='.jns-garden-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        if path.exists():
            st=path.stat()
            os.chown(temp,st.st_uid,st.st_gid)
            os.chmod(temp,st.st_mode & 0o777)
        else:
            os.chmod(temp,0o644)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def main():
    old,new=compose()
    print('JNS_GARDEN_PLAN '+json.dumps({'status':'ready','paths':list(map(str,new)),
          'hashes':{p.name:sha(x) for p,x in old.items()},
          'maintenance_default':'unlocked_restored','backdoor_minutes':10},sort_keys=True),flush=True)
    if '--apply' not in sys.argv:return
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup_dir=ROOT/'.jns-backups'/('garden-features-'+stamp)
    backup_dir.mkdir(parents=True,exist_ok=False)
    original_backup={}
    for path,contents in old.items():
        b=backup_dir/('automations.yaml' if path==A else 'doorbell.yaml' if path==D else 'testing.yaml')
        b.write_bytes(contents)
        check(sha(b.read_bytes())==sha(contents),'backup verification failure')
        original_backup[path]=b
    changed=[]
    try:
        for path in [A,D,UI,P]:
            write_atomic(path,new[path],old.get(path))
            changed.append(path)
        print('JNS_GARDEN_APPLIED '+json.dumps({'status':'applied','backup':str(backup_dir),
             'changed':[str(p) for p in changed],'hashes':{p.name:sha(new[p]) for p in changed}}),flush=True)
    except BaseException:
        for path in reversed(changed):
            if path.read_bytes()!=new[path]:continue
            if path==P: path.unlink()
            else:write_atomic(path,old[path],new[path])
        raise
try:main()
except Exception as e:
    print('JNS_GARDEN_BLOCKED '+json.dumps({'error_type':type(e).__name__,'reason':str(e)[:300]}),flush=True)
    raise SystemExit(2)
