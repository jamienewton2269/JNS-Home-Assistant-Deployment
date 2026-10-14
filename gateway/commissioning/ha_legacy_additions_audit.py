#!/usr/bin/env python3
"""HA900 legacy additions inventory: read-only, stdlib, no secrets exported."""
import json,re,collections,datetime
from pathlib import Path
R=Path('/config')
out=[]
def say(x): out.append(str(x))
def load(name):
 try: return json.loads((R/'.storage'/name).read_text()).get('data',{})
 except Exception as e: say('Could not read '+name+': '+type(e).__name__); return {}
def clean(s):
 s=str(s)
 s=re.sub(r'(?i)(password|secret|token|key)\s*[:=]\s*[^\s,]+',r'\1=[REDACTED]',s)
 return s[:120]
say('HA900 LEGACY INVENTORY (READ ONLY)')
say('Generated: '+datetime.datetime.now(datetime.timezone.utc).isoformat())
entries=load('core.config_entries').get('entries',[])
say('\n=== INTEGRATIONS ===')
for e in entries:
 say('%s | %s | disabled=%s'%(e.get('domain'),clean(e.get('title','')),bool(e.get('disabled_by'))))
say('\n=== CUSTOM INTEGRATIONS ===')
d=R/'custom_components'
if d.is_dir():
 for p in sorted(d.iterdir()):
  if p.is_dir():
   try:
    m=json.loads((p/'manifest.json').read_text())
    say('%s | version=%s | type=%s'%(p.name,m.get('version','?'),m.get('integration_type','?')))
   except Exception: say(p.name)
say('\n=== ENERGY AND TUYA ENTITIES ===')
ents=load('core.entity_registry').get('entities',[])
for e in ents:
 s=' '.join(str(e.get(k,'')) for k in ('entity_id','platform','name','original_name')).lower()
 if any(k in s for k in ('tuya','meter','energy','power','voltage','current','electric','grid')):
  say('%s | platform=%s | disabled=%s | name=%s'%(e.get('entity_id'),e.get('platform'),bool(e.get('disabled_by')),clean(e.get('name') or e.get('original_name') or '')))
say('\n=== CUSTOM FILES / PACKAGES ===')
for dirn in ('packages','scripts','python_scripts','www','dashboards'):
 p=R/dirn
 if p.is_dir():
  files=sorted(x.relative_to(R) for x in p.rglob('*') if x.is_file())
  say('%s: %d files'%(dirn,len(files)))
  for f in files[:80]: say('  '+str(f))
for fn in ('configuration.yaml','automations.yaml','scripts.yaml','scenes.yaml'):
 p=R/fn
 if p.is_file():
  s=p.read_text(errors='replace')
  say('\n'+fn+': '+str(len(s.splitlines()))+' lines')
  for alias in re.findall(r'^\s*-?\s*alias:\s*(.{1,120})$',s,re.M)[:100]:
   say('  automation: '+clean(alias))
say('\n=== HELPER COUNTS ===')
for name in ('input_boolean','input_number','input_datetime','input_select','timer','counter','utility_meter','template'):
 n=load(name).get('items',[])
 if n:say(name+': '+str(len(n)))
say('\n=== NATIVE-FIRST REVIEW ===')
for s in ('Energy: native Energy dashboard, Utility Meter, template/integration sensors; confirm sensor state_class and unit.',
'Tuya: evaluate official Tuya vs community Tuya Local for LAN needs; do not copy old local keys blindly.',
'Zigbee: MQTT integration + Zigbee2MQTT, standard entities and labels.',
'Lighting: native automation, helpers, schedules, scripts, scenes and labels.',
'Chimes: native media_player + HA automations, existing MPD.',
'Custom code: retain only when native integrations/helpers cannot meet tested requirements.'):
 say(s)
say('\nNOTE: Inventory only. No device changed; no passwords/local keys exported.')
report='\n'.join(out)+'\n'
p=R/'ha_legacy_audit_report.txt'
p.write_text(report)
print(report)
print('REPORT WRITTEN:',p)
