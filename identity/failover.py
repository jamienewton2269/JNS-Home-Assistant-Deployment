#!/usr/bin/env python3
"""Stop only each new slapd instance, test survivor, always restart in finally."""
import subprocess,shlex,base64,secrets,time,sys
def remote(host,args,capture=False):
 r=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@'+host,shlex.join(args)],capture_output=capture,text=True)
 if r.returncode:raise RuntimeError('Failover operation failed on '+host)
 return r.stdout
def py(host,ct,src):
 code='import base64;exec(compile(base64.b64decode('+repr(base64.b64encode(src.encode()).decode())+'),"identity-failover","exec"))'
 return remote(host,['pct','exec',str(ct),'--','python3','-c',code],True)
uid='identity-failover-'+secrets.token_hex(4);pw=secrets.token_urlsafe(24)
prefix='''import ldap,json,pathlib,time
D=json.loads(pathlib.Path('/root/identity/bootstrap.json').read_text());base='dc=jnsystems,dc=xyz'
c=ldap.initialize('ldaps://'+D['name']+'.home.arpa');c.set_option(ldap.OPT_NETWORK_TIMEOUT,5);c.simple_bind_s('cn=admin,'+base,D['admin'])
'''+f"dn='uid={uid},ou=People,'+base\npw={pw!r}\n"
try:
 py('nodea.home.arpa',251,prefix+"c.add_s(dn,[('objectClass',[b'inetOrgPerson']),('uid',["+repr(uid.encode())+"]),('cn',[b'Failover test']),('sn',[b'Test']),('userPassword',[pw.encode()])]);c.unbind_s()")
 time.sleep(7)
 for failed,ct,alive,otherct in [('nodea.home.arpa',251,'nodeb.home.arpa',252),('nodeb.home.arpa',252,'nodea.home.arpa',251)]:
  remote(failed,['pct','exec',str(ct),'--','systemctl','stop','slapd'])
  try:
   result=py(alive,otherct,prefix+"c.simple_bind_s(dn,pw);c.passwd_s(dn,pw,pw+'changed');c.simple_bind_s(dn,pw+'changed');c.unbind_s();print('Survivor login and password change passed')")
   print('PASS',failed,'offline;',result.strip(),flush=True)
  finally:remote(failed,['pct','exec',str(ct),'--','systemctl','start','slapd'])
  time.sleep(10)
  for host,num in [('nodea.home.arpa',251),('nodeb.home.arpa',252)]:
   py(host,num,prefix+"c.simple_bind_s(dn,pw+'changed');c.unbind_s()")
  # Restore the disposable password for the next direction using the current value.
  py(alive,otherct,prefix+"c.passwd_s(dn,None,pw+'next');c.unbind_s()")
  pw+='next';prefix=prefix[:prefix.rfind('pw=')]+f'pw={pw!r}\n';time.sleep(7)
  print('PASS recovered node converged with survivor',flush=True)
finally:
 for host,num in [('nodea.home.arpa',251),('nodeb.home.arpa',252)]:
  remote(host,['pct','exec',str(num),'--','systemctl','start','slapd'])
 py('nodea.home.arpa',251,prefix+"c.delete_s(dn);c.unbind_s()")
print('FAILOVER COMPLETE',flush=True)
