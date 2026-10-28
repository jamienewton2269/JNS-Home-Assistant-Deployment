#!/usr/bin/env python3
"""Read-only Lux off-delay and dashboard insertion structure inspection."""
import sys,base64,json,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
P=r'''
import pathlib,json,yaml,re
R=pathlib.Path('/config')
f={}
for p in sorted((R/'packages').glob('*.yaml')):
 t=p.read_text()
 if 'jns_lux_bright_enough_for_off' in t or 'general_lux_safe_to_switch_off' in t or 'jns_lighting_effective_lux' in t:
  lines=t.splitlines()
  rows=[{'line':i+1,'text':s[:170]} for i,s in enumerate(lines) if re.search('jns_lux_bright_enough_for_off|general_lux_safe_to_switch_off|jns_lighting_effective_lux|delay_on|off_lux|hysteresis|safe_to',s)]
  f[p.name]={'matched':rows[:50],'content':t[:9500]}
d=yaml.safe_load((R/'dashboards/testing.yaml').read_text())
view=next(x for x in d['views'] if x.get('path')=='lighting-settings')
print('JNS_LUX_STAGE_DETAIL',json.dumps({'template_sources':f,'lighting_settings_cards':[{'title':c.get('title'),'type':c.get('type'),'entities':c.get('entities',[])[:12]} for c in view['cards']]},default=str))
'''
def guest(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 for i in range(50):
  if r.get('exited'):return r
  if not isinstance(r.get('pid'),int):raise RuntimeError('missing PID')
  time.sleep(1)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 raise RuntimeError('timed out')
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(P.encode()).decode())+"))"
r=guest(['docker','exec','homeassistant','python3','-c',code])
print((r.get('out-data') or '')[-26000:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError((r.get('err-data') or '')[-250:])
