#!/usr/bin/env python3
"""Guarded two-file JNS HA-General predictive heating / bedtime learning installation.
Dry-run by default, never touches security packages or an existing bedtime script.
"""
import base64,datetime,hashlib,json,os,stat,sys,tempfile
from pathlib import Path
import yaml
ROOT=Path('/config')
DASH=ROOT/'dashboards/testing.yaml'
PKG=ROOT/'packages/jns_heating_predictive_schedule.yaml'
VALID_ALARMS={'alarm_control_panel.home_alarm','alarm_control_panel.house_alarm'}
def check(condition,message):
 if not condition:raise RuntimeError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def write_atomic(path,new):
 st=path.stat() if path.exists() else None
 fd,tmp=tempfile.mkstemp(prefix='.jns-heating-presence-',dir=str(path.parent))
 try:
  with os.fdopen(fd,'wb') as f:
   f.write(new);f.flush();os.fsync(f.fileno())
  if st:
   os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode))
  else:os.chmod(tmp,0o644)
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def add_card(raw,path,card):
 text=raw.decode('utf-8')
 marker='  path: '+path+'\n'
 check(text.count(marker)==1,'Dashboard view not unique: '+path)
 pos=text.index(marker)
 start=text.rfind('- title:',0,pos)
 check(start>=0,'Dashboard view title not found')
 nextview=text.find('\n- title:',pos)
 if nextview<0:nextview=len(text)
 cardheader=text.find('  cards:\n',pos,nextview)
 check(cardheader>=0,'View card list not found: '+path)
 insert=cardheader+len('  cards:\n')
 check('JNS Heating - Predictive Schedule' not in text[pos:nextview],'Heating schedule cards already installed')
 return (text[:insert]+card+text[insert:]).encode()
CONTROL='''  - type: entities
    title: JNS Heating - Predictive Schedule
    show_header_toggle: false
    entities:
      - entity: input_boolean.jns_heating_automatic_override
        name: Manual override - suspend automatic setpoint changes
      - entity: input_number.jns_heating_away_minimum_temp
        name: Minimum house temperature when armed away
      - entity: input_boolean.jns_heating_bedtime_learning_paused
        name: Pause learning normal bedtime
      - entity: sensor.jns_heating_verified_alarm_state
        name: Alarm mode
      - entity: sensor.jns_heating_schedule_decision
        name: Automatic heating decision
      - entity: sensor.jns_heating_learned_bedtime
        name: Learned typical bedtime
      - entity: sensor.jns_heating_predictive_preheat_minutes
        name: Predicted heating lead to 21C
      - entity: sensor.jns_heating_predictive_cooling_minutes
        name: Predicted natural cooling lead
'''
HEATING='''  - type: entities
    title: JNS Heating - Predictive Schedule and Bedtime Learning
    show_header_toggle: false
    entities:
      - entity: input_boolean.jns_heating_automatic_override
        name: Suspend automatic heating changes
      - entity: input_number.jns_heating_away_minimum_temp
        name: Armed-away minimum temperature
      - entity: input_boolean.jns_heating_bedtime_learning_paused
        name: Pause bedtime learning
      - entity: sensor.jns_heating_learned_bedtime
        name: Average bedtime
      - entity: input_number.jns_heating_bedtime_samples
        name: Bedtime observations
      - entity: sensor.jns_heating_predictive_preheat_minutes
        name: Minutes needed to reach 21C
      - entity: sensor.jns_heating_predictive_cooling_minutes
        name: Minutes to cool towards 18C
      - entity: sensor.jns_heating_schedule_decision
        name: Current decision
'''
def main():
 data=base64.b64decode(sys.argv[1])
 check(not PKG.exists() and PKG.parent.is_dir(),'Heating schedule already installed')
 check(DASH.exists() and not DASH.is_symlink(),'Dashboard missing or symlink')
 p=yaml.safe_load(data)
 check(isinstance(p,dict) and set(['automation','template','input_number','input_boolean','input_datetime']).issubset(p),'Package does not contain required controls')
 ids=[x.get('id') for x in p['automation']]
 check(ids==['jns_heating_learn_bedtime_v1','jns_heating_alarm_predictive_target_v1'],'Package automation identities unexpected')
 checks=[str(p['automation'][1]),str(p['template'])]
 check(all(x in checks[0]+' '.join(checks[1:]) for x in VALID_ALARMS),'Alarm fail-closed source checks missing')
 check('climate.thermostat_thermostat' in str(p),'Honeywell target missing')
 existing=DASH.read_bytes()
 orig=yaml.safe_load(existing)
 check(isinstance(orig,dict) and isinstance(orig.get('views'),list),'Dashboard invalid root')
 newdash=add_card(add_card(existing,'controls',CONTROL),'house-temperature',HEATING)
 check(yaml.safe_load(newdash).get('views'),'Modified dashboard YAML invalid')
 original_views={v.get('path'):v for v in orig['views']}
 modified=yaml.safe_load(newdash)
 for v in modified['views']:
  name=v.get('path')
  if name not in ('controls','house-temperature'):
   check(v==original_views.get(name),'Unexpected changes to dashboard view '+str(name))
  else:
   oldview=original_views.get(name)
   check(v.get('cards',[])[1:]==oldview.get('cards',[]),'Original dashboard cards changed: '+str(name))
 report={'status':'planned','package':str(PKG),'dashboard':str(DASH),
   'package_sha':sha(data),'dashboard_old_sha':sha(existing),'dashboard_new_sha':sha(newdash),
   'alarm_fail_closed':True,'prediction_uses_existing_learner':True,
   'adds_controls_to':['controls','house-temperature']}
 print('JNS_HEATING_PRESENCE_PLAN '+json.dumps(report),flush=True)
 if '--apply' not in sys.argv:return
 backupdir=ROOT/'.jns-backups'/('heating-presence-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 backupdir.mkdir(parents=True,mode=0o700,exist_ok=False)
 backup=backupdir/'testing.yaml'
 backup.write_bytes(existing);os.chmod(backup,0o600)
 check(backup.read_bytes()==existing,'Backup verification failed')
 check(not PKG.exists() and DASH.read_bytes()==existing,'Concurrent configuration change')
 write_atomic(PKG,data)
 write_atomic(DASH,newdash)
 check(PKG.read_bytes()==data and DASH.read_bytes()==newdash,'Post-write verification failed')
 print('JNS_HEATING_PRESENCE_APPLIED '+json.dumps({
   'backup':str(backup),'package':str(PKG),'dashboard':str(DASH),
   'package_sha':sha(data),'dashboard_before':sha(existing),'dashboard_after':sha(newdash)}),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_HEATING_PRESENCE_BLOCKED '+type(e).__name__+': '+str(e)[:300],flush=True)
  sys.exit(2)
