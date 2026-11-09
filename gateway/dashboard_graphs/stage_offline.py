"""Stage all graph changes locally before a short, transactional Core restart."""
import pathlib,json,base64,sys,os,hashlib,stat,sqlite3,yaml,copy,shlex
R=pathlib.Path('/config')
runid=sys.argv[-1];assert runid.isdecimal()
b=R/'.jns-backups'/('graph-card-'+runid)
assert not b.exists(),'Transaction already staged; inspect before rerun'
def h(x):return hashlib.sha256(x).hexdigest()
class ConfigLoader(yaml.SafeLoader):pass
ConfigLoader.add_multi_constructor('!',lambda loader,tag,node: None)
configraw=(R/'configuration.yaml').read_bytes()
cfg=yaml.load(configraw,Loader=ConfigLoader)
ll=cfg.get('lovelace',{}) or {}
resource_url='/local/community/Statistics-Graph-Chart-Card/statistics-graph-chart-card.js'
js=R/'www/community/Statistics-Graph-Chart-Card/statistics-graph-chart-card.js'
assert js.is_file() and js.stat().st_size>10000,'Chosen graph card is not installed'
assert (js.parent/'translations.js').is_file(),'Installed graph translation file missing'
files=list((R/'dashboards').glob('*.yaml'))+list((R/'lovelace').glob('*.yaml'))+list((R/'.storage').glob('lovelace*'))
if (R/'ui-lovelace.yaml').is_file():files.append(R/'ui-lovelace.yaml')
docs=[];ids=set()
def findids(x):
 if isinstance(x,dict):
  if x.get('type') in ('history-graph','statistics-graph'):
   for e in x.get('entities',[]):ids.add(entity_id(e))
  for v in x.values():findids(v)
 elif isinstance(x,list):
  for v in x:findids(v)
for p in sorted(set(files)):
 assert not p.is_symlink(),'Symlink dashboard requires review'
 raw=p.read_bytes()
 try:obj=json.loads(raw) if p.parent.name=='.storage' else yaml.safe_load(raw)
 except (yaml.YAMLError,json.JSONDecodeError):continue
 if graph_count(obj,{'history-graph','statistics-graph'}):docs.append((p,raw,obj));findids(obj)
meta={}
db=R/'home-assistant_v2.db'
if db.exists():
 con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=10)
 for eid in ids:
  row=con.execute('SELECT s.state,a.shared_attrs FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id LEFT JOIN state_attributes a ON s.attributes_id=a.attributes_id WHERE m.entity_id=? ORDER BY s.last_updated_ts DESC LIMIT 1',(eid,)).fetchone()
  if row:
   a=json.loads(row[1] or '{}');v=row[0]
   try:num=__import__('math').isfinite(float(v))
   except (ValueError,TypeError):num=False
   meta[eid]={'unit':a.get('unit_of_measurement',''),'state_class':a.get('state_class'),'numeric':num,'categorical':not num and v not in ('unknown','unavailable'),'name':a.get('friendly_name')}
 con.close()
changes=[];counts={};samples=[]
for p,raw,obj in docs:
 new,n=convert(obj,meta)
 assert graph_count(new,{'history-graph','statistics-graph'})==0
 assert graph_count(new,{CARD})==graph_count(obj,{CARD})+n
 if p.parent.name=='.storage':updated=(json.dumps(new,ensure_ascii=False,indent=2)+'\n').encode()
 else:updated=patch_yaml(raw,meta,new)
 counts[str(p.relative_to(R))]=n
 changes.append({'path':str(p.relative_to(R)),'old':raw,'new':updated,'count':n})
 # Keep private samples for local browser validation without exposing readings.
 def take(x):
  if isinstance(x,dict):
   if x.get('type')==CARD:samples.append(x)
   for v in x.values():take(v)
  elif isinstance(x,list):
   for v in x:take(v)
 take(new)
resource_registered=False
if ll.get('mode')=='yaml':
 resources=ll.get('resources',[]) or []
 assert isinstance(resources,list),'Included resource file requires separate review'
 resource_registered=any('statistics-graph-chart-card' in x.get('url','').lower() for x in resources if isinstance(x,dict))
 if not resource_registered:
  text=configraw.decode();node=yaml.compose(text)
  ln=next(v for k,v in node.value if k.value=='lovelace')
  rn=next((v for k,v in ln.value if k.value=='resources'),None)
  newresources=resources+[{'url':resource_url,'type':'module'}]
  if rn:
   assert isinstance(rn,yaml.SequenceNode),'Resource include requires separate review'
   start=rn.start_mark.index;end=rn.end_mark.index-rn.end_mark.column
   dump=yaml.safe_dump(newresources,sort_keys=False);pad=' '*rn.start_mark.column
   lines=dump.splitlines(keepends=True);replacement=lines[0]+''.join(pad+l for l in lines[1:])
   text=text[:start]+replacement+text[end:]
  else:
   end=ln.end_mark.index-ln.end_mark.column
   text=text[:end]+'  resources:\n'+''.join('  '+l for l in yaml.safe_dump(newresources,sort_keys=False).splitlines(keepends=True))+text[end:]
  expected=copy.deepcopy(cfg);expected['lovelace']['resources']=newresources
  assert yaml.load(text,Loader=ConfigLoader)==expected,'Resource patch changed unrelated config'
  changes.append({'path':'configuration.yaml','old':configraw,'new':text.encode(),'count':0})
