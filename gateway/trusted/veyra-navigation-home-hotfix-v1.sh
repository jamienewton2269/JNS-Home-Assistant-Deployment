#!/usr/bin/env bash
set -Eeuo pipefail
if [ "$(id -u)" != "0" ]; then echo 'Run as root via sudo'; exit 2; fi
python3 - <<'PY'
from pathlib import Path
import ast,shutil,time
p=Path('/opt/veyra/veyra/kiosk.py')
j=Path('/opt/veyra/browser-extension/content.js')
b=Path('/opt/veyra/browser-extension/background.js')
for x in [p,j,b]:
 if not x.is_file(): raise SystemExit('Missing '+str(x))
s=p.read_text();js=j.read_text();bg=b.read_text()
old="if url.startswith('https://') and profile.startswith(SETTINGS.browser_profiles_root+'/'):"
key="if(e.ctrlKey&&e.shiftKey&&e.key.toLowerCase()==='h'){e.preventDefault();location.href=HOME;return;}"
esc="if(location.href!==HOME){e.preventDefault();history.back();return;}"
for v,txt in [(old,s),(key,js),(esc,js),('    CONTROL.unlink(missing_ok=True)',s)]:
 if txt.count(v)!=1: raise SystemExit('Unexpected source layout or patch already present: '+v[:60])
backup=Path('/var/backups/veyra-navigation')/time.strftime('%Y%m%d-%H%M%S')
backup.mkdir(parents=True)
for x in [p,j,b]: shutil.copy2(x,backup/x.name)
print('Rollback source backup:',backup)
s=s.replace(old,"if ((url == 'http://127.0.0.1:8766/' and profile == SETTINGS.browser_profile) or (url.startswith('https://') and profile.startswith(SETTINGS.browser_profiles_root+'/'))):",1)
server="""
# veyra-nav-home-v1: loopback-only browser Home command.
def _start_home_server():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != '/home':
                self.send_error(404);return
            if self.headers.get('Origin') not in (None,'','null'):
                self.send_error(403);return
            import json
            tmp=CONTROL.with_name('browser-control.home.tmp')
            tmp.write_text(json.dumps({'url':'http://127.0.0.1:8766/','profile':SETTINGS.browser_profile}))
            tmp.replace(CONTROL)
            self.send_response(204);self.end_headers()
        def log_message(self,*args): pass
    t=ThreadingHTTPServer(('127.0.0.1',8767),Handler)
    threading.Thread(target=t.serve_forever,daemon=True).start()

"""
s=s.replace('def main():',server+'def main():',1)
s=s.replace('    CONTROL.unlink(missing_ok=True)', '    CONTROL.unlink(missing_ok=True)\n    _start_home_server()',1)
ast.parse(s)
js=js.replace(key,"if(e.ctrlKey&&e.shiftKey&&e.key.toLowerCase()==='h'){e.preventDefault();e.stopImmediatePropagation();chrome.runtime.sendMessage({type:'veyra-nav-home-v1'});return;}",1)
js=js.replace(esc,"if(location.href!==HOME){e.preventDefault();e.stopImmediatePropagation();const p=location.pathname.replace(/\\/+$/,'');if(['','/watch','/browse','/home','/gb','/uk'].includes(p)||history.length<=1)chrome.runtime.sendMessage({type:'veyra-nav-home-v1'});else history.back();return;}",1)
bg+="\n// veyra-nav-home-v1\nchrome.runtime.onMessage.addListener((m)=>{if(m&&m.type==='veyra-nav-home-v1')fetch('http://127.0.0.1:8767/home',{method:'POST'}).catch(console.error)});\n"
p.write_text(s);j.write_text(js);b.write_text(bg)
print('Source update complete')
PY
/opt/veyra/.venv/bin/python -m py_compile /opt/veyra/veyra/kiosk.py
if command -v node >/dev/null; then
 node --check /opt/veyra/browser-extension/content.js
 node --check /opt/veyra/browser-extension/background.js
fi
echo 'Restarting kiosk one time to activate; Cage will briefly restart.'
systemctl reset-failed veyra-kiosk.service
systemctl restart --no-block veyra-kiosk.service
sleep 8
systemctl show veyra-kiosk.service -p ActiveState -p Result -p ExecMainStatus -p Restart
curl --max-time 3 -s -o /dev/null -w 'Home API HTTP %{http_code}\n' -X POST http://127.0.0.1:8767/home || true
