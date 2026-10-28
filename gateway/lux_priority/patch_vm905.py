#!/usr/bin/env python3
"""JNS Lux Priority Ladder V1: guarded, scoped, dry-run first; VM905 Core only."""
from pathlib import Path
import base64,copy,datetime,hashlib,json,os,re,stat,sys,tempfile,yaml
ROOT=Path('/config')
AUTO=ROOT/'automations.yaml'
DASH=ROOT/'dashboards/testing.yaml'
MANUAL=ROOT/'packages/jns_lux_manual_off_v1.yaml'
PACKAGE=ROOT/'packages/jns_lux_priority_ladder.yaml'
TAG='JNS_LUX_PRIORITY_LADDER_V1'
L=[
 ('hall','Hallway Centre','light.0x847127fffe2890a6',1,True),
 ('front','Hallway Front Door','light.0x847127fffe28965b',2,True),
 ('worktop','Kitchen Worktop','switch.general_kitchen_worktop_light',3,True),
 ('snug','Snug Corner','switch.0x84fd27fffe7040c9',4,True),
 ('radiator','Kitchen Radiator','switch.general_kitchen_radiator_light',5,True),
 ('tripod','Tree House Tripod','light.0x003c84fffe1a695c',6,True),
 ('living','Living Room Pendant','light.0x5c0272fffe400903',7,False),
 ('sofa','Snug Sofa LED','light.snug_sofa_led',8,False),
]
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def atomic(p,b):
 st=p.stat() if p.exists() else None
 fd,tmp=tempfile.mkstemp(prefix='.jns-lux-ladder-',dir=str(p.parent))
 try:
  with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
  if st:
   os.chown(tmp,st.st_uid,st.st_gid)
   os.chmod(tmp,stat.S_IMODE(st.st_mode))
  else:os.chmod(tmp,0o644)
  os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def make_automation(raw):
 original=yaml.safe_load(raw)
 require(isinstance(original,list),'HA automations list missing')
 hit=[x for x in original if str(x.get('id'))=='1791918795028']
 require(len(hit)==1,'Shared lux controller not uniquely present')
 a=copy.deepcopy(hit[0])
 require('General - Shared Lux Progressive Control' in a.get('alias',''),'Wrong lux controller')
 require(TAG not in str(a),'Already installed')
 require(a.get('mode')=='restart' and len(a.get('actions',[]))==2,'Unexpected controller structure')
 controls=a['actions'][0]['variables']
 require('all_eligible' in controls and 'priority_start_lux' in controls,'Core lux stage variables changed')
 repeat=a['actions'][1]['repeat']
 steps=repeat['sequence']
 require(len(steps)==2 and 'variables' in steps[0] and 'if' in steps[1],'Expected Lux loop with manual hold gate')
 v=steps[0]['variables']
 require(all(x in v for x in ['e','priority','start_lux','dimmable','level']),'Existing Lux dimmer logic unexpected')
 choices=steps[1]['then'][0]['choose']
 require(len(choices)==5,'Lux choice branch count changed')
 require(choices[0]['sequence'][0].get('action')=='homeassistant.turn_off','OFF branch not as audited')
 require(choices[0]['sequence'][1].get('action')=='input_text.set_value','OFF reason marker changed')
 require(choices[4]['sequence'][0].get('action')=='homeassistant.turn_on','Relay ON branch changed')
 # Keep the existing manual-off and bedtime guards around the entire repeat.
 labels=controls.get('all_eligible','')
 require('lighting_lux_controlled' in labels and 'commissioned' in labels,'Existing commissioning protections missing')
 # Only eight known, physically audited outputs can be in this managed ladder.
 rows=[f"  ('{e}', 'input_boolean.jns_lux_include_{i}', 'input_number.jns_lux_rank_{i}')" for i,n,e,r,initial in L]
 controls['all_eligible']=("{% set ns = namespace(rows=[], enabled=[]) %}\n"
  "{% for eid, toggle, rank in [\n"+",\n".join(rows)+"\n] %}\n"
  "  {% if is_state(toggle,'on') and states(eid) in ['on','off'] %}\n"
  "    {% set ns.rows = ns.rows + [[states(rank)|int(8), eid]] %}\n"
  "  {% endif %}\n"
  "{% endfor %}\n"
  "{% for entry in ns.rows | sort %}\n"
  "  {% set ns.enabled = ns.enabled + [entry[1]] %}\n"
  "{% endfor %}\n{{ ns.enabled }}")
 controls['high_priority']="{{ [all_eligible[0]] if all_eligible | count > 0 else [] }}"
 v['priority']="{{ (all_eligible | list).index(e) == 0 }}"
 v['start_lux']=("{% set ordinal = (all_eligible | list).index(e) %}\n"
   "{% set gap = states('input_number.jns_lux_ladder_stage_gap')|float(350) %}\n"
   "{% set early = states('input_number.general_lux_priority_boost')|float(1000) %}\n"
   "{{ [100, normal_start_lux|float + early - ordinal * gap] | max }}")
 # New stable-off guard is held for 20 minutes; each lamp has its own OFF threshold.
 v['safe_off']=("{{ is_state('binary_sensor.jns_lux_priority_bright_stable','on')"
   " and not raining|bool and is_state(e,'on')"
   " and decision_lux|float >= (start_lux|float +"
   " states('input_number.general_lighting_lux_hysteresis')|float(400)) }}")
 choices[0]['conditions'][0]['value_template']="{{ safe_off|bool }}"
 # Announce automatic OFF before transmitting to guard against MQTT feedback
 # getting captured as a user manual-OFF.
 choices[0]['sequence'][0],choices[0]['sequence'][1]=choices[0]['sequence'][1],choices[0]['sequence'][0]
 choices[4]['conditions'][0]['value_template']=("{{ not priority|bool and decision_lux|float < start_lux|float"
                                                  " and not dimmable }}")
 # Additional entity/rank/spacing state changes take effect immediately.
 trig=next(x for x in a['triggers'] if x.get('trigger')=='state' and isinstance(x.get('entity_id'),list))
 for i,n,e,r,initial in L:
  trig['entity_id'].extend(['input_boolean.jns_lux_include_'+i,'input_number.jns_lux_rank_'+i])
 trig['entity_id']+=['input_number.jns_lux_ladder_stage_gap','input_boolean.jns_lux_ladder_initialized']
 a['description']=str(a.get('description',''))+' '+TAG+': per-light ordinal lux stages, reverse-order 20-min safe-off, native dashboard rankings.'
 # Disable new ladder until one-time bootstrap, avoiding unintended first-start actions.
 require(len(a['conditions'])==1 and a['conditions'][0].get('entity_id')=='input_boolean.general_bedtime_mode',
         'Bedtime block missing')
 a['conditions'].append({'condition':'state','entity_id':'input_boolean.jns_lux_ladder_initialized','state':'on'})
 text=raw.decode('utf-8')
 pat=r"(?m)^- id: ['\"]?1791918795028['\"]?[ \t]*$"
 matches=list(re.finditer(pat,text))
 require(len(matches)==1,'Cannot safely isolate existing controller YAML')
 start=matches[0].start()
 nxt=re.search(r'(?m)^- id:',text[matches[0].end():])
 end=matches[0].end()+nxt.start() if nxt else len(text)
 block=yaml.safe_dump([a],sort_keys=False,allow_unicode=True,width=160)
 modified=(text[:start]+block+text[end:]).encode()
 new=yaml.safe_load(modified)
 original_other=[x for x in original if str(x.get('id'))!='1791918795028']
 changed_other=[x for x in new if str(x.get('id'))!='1791918795028']
 require(original_other==changed_other,'Unrelated automations modified')
 assert [x for x in new if str(x.get('id'))=='1791918795028']==[a]
 return modified
