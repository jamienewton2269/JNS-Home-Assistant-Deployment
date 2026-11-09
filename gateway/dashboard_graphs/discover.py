import sys,json
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','ps','--format','{{.Names}}']))
print('HA_CONTAINERS',r.get('out-data',''),flush=True)
