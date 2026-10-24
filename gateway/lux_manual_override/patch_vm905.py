#!/usr/bin/env python3
"""Guarded, reversible HA905 manual-off lockout and HA-General dashboard insertion.
Script executes INSIDE Home Assistant Core Docker container via existing JNS node runner.
Dry-run unless --apply; never edits .storage, never changes security/PIR scripts.
"""
import base64,copy,datetime,hashlib,json,os,re,sys,tempfile
from pathlib import Path
import yaml
ROOT=Path('/config')
AUTO=ROOT/'automations.yaml'
DASH=ROOT/'dashboards/testing.yaml'
PKG=ROOT/'packages/jns_lux_manual_off_v1.yaml'
PACKAGE_BYTES=base64.b64decode(PACKAGE_B64)
PACKAGE=yaml.safe_load(PACKAGE_BYTES)
SHARED='1791918795028'
SNUG='1791820842687'
HOLD="{{ not is_state('input_boolean.jns_lux_manual_hold_all', 'on') and e not in states('input_text.jns_lux_off_tonight_entities').split('|') }}"
SNUG_HOLD="{{ not is_state('input_boolean.jns_lux_manual_hold_all', 'on') and 'switch.0x84fd27fffe7040c9' not in states('input_text.jns_lux_off_tonight_entities').split('|') }}"
def require(test,msg):
    if not test:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def modify_automation(a,identity):
    if identity==SHARED:
        require(a.get('alias')=='General - Shared Lux Progressive Control','Lux alias mismatch')
        reps=[x for x in a.get('actions',[]) if isinstance(x,dict) and isinstance(x.get('repeat'),dict)]
        require(len(reps)==1,'Lux repeat count mismatch')
        seq=reps[0]['repeat'].get('sequence',[])
        eligible=[i for i,x in enumerate(seq) if 'choose' in x]
        require(len(eligible)==1,'Lux choose branch mismatch')
        pos=eligible[0]
        require(not any('jns_lux_off_tonight_entities' in str(x) for x in seq),'Lux already patched')
        seq[pos]={'if':[{'condition':'template','value_template':HOLD}],'then':[seq[pos]]}
    else:
        require(a.get('alias')=='General - Snug Daylight Pilot','Snug alias mismatch')
        conditions=a.get('conditions',[])
        require(isinstance(conditions,list) and not any('jns_lux_off_tonight_entities' in str(x) for x in conditions),'Snug already patched')
        conditions.append({'condition':'template','value_template':SNUG_HOLD})
def splice(raw,identity):
    text=raw.decode()
    before=yaml.safe_load(text)
    require(isinstance(before,list),'automation root changed')
    matches=[i for i,v in enumerate(before) if str(v.get('id'))==identity]
    require(len(matches)==1,'missing/duplicated '+identity)
    expected=copy.deepcopy(before)
    modify_automation(expected[matches[0]],identity)
    match=list(re.finditer(r"(?m)^- id: ['\"]?"+re.escape(identity)+r"['\"]?[ \t]*$",text))
    require(len(match)==1,'raw automation splice ambiguous '+identity)
    start=match[0].start()
    nxt=re.search(r'(?m)^- id:',text[match[0].end():])
    end=match[0].end()+nxt.start() if nxt else len(text)
    new_block=yaml.safe_dump([expected[matches[0]]],allow_unicode=True,sort_keys=False,width=160)
    result=(text[:start]+new_block+text[end:]).encode()
    require(yaml.safe_load(result)==expected,'automation semantic guard '+identity)
    return result