def make_manual(raw):
 d=yaml.safe_load(raw)
 require(isinstance(d,dict) and isinstance(d.get('automation'),list),'Missing manual OFF package')
 matches=[x for x in d['automation'] if x.get('id')=='jns_lux_record_manual_off_tonight_v1']
 require(len(matches)==1,'Manual-off capture automation missing')
 c=matches[0]['conditions']
 require(len(c)>=2 and c[0].get('entity_id')=='sun.sun','Unexpected manual off safeguards')
 tpl=c[1]['value_template']
 require('new.context.parent_id is none' in tpl,'Manual-off context guard changed')
 require("and eid != 'switch.0xa4c13837e231806e' }}" in tpl,'Manual-off exclusion changed')
 require(TAG not in str(matches[0]),'Manual-off V1 already patched')
 # The original capture includes kitchen aliases and label-controlled lamps.
 # Opted-in sofa and living room lights must have same manual-off protection.
 require("'switch.general_kitchen_radiator_light'" in tpl,'Kitchen exception changed')
 tpl=tpl.replace("'switch.general_kitchen_radiator_light']",
                 "'switch.general_kitchen_radiator_light',\n"
                 "                  'light.0x5c0272fffe400903',\n"
                 "                  'light.snug_sofa_led']")
 prefix=("{% set last = states('input_text.jns_lighting_last_decision') %}\n"
         "{% set marker = states.input_text.jns_lighting_last_decision if "
         "states.input_text.jns_lighting_last_decision is defined else none %}\n"
         "{% set recent = marker is not none and 0 <= "
         "as_timestamp(now())-as_timestamp(marker.last_changed,0) < 45 %}\n"
         "{% set controlled = recent and (' ' ~ eid ~ ' OFF ') in last %}\n")
 require("{% set eid =" in tpl,'Missing original event entity ID')
 # Insert only after existing eid assignment, before final decision.
 pos=tpl.find("{{ old is not none")
 require(pos>0,'Missing manual-off decision body')
 tpl=tpl[:pos]+prefix+tpl[pos:]
 tpl=tpl.replace("and eid != 'switch.0xa4c13837e231806e' }}",
                 "and eid != 'switch.0xa4c13837e231806e'\n   and not controlled }}")
 c[1]['value_template']=tpl
 matches[0]['description']=str(matches[0].get('description',''))+' '+TAG+' controller-OFF intent excluded.'
 b=yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=160).encode()
 require(yaml.safe_load(b)==d,'Manual OFF YAML changed unexpectedly')
 return b
