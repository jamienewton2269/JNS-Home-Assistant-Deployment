#!/usr/bin/env python3
"""LAN-only APK download host; serves only its own release files and metadata."""
import argparse,fcntl,hashlib,html,http.server,ipaddress,json,logging,logging.handlers,os,pathlib,re,socket
parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--port',type=int,default=8099);args=parser.parse_args()
ROOT=pathlib.Path(args.root).resolve();ROOT.mkdir(parents=True,exist_ok=True)
lock=(ROOT/'server.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
log=logging.getLogger('apk-tests');log.setLevel(logging.INFO);log.addHandler(logging.handlers.RotatingFileHandler(ROOT/'server.log',maxBytes=1048576,backupCount=1))
class Handler(http.server.BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,fmt,*values):log.info('%s %s',self.address_string(),fmt%values)
 def allowed(self):
  try:
   ip=ipaddress.ip_address(self.client_address[0]);ip=ip.ipv4_mapped if isinstance(ip,ipaddress.IPv6Address) and ip.ipv4_mapped else ip
   return ip.is_private or ip.is_loopback or ip.is_link_local
  except ValueError:return False
 def send_data(self,data,mime,status=200,head=False):
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store, max-age=0');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
  if not head:self.wfile.write(data)
 def do_HEAD(self):self.serve(True)
 def do_GET(self):self.serve(False)
 def serve(self,head=False):
  if not self.allowed():self.send_data(b'LAN access only','text/plain',403,head);return
  route=self.path.split('?',1)[0]
  try:manifest=json.loads((ROOT/'current.json').read_text())
  except (OSError,ValueError):self.send_data(b'No release published','text/plain',503,head);return
  if route=='/health':self.send_data(json.dumps({'service':'jns-apk-tests','version':manifest['version'],'sha256':manifest['sha256']}).encode(),'application/json',head=head);return
  if route=='/manifest.json':self.send_data(json.dumps(manifest,indent=2).encode(),'application/json',head=head);return
  if route=='/':
   name=html.escape(manifest['filename']);version=html.escape(manifest['version']);digest=html.escape(manifest['sha256']);size=manifest['size_bytes']/1024/1024
   page=f'''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chicken Tracker · Android tests</title><style>body{{background:#07150f;color:#d9eedf;font:16px system-ui;max-width:640px;margin:8vh auto;padding:24px}}small{{color:#84aa92}}h1{{font-weight:600}}a{{display:inline-block;background:#95e8b0;color:#0c2515;padding:18px 25px;border-radius:10px;font-weight:700;text-decoration:none}}code{{font-size:11px;overflow-wrap:anywhere}}p{{line-height:1.65}}.details{{border-top:1px solid #254c32;margin-top:32px;padding-top:18px}}</style><small>JNS / LOCAL ANDROID TEST BUILDS</small><h1>Chicken Tracker</h1><p>Motion tracker. Simulated pings. One very large visitor.</p><p><a href="/latest.apk" download="{name}">Download latest APK ↓</a></p><p>Version {version} · {size:.1f} MB · Android 8+</p><p>Open the download to install or update. Allow Camera, then tap <b>Activate tracker</b>. Keep this page bookmarked for the next test build.</p><p>The detector and sounds are bundled for offline use. This is a signed test build.</p><div class="details"><small>SHA-256</small><p><code>{digest}</code></p></div></html>'''
   self.send_data(page.encode(),'text/html; charset=utf-8',head=head);return
  filename=manifest['filename'] if route=='/latest.apk' else route[len('/releases/'):] if route.startswith('/releases/') else ''
  if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*\.apk',filename):self.send_data(b'Not found','text/plain',404,head);return
  file=ROOT/'releases'/filename
  if not file.is_file() or file.is_symlink():self.send_data(b'Not found','text/plain',404,head);return
  length=file.stat().st_size;start,end=0,length-1;status=200
  if self.headers.get('Range'):
   m=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
   if not m:self.send_data(b'Unsupported range','text/plain',416,head);return
   start=int(m[1]);end=min(length-1,int(m[2]) if m[2] else length-1);status=206
   if start>end or start>=length:self.send_data(b'Invalid range','text/plain',416,head);return
  self.send_response(status);self.send_header('Content-Type','application/vnd.android.package-archive');self.send_header('Content-Disposition',f'attachment; filename="{filename}"');self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store, max-age=0');self.send_header('X-Content-Type-Options','nosniff')
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{length}')
  self.end_headers()
  if not head:
   with file.open('rb') as f:
    f.seek(start);remaining=end-start+1
    while remaining:
     block=f.read(min(65536,remaining))
     if not block:break
     self.wfile.write(block);remaining-=len(block)
class Server(http.server.ThreadingHTTPServer):
 address_family=socket.AF_INET6
 daemon_threads=True
 def server_bind(self):self.socket.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0);super().server_bind()
server=Server(('::',args.port),Handler)
log.info('jns-apk-tests started port=%d root=%s',args.port,ROOT)
server.serve_forever()
