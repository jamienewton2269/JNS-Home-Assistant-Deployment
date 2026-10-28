#!/usr/bin/env python3
"""Scoped, hash-guarded addition of an 18C thermostat setpoint on bedtime activation.
Dry-run by default; execute inside HA-General Core via the existing JNS gateway.
"""
from pathlib import Path
import copy,datetime,hashlib,json,os,re,stat,sys,tempfile,yaml
ROOT=Path('/config')
P=ROOT/'packages/jns_bedtime_controller.yaml'
EXPECTED='74738f272f63514322bfa4ccf1dcec42a6d53e0aa510a8e08ce473d5a3093a8b'
ENTITY='climate.thermostat_thermostat'
ID='jns_bedtime_trigger_on_mode'
def req(x,m):
 if not x:raise RuntimeError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def atomic(path,data):
 s=path.stat()
 fd,tmp=tempfile.mkstemp(prefix='.jns-heat18-',dir=str(path.parent))
 try:
  with os.fdopen(fd,'wb') as f:
   f.write(data);f.flush();os.fsync(f.fileno())
  os.chown(tmp,s.st_uid,s.st_gid)
  os.chmod(tmp,stat.S_IMODE(s.st_mode))
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def main():
 req(P.is_file() and not P.is_symlink(),'Bedtime YAML missing or symlink')
 old=P.read_bytes()
 req(sha(old)==EXPECTED,'Live bedtime package differs from audited SHA; refusing concurrent edits')
 original=yaml.safe_load(old)
 req(isinstance(original,dict) and isinstance(original.get('automation'),list),'Bad package structure')
 candidates=[x for x in original['automation'] if x.get('id')==ID]
 req(len(candidates)==1,'Bedtime trigger must be unique')
 a=candidates[0]
 req(a.get('alias')=='JNS Bedtime - dashboard or hallway activation','Bedtime activation alias mismatch')
 triggers=a.get('triggers',[])
 req(len(triggers)==1 and triggers[0]=={'trigger':'state','entity_id':'input_boolean.general_bedtime_mode','from':'off','to':'on'},'Unexpected mode transition trigger')
 seq=a.get('actions',[])
 req(len(seq)==1 and seq[0]=={'action':'script.jns_bedtime_shutdown'},'Unexpected bedtime action sequence; refusing edit')
 reg=json.loads((ROOT/'.storage/core.entity_registry').read_text())['data']['entities']
 req(len([x for x in reg if x.get('entity_id')==ENTITY and not x.get('disabled_by')])==1,'Honeywell climate entity missing/disabled')
 updated=copy.deepcopy(original)
 newact=next(x for x in updated['automation'] if x.get('id')==ID)
 heat={'action':'climate.set_temperature','target':{'entity_id':ENTITY},'data':{'temperature':18},'continue_on_error':True}
 newact['actions'].insert(0,heat)
 # Splice only existing automation's action list; other YAML text remains byte-identical.
 text=old.decode('utf-8')
 start=re.search(r'(?m)^[ ]{0,2}- id: '+ID,text)
 req(start is not None,'Raw bedtime automation block absent')
 nxt=re.search(r'(?m)^[ ]{0,2}- id:',text[start.end():])
 end=start.end()+nxt.start() if nxt else len(text)
 block=text[start.start():end]
 anchor='  - action: script.jns_bedtime_shutdown\n'
 req(block.count(anchor)==1,'Raw script action anchor missing or duplicated')
 snippet=('  - action: climate.set_temperature\n'
          '    target:\n'
          '      entity_id: climate.thermostat_thermostat\n'
          '    data:\n'
          '      temperature: 18\n'
          '    continue_on_error: true\n')
 new=(text[:start.start()]+block.replace(anchor,snippet+anchor,1)+text[end:]).encode('utf-8')
 req(yaml.safe_load(new)==updated,'YAML semantic comparison failed')
 # Confirm no other aliases, triggers, scripts or steps semantically changed.
 req(len(updated['automation'])==len(original['automation']),'Automation count changed')
 report={'file':str(P),'old_sha256':sha(old),'new_sha256':sha(new),'automation_id':ID,
         'heating_entity':ENTITY,'target_celsius':18,'keeps_bedtime_shutdown':True,
         'continue_on_thermostat_error':True}
 print('JNS_BEDTIME_HEAT18_PLAN '+json.dumps(report),flush=True)
 if '--apply' not in sys.argv:return
 backupdir=ROOT/'.jns-backups'/('bedtime-heating18-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 backupdir.mkdir(parents=True,exist_ok=False,mode=0o700)
 backup=backupdir/P.name
 backup.write_bytes(old);os.chmod(backup,0o600)
 req(backup.read_bytes()==old,'Backup verification failed')
 req(P.read_bytes()==old,'Concurrent modification detected before install')
 atomic(P,new)
 req(P.read_bytes()==new,'Write verification failed')
 print('JNS_BEDTIME_HEAT18_APPLIED '+json.dumps({'backup':str(backup),'target':str(P),
       'before_sha256':sha(old),'after_sha256':sha(new)}),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_BEDTIME_HEAT18_BLOCKED '+type(e).__name__+': '+str(e)[:230],flush=True)
  sys.exit(2)
