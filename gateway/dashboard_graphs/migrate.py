"""Transactional graph migration via existing Node C SSH/QGA and Core API."""
import sys,pathlib,base64,json,time,os,hashlib,copy,yaml
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
from convert_graphs import convert,CARD,graph_count
HERE=pathlib.Path('gateway/dashboard_graphs')
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
def core(source,*args,container='homeassistant'):
 code="exec(__import__('base64').b64decode('"+base64.b64encode(source.encode()).decode()+"'))"
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','exec',container,'python3','-c',code,*args]));pid=r.get('pid');until=time.monotonic()+150
 while not r.get('exited') and 'exitcode' not in r:
  if pid is None or time.monotonic()>until:raise RuntimeError('Guest completion unknown; inspect before retry')
  time.sleep(2);r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 if r.get('exitcode')!=0:raise RuntimeError('Guest operation failed: '+(r.get('err-data') or '')[-500:])
 if r.get('out-truncated'):raise RuntimeError('Guest response truncated')
 return r.get('out-data','')
def rpc(commands):
 raw=core((HERE/'api_rpc.py').read_text(),base64.b64encode(json.dumps(commands).encode()).decode(),container='app_local_jns_guest_alarm')
 rs=json.loads(raw)
 for r in rs:
  if not r.get('success'):raise RuntimeError('Dashboard API rejected operation: '+str(r.get('error',{}).get('code')))
 return [r.get('result') for r in rs]
SNAPSHOT=r'''
import pathlib,json,base64,yaml,os,hashlib
R=pathlib.Path('/config');files=list((R/'dashboards').glob('*.yaml'))+list((R/'lovelace').glob('*.yaml'))
if (R/'ui-lovelace.yaml').exists():files.append(R/'ui-lovelace.yaml')
out=[]
for p in files:
 if p.is_symlink():raise RuntimeError('Dashboard symlink needs explicit review')
 try:d=yaml.safe_load(p.read_text())
 except yaml.YAMLError:continue
 if not isinstance(d,dict) or 'views' not in d:continue
 out.append({'path':str(p.relative_to(R)),'raw':base64.b64encode(p.read_bytes()).decode(),'config':d})
print(json.dumps(out,separators=(',',':')))
'''
BACKUP=r'''
import pathlib,json,sys,base64,os
R=pathlib.Path('/config');data=json.loads(base64.b64decode(sys.argv[1]));b=R/'.jns-backups'/('graph-card-'+sys.argv[2]);b.mkdir(parents=True,mode=0o700,exist_ok=False)
for i,x in enumerate(data['yaml']):
 p=R/x['path'];old=base64.b64decode(x['raw']);assert p.read_bytes()==old,'Concurrent YAML edit'
 q=b/('yaml-'+str(i)+'.yaml');q.write_bytes(old);q.chmod(0o600)
 q=b/('yaml-'+str(i)+'-proposed.yaml');q.write_bytes(base64.b64decode(x['new_raw']));q.chmod(0o600)
(b/'transaction.json').write_text(json.dumps(data));(b/'transaction.json').chmod(0o600)
print(str(b))
'''
WRITE=r'''
import pathlib,json,sys,base64,os,tempfile,stat,yaml
b=pathlib.Path(sys.argv[1]);assert b.parent==pathlib.Path('/config/.jns-backups') and b.name.startswith('graph-card-')
t=json.loads((b/'transaction.json').read_text());written=[]
try:
 for x in t['yaml']:
  p=pathlib.Path('/config')/x['path'];old=base64.b64decode(x['raw']);new=base64.b64decode(x['new_raw'])
  assert not p.is_symlink() and p.read_bytes()==old,'Concurrent YAML edit'
  st=p.stat();fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.graph-card-')
  try:
   with os.fdopen(fd,'wb') as f:f.write(new);f.flush();os.fsync(f.fileno())
   os.chmod(tmp,stat.S_IMODE(st.st_mode));os.chown(tmp,st.st_uid,st.st_gid)
   assert p.read_bytes()==old;os.replace(tmp,p);written.append(x)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
  assert p.read_bytes()==new and yaml.safe_load(new)==x['new_config']
except Exception:
 for x in written:
  p=pathlib.Path('/config')/x['path']
  if p.read_bytes()==base64.b64decode(x['new_raw']):p.write_bytes(base64.b64decode(x['raw']))
 raise
print('YAML_APPLIED',len(written))
'''
ROLLBACK=r'''
import pathlib,json,sys,base64
b=pathlib.Path(sys.argv[1]);assert b.parent==pathlib.Path('/config/.jns-backups') and b.name.startswith('graph-card-')
t=json.loads((b/'transaction.json').read_text())
for x in t['yaml']:
 p=pathlib.Path('/config')/x['path'];new=base64.b64decode(x['new_raw']);old=base64.b64decode(x['raw'])
 assert p.read_bytes() in (new,old),'Concurrent edit; rollback stopped'
for x in t['yaml']:(pathlib.Path('/config')/x['path']).write_bytes(base64.b64decode(x['raw']))
print('YAML_ROLLED_BACK')
'''
def patch_yaml(raw,meta,expected):
 # Preserve comments and unrelated YAML text, replacing only native graph maps.
 text=raw.decode();root=yaml.compose(text);replacements=[]
 def visit(node):
  if isinstance(node,yaml.MappingNode):
   typ=next((v.value for k,v in node.value if k.value=='type' and isinstance(v,yaml.ScalarNode)),None)
   if typ in ('history-graph','statistics-graph'):
    obj=yaml.safe_load(yaml.serialize(node));new,_=convert(obj,meta)
    dump=yaml.safe_dump(new,sort_keys=False,allow_unicode=True)
    lines=dump.splitlines(keepends=True);pad=' '*node.start_mark.column
    rendered=lines[0]+''.join(pad+l for l in lines[1:])
    end=node.end_mark.index-node.end_mark.column
    replacements.append((node.start_mark.index,end,rendered));return
   for _,v in node.value:visit(v)
  elif isinstance(node,yaml.SequenceNode):
   for v in node.value:visit(v)
 visit(root)
 for start,end,new in sorted(replacements,reverse=True):text=text[:start]+new+text[end:]
 assert yaml.safe_load(text)==expected,'YAML patch changed unrelated structure'
 return text.encode()