else:
 p=R/'.storage/lovelace_resources';raw=p.read_bytes() if p.exists() else None
 obj=json.loads(raw) if raw else {'version':1,'minor_version':1,'key':'lovelace_resources','data':{'items':[]}}
 resources=obj['data'].setdefault('items',[])
 resource_registered=any('statistics-graph-chart-card' in x.get('url','').lower() for x in resources)
 if not resource_registered:
  resources.append({'id':__import__('uuid').uuid4().hex,'url':resource_url,'type':'module'})
  changes.append({'path':'.storage/lovelace_resources','old':raw,'new':(json.dumps(obj,indent=2)+'\n').encode(),'count':0})
assert 1<=sum(counts.values())<=150,'Unexpected graph count or already migrated'
b.mkdir(parents=True,mode=0o700);(b/'original').mkdir(mode=0o700);(b/'proposed').mkdir(mode=0o700)
manifest=[]
hostroot='/mnt/data/supervisor/homeassistant'
guards=[];writes=[];rollbacks=[]
for i,x in enumerate(changes):
 rel=x['path'];assert '..' not in pathlib.PurePosixPath(rel).parts and '\n' not in rel and not rel.startswith('/')
 target=hostroot+'/'+rel;qtarget=shlex.quote(target)
 if x['old'] is not None:
  p=b/'original'/str(i);p.write_bytes(x['old']);p.chmod(0o600)
  guards.append('test "$(sha256sum '+qtarget+' | cut -d\' \' -f1)" = '+h(x['old']))
 else:guards.append('test ! -e '+qtarget)
 p=b/'proposed'/str(i);p.write_bytes(x['new']);p.chmod(0o600)
 hstage=hostroot+'/.jns-backups/'+b.name
 proposed=shlex.quote(hstage+'/proposed/'+str(i));original=shlex.quote(hstage+'/original/'+str(i));tmp=shlex.quote(target+'.graph-card-'+runid)
 writes+=['test ! -L '+qtarget,'test ! -e '+tmp,
          ('cp -p '+qtarget+' '+tmp) if x['old'] is not None else ('touch '+tmp+'; chmod 600 '+tmp),
          'cat '+proposed+' > '+tmp,'test "$(sha256sum '+tmp+' | cut -d\' \' -f1)" = '+h(x['new']),
          'mv '+tmp+' '+qtarget]
 if x['old'] is None:rollbacks.append('if test -f '+qtarget+' && test "$(sha256sum '+qtarget+' | cut -d\' \' -f1)" = '+h(x['new'])+'; then rm '+qtarget+'; fi')
 else:rollbacks.append('if test -f '+qtarget+' && test "$(sha256sum '+qtarget+' | cut -d\' \' -f1)" = '+h(x['new'])+'; then cat '+original+' > '+qtarget+'; fi')
 manifest.append({'path':rel,'old_sha':h(x['old']) if x['old'] is not None else None,'new_sha':h(x['new']),'graphs':x['count']})
for x in changes:
 p=R/x['path'];assert (p.read_bytes() if p.exists() else None)==x['old'],'Concurrent edit before backup complete'
(b/'manifest.json').write_text(json.dumps({'files':manifest,'counts':counts,'card_sha256':h(js.read_bytes()),'resource_was_registered':resource_registered},indent=2))
rollback='#!/bin/sh\nset -eu\n'+'\n'.join(rollbacks)+'\n'
(b/'rollback.sh').write_text(rollback);(b/'rollback.sh').chmod(0o700)
apply='#!/bin/sh\nset -eu\n'+'\n'.join(guards)+'\ntrap '+shlex.quote('sh '+hostroot+'/.jns-backups/'+b.name+'/rollback.sh')+' EXIT\n'+'\n'.join(writes)+'\ntrap - EXIT\necho GRAPH_FILES_APPLIED\n'
(b/'apply.sh').write_text(apply);(b/'apply.sh').chmod(0o700)
# No actual readings in browser samples: rename the series to synthetic entities.
for c in samples:
 for i,e in enumerate(c.get('entities',[])):e['entity']='binary_sensor.sample_'+str(i) if 'state_map' in e else 'sensor.sample_'+str(i);e['name']='Sample '+str(i+1)
(b/'samples.json').write_text(json.dumps(samples));(b/'samples.json').chmod(0o600)
print('GRAPH_STAGE_VERIFIED',json.dumps({'backup':str(b),'graphs':sum(counts.values()),'files':counts,'resource_was_registered':resource_registered,'card_sha256':h(js.read_bytes())}),flush=True)
