#!/usr/bin/env python3
"""Read-only freshness audit for existing SM-S721B location, Wi-Fi and Bluetooth.
Does not print SSID/Bluetooth device identifiers or precise location.
"""
import sys, json, base64, time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
SRC=r"""
from pathlib import Path
import json,sqlite3,time,datetime
db=Path('/config/home-assistant_v2.db')
target=['device_tracker.sm_s721b','sensor.sm_s721b_wi_fi_connection',
        'sensor.sm_s721b_bluetooth_connection','binary_sensor.sm_s721b_bluetooth_state']
out={}
if not db.exists():
    print(json.dumps({'status':'no_sqlite_recorder','entries':{}}))
else:
    try:
        con=sqlite3.connect('file:/config/home-assistant_v2.db?mode=ro',uri=True,timeout=5)
        con.execute('PRAGMA query_only=ON')
        for eid in target:
            rec=con.execute(
              'SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON m.metadata_id=s.metadata_id '
              'WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 1', (eid,)).fetchone()
            if rec is None:
                out[eid]={'recorded':False}
                continue
            state,stamp=rec
            state=str(state or '').strip()
            if state.lower() in ('unknown','unavailable','', 'none','null'):
                status='not_usable'
            elif eid.endswith('wi_fi_connection'):
                status='not_connected' if state.lower() in ('not connected','disconnected','none') else 'connected_ssid_redacted'
            elif eid.startswith('device_tracker.'):
                status=state if state in ('home','not_home') else 'other_zone_or_state'
            elif eid.endswith('bluetooth_state'):
                status='on' if state=='on' else ('off' if state=='off' else 'other')
            else:
                status='connected_device_redacted' if state.lower() not in ('not connected','disconnected') else 'not_connected'
            out[eid]={'recorded':True,'classification':status,
                      'age_minutes':round((time.time()-(stamp or 0))/60,1) if stamp else None}
        con.close()
        print(json.dumps({'status':'ok','entries':out},sort_keys=True))
    except Exception as exc:
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__}))
"""
def guest(node,vm,code):
    enc=base64.b64encode(code.encode()).decode()
    arg="exec(__import__('base64').b64decode('"+enc+"'))"
    cmd=['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',arg]
    response=json.loads(ssh_host(node,cmd))
    pid=response.get('pid')
    for n in range(35):
        if response.get('exited'): break
        if not isinstance(pid,int): raise RuntimeError('missing_guest_pid')
        time.sleep(1)
        response=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
    if not response.get('exited') or response.get('exitcode')!=0:
        raise RuntimeError('guest_command_failed')
    return json.loads(response.get('out-data') or '{}')
try:
    print('HA_PRIMARY_SAMSUNG_PRESENCE_FRESHNESS',json.dumps(guest('nodea',902,SRC),sort_keys=True))
except Exception as e:
    print('HA_PRIMARY_SAMSUNG_PRESENCE_FRESHNESS',json.dumps({'status':'blocked','error':str(e)[:100]}))