def main():
 runid=os.environ.get('GITHUB_RUN_ID','local');assert runid.isdecimal()
 resources,dashboards,meta=rpc([{'type':'lovelace/resources'},{'type':'lovelace/dashboards/list'},{'type':'__metadata'}])
 # The already installed card is reused; no download or extra graph dependency.
 matches=[r for r in resources if 'statistics-graph-chart-card' in r.get('url','').lower()]
 assert len(matches)<=1,'Duplicate graph resource needs review'
 yfiles=json.loads(core(SNAPSHOT));yc=[];sc=[];counts={}
 for x in yfiles:
  new,n=convert(x['config'],meta)
  if not n:continue
  x['new_config']=new;x['new_raw']=base64.b64encode(patch_yaml(base64.b64decode(x['raw']),meta,new)).decode();x['count']=n
  yc.append(x);counts[x['path']]=n
 # Storage dashboards use Core's API, never direct writes to active .storage.
 targets=[{'url_path':d['url_path']} for d in dashboards if d.get('mode')=='storage']
 # Include default dashboard only if explicitly configured in storage.
 for target in targets:
  old=rpc([{'type':'lovelace/config',**target}])[0]
  new,n=convert(old,meta)
  if n:sc.append({'target':target,'old':old,'new':new,'count':n});counts[target['url_path']]=n
 total=sum(counts.values())
 print('GRAPH_PLAN',json.dumps({'native_graphs':total,'targets':counts,'resource_registered':bool(matches)}),flush=True)
 if not total:print('GRAPH_ALREADY_MIGRATED',flush=True);return
 data={'yaml':yc,'storage':sc,'resources_before':resources,'counts':counts}
 backup=core(BACKUP,base64.b64encode(json.dumps(data).encode()).decode(),runid).strip()
 print('GRAPH_BACKUP_VERIFIED',backup,flush=True)
 if '--apply' not in sys.argv:print('GRAPH_DRY_RUN_OK',flush=True);return
 saved=[];resource_id=None;yaml_written=False
 try:
  # Register once if the Marketplace installed the files but no resource exists.
  if not matches:
   rr=rpc([{'type':'lovelace/resources/create','res_type':'module','url':'/local/community/Statistics-Graph-Chart-Card/statistics-graph-chart-card.js'}])[0]
   resource_id=rr['id']
  for x in sc:
   assert rpc([{'type':'lovelace/config',**x['target']}])[0]==x['old'],'Concurrent storage dashboard edit'
   rpc([{'type':'lovelace/config/save',**x['target'],'config':x['new']}]);saved.append(x)
   assert rpc([{'type':'lovelace/config',**x['target']}])[0]==x['new'],'Storage readback mismatch'
  print(core(WRITE,backup),end='',flush=True);yaml_written=True
  # YAML views are loaded on demand; force each registered YAML dashboard to
  # reload so config/readback verifies the actual serving path.
  verified=[]
  for d in dashboards:
   cfg=rpc([{'type':'lovelace/config','url_path':d['url_path'],'force':True}])[0]
   assert graph_count(cfg,{'history-graph','statistics-graph'})==0,'Native graph remains in registered dashboard'
   if graph_count(cfg,{CARD}):verified.append({'dashboard':d['url_path'],'graphs':graph_count(cfg,{CARD})})
  print('GRAPH_MIGRATION_VERIFIED',json.dumps({'converted':total,'targets':counts,'api_readback':verified,'backup':backup,'core_restart':False,'entity_values_changed':False}),flush=True)
 except Exception:
  if yaml_written:print(core(ROLLBACK,backup),end='',flush=True)
  for x in reversed(saved):
   current=rpc([{'type':'lovelace/config',**x['target']}])[0]
   if current==x['new']:rpc([{'type':'lovelace/config/save',**x['target'],'config':x['old']}])
  if resource_id:rpc([{'type':'lovelace/resources/delete','resource_id':resource_id}])
  print('GRAPH_TRANSACTION_ROLLED_BACK',flush=True);raise
if __name__=='__main__':main()
