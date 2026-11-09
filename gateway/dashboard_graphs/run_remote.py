import base64,json,sys,time,pathlib
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
source=pathlib.Path(sys.argv[1]).read_bytes()
code="exec(__import__('base64').b64decode('"+base64.b64encode(source).decode()+"'))"
vm='905'
args=['qm','guest','exec',vm,'--','docker','exec','homeassistant','python3','-c',code,*sys.argv[2:]]
r=json.loads(ssh_host('nodeb',args));pid=r.get('pid')
until=time.monotonic()+180
while not r.get('exited') and 'exitcode' not in r:
 if pid is None or time.monotonic()>until:raise RuntimeError('Guest completion unknown; no blind retry')
 time.sleep(2);r=json.loads(ssh_host('nodeb',['qm','guest','exec-status',vm,str(pid)]))
print(r.get('out-data',''),end='',flush=True)
if r.get('exitcode')!=0:
 print((r.get('err-data') or '')[-2000:],flush=True)
 raise SystemExit(1)
assert not r.get('out-truncated'),'Truncated result'