def dashboard(old):
    text=old.decode()
    marker="- title: Lighting Settings\n  path: lighting-settings\n  icon: mdi:weather-sunny\n  cards:\n"
    require(text.count(marker)==1,'cannot find exactly one Lighting Settings view')
    require("  path: evening-lighting\n" not in text,'Evening Lighting page already present')
    view="""- title: Evening Lighting
  path: evening-lighting
  icon: mdi:lightbulb-night
  cards:
  - type: markdown
    content: >-
      ## Manual control takes priority

      Switch a Lux-controlled light OFF here or at its physical switch and
      the Lux Controller will leave it OFF for the rest of tonight.
      Other lights remain automatic. The hold resets after sunrise.

      WC motion, doorbell and security-light automations still operate independently.
  - type: entities
    title: Evening Lux-Controlled Lights
    show_header_toggle: false
    entities:
    - entity: light.0x847127fffe2890a6
      name: Hallway Centre
    - entity: light.0x847127fffe28965b
      name: Hallway Front Door
    - entity: switch.0x84fd27fffe7040c9
      name: Snug Corner Lamp
    - entity: light.snug_sofa_led
      name: Snug Sofa LED
    - entity: light.0x003c84fffe1a695c
      name: Tree House Tripod
    - entity: switch.general_kitchen_worktop_light
      name: Kitchen Worktop
    - entity: switch.general_kitchen_radiator_light
      name: Kitchen Radiator
  - type: entities
    title: Manual-Off Status and Reset
    show_header_toggle: false
    entities:
    - entity: input_boolean.jns_lux_manual_hold_all
      name: Pause all Lux automatic lighting
    - entity: input_text.jns_lux_off_tonight_entities
      name: Held off until sunrise (read-only status)
    - entity: script.jns_lux_resume_all
      name: Resume automatic Lux control now
  - type: markdown
    content: >-
      **Tonight's held-off lights:** {% set s =
      states('input_text.jns_lux_off_tonight_entities') %}
      {{ s.split('|') | join(', ') if s not in ['','unknown','unavailable']
      else 'None' }}

      If an emergency/security automation switches a light on,
      its own controls remain authoritative.
"""
    updated=text.replace(marker,view+marker,1).encode()
    parsed=yaml.safe_load(updated)
    require(isinstance(parsed,dict) and len([v for v in parsed.get('views',[]) if v.get('path')=='evening-lighting'])==1,'UI semantic guard failed')
    return updated
def atomic(path,new,original=None):
    if original is None:require(not path.exists(),'unanticipated existing package')
    else:require(path.read_bytes()==original,'concurrent file edit '+str(path))
    fd,tmp=tempfile.mkstemp(prefix='.jns-lux-manual-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(new);stream.flush();os.fsync(stream.fileno())
        if path.exists():
            stat=path.stat();os.chown(tmp,stat.st_uid,stat.st_gid);os.chmod(tmp,stat.st_mode & 0o777)
        else:os.chmod(tmp,0o644)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def main():
    require(not PKG.exists(),'package already installed, refusing duplicate deployment')
    require(set(['input_text','input_boolean','automation','script']).issubset(PACKAGE),'invalid package')
    originals={AUTO:AUTO.read_bytes(),DASH:DASH.read_bytes()}
    staged={AUTO:splice(splice(originals[AUTO],SHARED),SNUG),DASH:dashboard(originals[DASH]),PKG:PACKAGE_BYTES}
    for path,data in staged.items():
        require(yaml.safe_load(data) is not None,'YAML parse failed '+path.name)
    print('JNS_LUX_MANUAL_PLAN '+json.dumps({'status':'ready',
      'paths':[str(p) for p in staged],
      'before_hashes':{p.name:sha(v) for p,v in originals.items()},
      'after_hashes':{p.name:sha(v) for p,v in staged.items()},
      'per_light_manual_off':True,'sunrise_reset':True,'ui_path':'evening-lighting'},sort_keys=True),flush=True)
    if '--apply' not in sys.argv:return
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backdir=ROOT/'.jns-backups'/('lux-manual-off-'+stamp)
    backdir.mkdir(parents=True,exist_ok=False)
    for file,b in originals.items():
        target=backdir/('testing.yaml' if file==DASH else file.name)
        target.write_bytes(b)
        require(sha(target.read_bytes())==sha(b),'backup verification failed')
    applied=[]
    try:
        for path,data in staged.items():
            atomic(path,data,originals.get(path))
            applied.append(path)
    except BaseException:
        for path in reversed(applied):
            if path.read_bytes()!=staged[path]:continue
            if path==PKG:path.unlink()
            else:atomic(path,originals[path],staged[path])
        raise
    print('JNS_LUX_MANUAL_APPLIED '+json.dumps({'status':'applied',
       'backup':str(backdir),'after_hashes':{p.name:sha(v) for p,v in staged.items()}}),flush=True)
try:main()
except Exception as e:
    print('JNS_LUX_MANUAL_BLOCKED '+json.dumps({'error_type':type(e).__name__,'reason':str(e)[:350]}),flush=True)
    sys.exit(2)
