#!/usr/bin/env python3
"""Read-only JNS WC lighting audit on live HA-General VM905."""
import base64, json, time, sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host

inspect=r"""
from pathlib import Path
import yaml, json, re
root=Path('/config')
matches=[]
for p in [root/'automations.yaml', *(root/'packages').glob('*.yaml')]:
    if not p.is_file(): continue
    try:
        data=yaml.safe_load(p.read_text())
    except Exception as e:
        print('PARSE_FAIL',p.name,type(e).__name__)
        continue
    blocks=[]
    if isinstance(data,list): blocks=data
    if isinstance(data,dict):
        v=data.get('automation',[])
        if isinstance(v,list):blocks=v
        elif isinstance(v,dict):blocks=[v]
    for a in blocks:
        if not isinstance(a,dict):continue
        alias=str(a.get('alias',''))
        text=yaml.safe_dump(a,sort_keys=False,allow_unicode=True)
        if re.search(r'\b(wc|toilet|bathroom|washroom)\b',alias,re.I) or (
             ('0xa4c138999d9f23eb' in text or 'downstairs_wc' in text.lower())
             and re.search(r'\b(wc|toilet)\b',text,re.I)):
            matches.append({'file':str(p.relative_to(root)),'alias':alias,
                            'id':a.get('id'),'yaml':text[:19000]})
print('=== WC AUTOMATIONS ===')
print(json.dumps(matches,indent=2,ensure_ascii=False))
print('=== LUX CONTROLLER CURRENT ===')
a=yaml.safe_load((root/'automations.yaml').read_text()) or []
for item in a:
    if 'Shared Lux Progressive' in str(item.get('alias','')):
        print(yaml.safe_dump(item,sort_keys=False,allow_unicode=True)[:26000])
print('=== SENSOR / TEMPLATE LUX PACKAGE SOURCES ===')
for pp in [root/'packages/jns_synthetic_lux_calibration.yaml',
           root/'packages/jns_synthetic_lux.yaml',
           root/'packages/jns_lux.yaml']:
    if pp.exists():
        print('FILE',pp.name)
        print(pp.read_text()[:14000])
print('=== WC HELPER DEFINITIONS ===')
for p in [root/'configuration.yaml',*(root/'packages').glob('*.yaml')]:
    content=p.read_text()
    if re.search(r'(wc.*(lux|light|motion)|lux.*wc)',content,re.I):
        print('file',str(p.relative_to(root)))
        for n,line in enumerate(content.splitlines(),1):
            if re.search(r'(wc.*(lux|light|motion)|lux.*wc)',line,re.I):
                print(n,line[:280])
"""
encoded=base64.b64encode(inspect.encode()).decode()
arg="exec(__import__('base64').b64decode("+repr(encoded)+"))"
command=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]
resp=json.loads(ssh_host('nodeb',command))
for i in range(50):
    if resp.get('exited'): break
    time.sleep(1)
    resp=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(resp['pid'])]))
if not resp.get('exited') or resp.get('exitcode')!=0:
    print('WC_AUDIT_BLOCKED',resp.get('err-data','')[:1000]);raise SystemExit(1)
print(resp.get('out-data','')[:68000])
