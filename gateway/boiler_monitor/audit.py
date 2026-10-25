#!/usr/bin/env python3
import sys,json
sys.path.insert(0,'gateway/boiler_monitor')
from deploy import guest,core
P=r"""
import pathlib,json,sqlite3,urllib.request
root=pathlib.Path('/config')
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
print('BOILER_REGISTRY',json.dumps([{k:e.get(k) for k in ('entity_id','unique_id','disabled_by','platform')} for e in reg if 'boiler' in e.get('entity_id','') or 'boiler' in str(e.get('unique_id',''))]))
db=sqlite3.connect('file:/config/home-assistant_v2.db?mode=ro',uri=True,timeout=3)
print('RECORDED_BOILER',json.dumps(db.execute("SELECT m.entity_id,s.state,s.last_updated_ts FROM states s JOIN states_meta m USING(metadata_id) WHERE m.entity_id LIKE '%jns_boiler%' ORDER BY s.last_updated_ts DESC LIMIT 15").fetchall()))
print('RECORDER_LATEST_UPDATE',db.execute('select max(last_updated_ts) from states').fetchone())
try:
 with urllib.request.urlopen('http://127.0.0.1:8123/',timeout=6) as r:print('CORE_HTTP_STATUS',r.status)
except Exception as e:print('CORE_HTTP_STATUS_ERROR',type(e).__name__)
"""
print(core(P),flush=True)
cmd="docker logs --tail 1500 homeassistant 2>&1 | grep -Ei 'boiler|invalid config|setup failed|error setting up|home assistant initialized|starting home assistant|setup of domain' | grep -Eiv 'token|secret|password|bearer|authorization' | tail -30 | cut -c 1-450"
r=guest(['sh','-c',cmd])
print('CORE_FILTERED_SETUP_LOG',r.get('out-data','')[-10000:],flush=True)