def make_dashboard(raw):
 original=yaml.safe_load(raw)
 require(isinstance(original,dict) and isinstance(original.get('views'),list),'Unexpected dashboard root')
 require(not any(x.get('path')=='lux-priorities' for x in original['views']),'Priority view already present')
 short={'type':'markdown','content':'**Lux Priority Ladder** is now available in the **Lux Priorities** tab. Adjust the light order, individual participation and stage spacing there.'}
 profiles=',\n'.join(" ('input_boolean.jns_lux_include_%s','input_number.jns_lux_rank_%s','%s','%s')"%(i,i,n,e) for i,n,e,r,initial in L)
 summary=("### Live lighting order\n"
  "**Outdoor effective light:** {{ states('sensor.jns_lighting_effective_lux') }} lx "
  "({{ state_attr('sensor.jns_lighting_effective_lux','source') or 'source unknown' }})\n\n"
  "{% set ns=namespace(entries=[]) %}\n"
  "{% for enabled, rank, name, eid in [\n"+profiles+"\n] %}\n"
  "  {% if is_state(enabled,'on') %}\n"
  "    {% set ns.entries=ns.entries+[[states(rank)|int(8),name,eid]] %}\n"
  "  {% endif %}\n"
  "{% endfor %}\n"
  "{% set base=states('input_number.general_outdoor_lighting_on_lux')|float(2500) %}\n"
  "{% set early=states('input_number.general_lux_priority_boost')|float(1000) %}\n"
  "{% set gap=states('input_number.jns_lux_ladder_stage_gap')|float(350) %}\n"
  "{% for row in ns.entries | sort %}\n"
  "  {% set lux=[100,base+early-(loop.index0*gap)] | max %}\n"
  "**{{ loop.index }}. {{ row[1] }}** — below {{ lux|round(0)|int }} lx "
  "· {{ 'ON' if is_state(row[2],'on') else ('OFF' if is_state(row[2],'off') else 'Unavailable') }}\n\n"
  "{% endfor %}\n"
  "The order above is live, sorted by each enabled lamp's position slider. "
  "During daylight the lights fade and switch off in reverse order, with "
  "a 20-minute bright-condition guard and adjustable hysteresis.")
 sections=[]
 for i,n,e,r,initial in L:
  sections.append({'type':'entities','title':n+(' · optional' if not initial else ''),
                   'show_header_toggle':False,
                   'entities':[{'entity':'input_boolean.jns_lux_include_'+i,'name':'Use in Lux control'},
                               {'entity':'input_number.jns_lux_rank_'+i,'name':'Priority (1 = first ON)'},
                               {'entity':e,'name':'Current light'}]})
 view={'title':'Lux Priorities','path':'lux-priorities','icon':'mdi:format-list-numbered',
       'cards':[
        {'type':'markdown','content':summary},
        {'type':'entities','title':'Lux stage controls','show_header_toggle':False,
         'entities':[{'entity':'input_number.general_outdoor_lighting_on_lux','name':'Lux start reference'},
                     {'entity':'input_number.general_lux_priority_boost','name':'How much earlier the first light starts'},
                     {'entity':'input_number.jns_lux_ladder_stage_gap','name':'Lux gap between lights'},
                     {'entity':'input_number.general_lighting_lux_hysteresis','name':'OFF hysteresis'},
                     {'entity':'input_number.general_lux_rain_boost','name':'Rain adjustment'},
                     {'entity':'binary_sensor.jns_lux_priority_bright_stable','name':'Bright stable for 20 min'},
                     {'entity':'input_boolean.jns_lux_manual_hold_all','name':'Pause all Lux control'}]},
        {'type':'grid','columns':2,'square':False,'cards':sections},
        {'type':'markdown','content':'**Safety:** manual OFF is respected until sunrise. Bedtime, WC PIR, security and protected-power automations are independent. New living-room/sofa outputs are OFF by default until you explicitly enable them. Priority affects the Lux engine, not physical manual switches.'}
       ]}
 text=raw.decode('utf-8')
 # Place one concise locator in the existing Controls view.
 marker='- title: Controls\n  path: controls\n'
 require(text.count(marker)==1,'Control view header changed')
 start=text.index(marker)+len(marker)
 cards=text.find('  cards:\n',start)
 nxt=text.find('\n- title:',start)
 require(cards>=0 and (nxt<0 or cards<nxt),'Controls card start ambiguous')
 insertion='  '+yaml.safe_dump([short],sort_keys=False,allow_unicode=True,width=160).replace('\n','\n  ').rstrip()+'\n'
 modified=text[:cards+len('  cards:\n')]+insertion+text[cards+len('  cards:\n'):]
 modified=modified.rstrip()+'\n'+yaml.safe_dump([view],sort_keys=False,allow_unicode=True,width=160)
 parsed=yaml.safe_load(modified)
 before={v.get('path'):v for v in original['views']}
 for v in parsed['views']:
  name=v.get('path')
  if name=='controls':
   old=before['controls']
   require(v['cards'][0]==short and v['cards'][1:]==old['cards'],'Existing control cards modified')
  elif name!='lux-priorities':
   require(v==before.get(name),'Unrelated dashboard view modified: '+str(name))
 require(len(parsed['views'])==len(original['views'])+1,'Unexpected dashboard views')
 return modified.encode()
