#!/usr/bin/env python3
import subprocess,shlex,base64,pathlib,sys
def remote(host,args):
 r=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@'+host,shlex.join(args)])
 if r.returncode:raise RuntimeError('Identity acceptance stage failed on '+host)
def py(host,ct,source):
 code='import base64;exec(compile(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'),"identity-check","exec"))'
 remote(host,['pct','exec',str(ct),'--','python3','-c',code])
try:
 for host,ct in [('nodea.home.arpa',251),('nodeb.home.arpa',252)]:
  remote(host,['pct','exec',str(ct),'--','bash','-c','hostname; getent ahostsv4 auth-a.home.arpa auth-b.home.arpa; getent ahostsv6 auth-a.home.arpa auth-b.home.arpa; ip -brief address; cat /etc/systemd/network/*.network; free -m; cat /var/www/identity/health.json'])
 py('nodea.home.arpa',251,pathlib.Path('identity/verify_guest.py').read_text())
except Exception as exc:print(type(exc).__name__+': acceptance incomplete',file=sys.stderr);sys.exit(1)
