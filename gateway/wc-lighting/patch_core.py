#!/usr/bin/env python3
"""Patch ONLY the WC motion ON lux template, never other HA automations."""
from pathlib import Path
import json, os, re, sys, tempfile, hashlib, shutil, datetime
import yaml

PATH=Path('/config/automations.yaml')
WC_ID='1791727298265'
ALIAS='General - WC Motion Light and Extractor'
OLD_SENSOR='sensor.0xa4c1383917c90309_illuminance'
NEW_SENSOR='sensor.jns_lighting_effective_lux'
NEW_TEMPLATE="""{% set lux = states('sensor.jns_lighting_effective_lux') %}
{% set threshold = states('input_number.general_outdoor_lighting_on_lux') | float(2500) * 1.5 %}
{{ is_number(lux) and lux | float(99999) < threshold }}"""
NEW_LINES=("            value_template: |-\n"+
           "".join("              "+line+"\n" for line in NEW_TEMPLATE.splitlines()))

def checksum(data):return hashlib.sha256(data).hexdigest()
def extract_old(parsed):
    matches=[a for a in parsed if str(a.get('id'))==WC_ID and a.get('alias')==ALIAS]
    if len(matches)!=1:raise RuntimeError('target automation missing/ambiguous')
    a=matches[0]
    return a['actions'][0]['choose'][0]['sequence'][0]['if'][0]['conditions'][1]['value_template']

def inspect_patch(data):
    text=data.decode()
    before=yaml.safe_load(text)
    if not isinstance(before,list):raise RuntimeError('expected automation YAML list')
    previous=extract_old(before)
    if NEW_SENSOR in previous and '* 1.5' in previous:
        return 'already_applied',data,previous
    if OLD_SENSOR not in previous or 'input_number.general_outdoor_lighting_on_lux' not in previous:
        raise RuntimeError('unexpected existing WC template - refusing')
    markers=list(re.finditer(r"(?m)^- id: ['\"]?1791727298265['\"]?$",text))
    if len(markers)!=1:raise RuntimeError('WC text marker count unexpected')
    start=markers[0].start()
    following=re.search(r'(?m)^- id:',text[start+len(markers[0].group()):])
    end=start+len(markers[0].group())+following.start() if following else len(text)
    segment=text[start:end]
    match=re.search(r'(?ms)^            value_template:.*?(?=^        then:)',segment)
    if not match or OLD_SENSOR not in match.group():
        raise RuntimeError('unexpected WC raw YAML template structure')
    patched=text[:start]+segment[:match.start()]+NEW_LINES+segment[match.end():]+text[end:]
    after=yaml.safe_load(patched)
    before_value=extract_old(before)
    after_value=extract_old(after)
    if OLD_SENSOR not in before_value or after_value.strip()!=NEW_TEMPLATE.strip():
        raise RuntimeError('post-patch template mismatch')
    # Every other automation and every other WC field must remain identical.
    before[ next(i for i,a in enumerate(before) if str(a.get('id'))==WC_ID) ]['actions'][0]['choose'][0]['sequence'][0]['if'][0]['conditions'][1]['value_template']=after_value
    if before!=after:
        raise RuntimeError('unexpected changes outside the targeted WC template')
    return 'ready',patched.encode(),after_value

def apply():
    current=PATH.read_bytes()
    status,patched,value=inspect_patch(current)
    if status=='already_applied':
        print(json.dumps({'status':status,'sha256':checksum(current)}));return
    if '--apply' not in sys.argv:
        print(json.dumps({'status':'preflight_ok','old_sha256':checksum(current),
            'new_sha256':checksum(patched),'wc_threshold_multiplier':1.5,
            'effective_lux_source':NEW_SENSOR}));return
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=PATH.with_name('automations.yaml.pre-wc-earlier-'+stamp+'.bak')
    if backup.exists():raise RuntimeError('backup collision')
    shutil.copy2(PATH,backup)
    if checksum(backup.read_bytes())!=checksum(current):raise RuntimeError('backup verification failed')
    if PATH.read_bytes()!=current:raise RuntimeError('concurrent source change detected')
    fd,temporary=tempfile.mkstemp(prefix='.jns_wc_',suffix='.yaml',dir=str(PATH.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(patched);f.flush();os.fsync(f.fileno())
        shutil.copymode(PATH,temporary)
        st=os.stat(PATH)
        os.chown(temporary,st.st_uid,st.st_gid)
        if PATH.read_bytes()!=current:raise RuntimeError('source changed during staging')
        os.replace(temporary,PATH)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    print(json.dumps({'status':'patched','backup':str(backup),
         'old_sha256':checksum(current),'new_sha256':checksum(patched),
         'wc_threshold_multiplier':1.5,'source':NEW_SENSOR}))

def rollback():
    backup=Path(sys.argv[sys.argv.index('--rollback')+1])
    expected=sys.argv[sys.argv.index('--rollback')+2]
    if backup.parent!=PATH.parent or not backup.name.startswith('automations.yaml.pre-wc-earlier-'):
        raise RuntimeError('unsafe backup path')
    if checksum(PATH.read_bytes())!=expected:raise RuntimeError('refuse rollback: subsequent edits detected')
    saved=backup.read_bytes()
    if not isinstance(yaml.safe_load(saved),list):raise RuntimeError('bad backup')
    fd,tmp=tempfile.mkstemp(prefix='.jns_wc_restore_',dir=str(PATH.parent))
    try:
        with os.fdopen(fd,'wb') as f:f.write(saved);f.flush();os.fsync(f.fileno())
        shutil.copystat(backup,tmp)
        st=os.stat(backup);os.chown(tmp,st.st_uid,st.st_gid)
        os.replace(tmp,PATH)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print(json.dumps({'status':'rolled_back','sha256':checksum(saved)}))
try:
    if '--rollback' in sys.argv:rollback()
    else:apply()
except Exception as error:
    print(json.dumps({'status':'blocked','error':str(error)[:200]}))
    raise SystemExit(2)