def main():
 require(len(sys.argv)>=2,'Expect base64 approved package YAML')
 pkg=base64.b64decode(sys.argv[1])
 loaded=yaml.safe_load(pkg)
 require(isinstance(loaded,dict) and 'automation' in loaded and 'template' in loaded,'Missing staged priority package components')
 require(TAG in pkg.decode(),'Wrong priority package revision')
 require(not PACKAGE.exists(),'Priority ladder already installed; no duplicate')
 old={p:p.read_bytes() for p in (AUTO,DASH,MANUAL)}
 require(all(p.is_file() and not p.is_symlink() for p in old),'Existing config unavailable/symlink')
 # Refuse silently retargeting a commissioned light to a different output.
 reg=json.loads((ROOT/'.storage/core.entity_registry').read_text())['data']['entities']
 registered={e.get('entity_id'):e for e in reg}
 for i,n,e,r,initial in L:
  require(e in registered and registered[e].get('disabled_by') is None,'Known light missing/disabled: '+n)
 for i,n,e,r,initial in L[:6]:
  if i not in ('worktop','radiator'):
   require('lighting_lux_controlled' in (registered[e].get('labels') or []),
           'Formerly Lux-controlled entity changed: '+n)
 new={AUTO:make_automation(old[AUTO]),DASH:make_dashboard(old[DASH]),MANUAL:make_manual(old[MANUAL]),PACKAGE:pkg}
 report={'target_vm':905,'files':{str(p):{'before_sha256':sha(old[p]) if p in old else None,'after_sha256':sha(b)} for p,b in new.items()},
         'active_initial_order':[n for i,n,e,r,enabled in L if enabled],
         'opt_in_lights':[n for i,n,e,r,enabled in L if not enabled],
         'no_other_automation_modified':True,'manually_held_off_protected':True}
 print('JNS_LUX_LADDER_PLAN '+json.dumps(report),flush=True)
 if '--apply' not in sys.argv:return
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 backupdir=ROOT/'.jns-backups'/('lux-priority-ladder-'+stamp)
 backupdir.mkdir(mode=0o700,parents=True,exist_ok=False)
 for p,b in old.items():
  dest=backupdir/p.name
  require(not dest.exists(),'Backup name duplicate')
  dest.write_bytes(b)
  os.chmod(dest,0o600)
  require(dest.read_bytes()==b,'Backup read-back mismatch: '+str(p))
 applied=[]
 try:
  for p,b in new.items():
   if p in old:require(p.read_bytes()==old[p],'Concurrent change: '+str(p))
   else:require(not p.exists(),'Concurrent package creation')
   atomic(p,b);applied.append(p)
  require(all(p.read_bytes()==b for p,b in new.items()),'Post-write mismatch')
 except BaseException:
  for p in reversed(applied):
   if p.read_bytes()==new[p]:
    if p in old:atomic(p,old[p])
    else:p.unlink()
  raise
 print('JNS_LUX_LADDER_APPLIED '+json.dumps({'backup':str(backupdir),'files':report['files']},sort_keys=True),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_LUX_LADDER_BLOCKED '+type(e).__name__+': '+str(e)[:340],flush=True)
  sys.exit(2)
