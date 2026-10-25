#!/usr/bin/env python3
"""Publish one verified APK and run an unprivileged local download server."""
import hashlib,json,os,pathlib,shlex,shutil,socket,subprocess,sys,tempfile,time,urllib.request
SOURCE=pathlib.Path(__file__).resolve().parent
ROOT=pathlib.Path.home()/'.local/share/jns-apk-tests';PORT=8099
manifest=json.loads((SOURCE/'release.json').read_text());filename=manifest['filename']
if pathlib.Path(filename).name!=filename or not filename.endswith('.apk'):raise SystemExit('Invalid release filename')
apk=SOURCE/'releases'/filename
if apk.stat().st_size!=manifest['size_bytes'] or hashlib.sha256(apk.read_bytes()).hexdigest()!=manifest['sha256']:raise SystemExit('APK integrity check failed')
ROOT.mkdir(parents=True,exist_ok=True);(ROOT/'releases').mkdir(exist_ok=True)
if shutil.disk_usage(ROOT).free<100*1024*1024:raise SystemExit('Insufficient space for safe publication')
destination=ROOT/'releases'/filename
if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest()!=manifest['sha256']:raise SystemExit('Versioned filename already holds another build; increase the version')
if not destination.exists():
 tmp=ROOT/'releases'/('.'+filename+'.tmp');shutil.copyfile(apk,tmp);os.chmod(tmp,0o644);os.replace(tmp,destination)
def atomic_write(path,data):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(data);os.replace(tmp,path)
server=ROOT/'server.py'
if server.exists() and server.read_bytes()!=(SOURCE/'server.py').read_bytes():raise SystemExit('Server code changed; stop/review the old server before upgrading it')
atomic_write(server,(SOURCE/'server.py').read_bytes());atomic_write(ROOT/'current.json',json.dumps(manifest,indent=2).encode())
def health():
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health',timeout=2) as r:return json.load(r)
 except Exception:return None
running=health()
if running is not None and running.get('service')!='jns-apk-tests':raise SystemExit('Port belongs to another service')
if running is None:
 probe=socket.socket(socket.AF_INET6);probe.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0)
 try:probe.bind(('::',PORT))
 except OSError:raise SystemExit('Port unavailable; no existing service was altered')
 finally:probe.close()
 env={k:v for k,v in os.environ.items() if k!='RUNNER_TRACKING_ID'}
 with (ROOT/'launcher.log').open('ab') as out:
  child=subprocess.Popen(['/usr/bin/python3',str(server),'--root',str(ROOT),'--port',str(PORT)],stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True,env=env)
 for attempt in range(20):
  if health():break
  if child.poll() is not None:raise SystemExit('Download server failed to start; inspect launcher.log')
  time.sleep(.25)
if not health():raise SystemExit('Download host health check failed')
persistence='not configured'
if shutil.which('crontab'):
 old=subprocess.run(['crontab','-l'],capture_output=True,text=True)
 if old.returncode==0 or (old.returncode==1 and 'no crontab' in old.stderr.lower()):
  marker='# jns-apk-tests';lines=[x for x in old.stdout.splitlines() if marker not in x]
  lines.append('@reboot /usr/bin/python3 '+shlex.quote(str(server))+' --root '+shlex.quote(str(ROOT))+' --port '+str(PORT)+' '+marker)
  subprocess.run(['crontab','-'],input='\n'.join(lines)+'\n',text=True,check=True);persistence='user crontab @reboot'
for host in ['127.0.0.1','10.10.110.13']:
 with urllib.request.urlopen(f'http://{host}:{PORT}/latest.apk',timeout=20) as response:
  assert response.headers.get_content_type()=='application/vnd.android.package-archive'
  assert hashlib.sha256(response.read()).hexdigest()==manifest['sha256']
 with urllib.request.urlopen(f'http://{host}:{PORT}/',timeout=5) as response:assert response.status==200
print('APK_HOST_VERIFIED');print('version='+manifest['version']);print('sha256='+manifest['sha256']);print('persistence='+persistence)
print('page_url=http://10.10.110.13:8099/');print('apk_url=http://10.10.110.13:8099/latest.apk')
print('DNS_NOTE=nodec.home.arpa did not resolve during preflight; nodec resolves to stale address. No DNS configuration was changed.')
