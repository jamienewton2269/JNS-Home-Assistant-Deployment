import pathlib,json,subprocess,websocket,urllib.request
token=None
try:token=pathlib.Path('/etc/jns/credentials/ha-general.token').read_text().strip()
except (OSError,PermissionError):pass
if not token:
 for cmd in [['sudo','-n','cat','/etc/jns/credentials/ha-general.token'],['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','root@localhost','cat /etc/jns/credentials/ha-general.token']]:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=12)
  if r.returncode==0 and len(r.stdout.strip())>64:token=r.stdout.strip();break
print('NODEC_HA_CREDENTIAL_AVAILABLE',bool(token),flush=True)
if not token:raise SystemExit(2)
for base in ['http://ha-general.home.arpa','http://ha-general.home.arpa:8123']:
 try:
  ws=websocket.create_connection(base.replace('http:','ws:')+'/api/websocket',timeout=10,suppress_origin=True)
  hello=json.loads(ws.recv());assert hello.get('type')=='auth_required'
  ws.send(json.dumps({'type':'auth','access_token':token}));assert json.loads(ws.recv()).get('type')=='auth_ok'
  print('CORE_AUTH_OK',base,flush=True)
  for i,t in enumerate(['lovelace/resources','lovelace/dashboards/list'],1):
   ws.send(json.dumps({'id':i,'type':t}));r=json.loads(ws.recv())
   assert r.get('success'),str(r.get('error',{}).get('code'))
   d=r['result']
   if t.endswith('/list'):d=[{k:x.get(k) for k in ('id','url_path','mode','filename')} for x in d]
   print(t,json.dumps(d),flush=True)
  ws.close();break
 except Exception as e:print('CORE_ENDPOINT_ERROR',base,type(e).__name__,flush=True)
else:raise SystemExit(3)
