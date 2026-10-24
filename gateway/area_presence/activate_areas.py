#!/usr/bin/env python3
"""Node C live promotion uses MQTT preview approval & Core-native checks."""
import base64,json,re,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'gateway/area_presence')
from primary_runner import guest
from readiness_probe import ssh_host
expected=['bedroom_baileys','dogs_run','hallway','snug','summer_house','wc']
def report():
 raw=ssh_host('nodeb',['pct','exec','212','--','timeout','15','mosquitto_sub','-h','mqtt-infra-a.home.arpa','-p','1883','-t','jns/site/areas/sync/ha-primary','-C','1','-W','12'])
 return json.loads(raw)
r=report()
if r.get('mode')!='dry_run' or r.get('conflicts') or sorted(r.get('missing',[]))!=expected:
 raise RuntimeError('MQTT area preview not conflict-free or changed; no promotion')
print('JNS_AREA_CONFLICT_FREE_PREVIEW '+json.dumps({'missing':r['missing'],'conflicts':r['conflicts']}),flush=True)
script=Path('gateway/area_presence/promote_vm902.py').read_bytes()
expr="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(script).decode())+"),'<area-promote>','exec'))"
def call(mode):
 res=guest(['docker','exec','homeassistant','python3','-c',expr,mode],80)
 out=res.get('out-data') or ''
 print('JNS_AREA_'+mode+' '+out[-1500:],flush=True)
 if res.get('exitcode')!=0:raise RuntimeError('area promotion failed '+str(res.get('err-data',''))[-300:])
 return out
def ha(args,limit=400):
 res=guest(['ha',*args],limit)
 print('JNS_AREA_HA '+json.dumps({'cmd':' '.join(args),'exitcode':res.get('exitcode'),
   'out_tail':(res.get('out-data') or '')[-300:]}),flush=True)
 return res.get('exitcode')==0
call('--dry-run')
out=call('--apply')
m=re.search(r'JNS_AREA_PROMOTION_APPLIED (\{.+\})',out)
if not m:raise RuntimeError('missing apply report')
manifest=json.loads(m.group(1))
try:valid=ha(['core','check'],320)
except Exception:valid=False
if not valid:
 rollback="from pathlib import Path;import hashlib; p=Path('/config/configuration.yaml'); old=Path("+repr(manifest['backup'])+").read_bytes(); new_sha="+repr(manifest['new_sha'])+"; assert hashlib.sha256(p.read_bytes()).hexdigest()==new_sha; p.write_bytes(old); print('JNS_AREA_RESTORED')"
 rb=guest(['docker','exec','homeassistant','python3','-c',rollback],80)
 print('JNS_AREA_ROLLBACK '+(rb.get('out-data') or '')[-300:],flush=True)
 raise RuntimeError('Area enable config check failed; restart prevented')
print('JNS_AREA_PROMOTION_CONFIG_VALID',flush=True)
if not ha(['core','restart'],520):raise RuntimeError('Core restart exit not confirmed')
if not ha(['core','info'],120):raise RuntimeError('Core health after restart not confirmed')
print('JNS_AREA_PROMOTION_CORE_STARTED',flush=True)
