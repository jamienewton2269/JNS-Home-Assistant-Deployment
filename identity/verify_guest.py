#!/usr/bin/python3
"""Acceptance tests use a disposable account; never print credentials or tokens."""
import ldap,json,pathlib,secrets,time,ssl,urllib.request,urllib.error
D=json.loads(pathlib.Path('/root/identity/bootstrap.json').read_text());BASE='dc=jnsystems,dc=xyz';PEOPLE='ou=People,'+BASE
def connect(host,who,password):
 c=ldap.initialize('ldaps://'+host+'.home.arpa');c.set_option(ldap.OPT_NETWORK_TIMEOUT,4);c.simple_bind_s(who,password);return c
def root(host):return connect(host,'cn=admin,'+BASE,D['admin'])
def check(name,condition):
 if not condition:raise AssertionError(name)
 print('PASS',name,flush=True)
def wait_auth(host,dn,password):
 for i in range(30):
  try:c=connect(host,dn,password);c.unbind_s();return
  except ldap.LDAPError:time.sleep(1)
 raise AssertionError('Replicated authentication failed: '+host)
if __name__=='__main__':
 for host in ['auth-a','auth-b']:
  wait_auth(host,'uid=jamie,'+PEOPLE,D['jamie'])
  c=connect(host,'cn=reader,ou=Services,'+BASE,D['reader'])
  r=c.search_s(PEOPLE,ldap.SCOPE_SUBTREE,'(uid=jamie)',['userPassword','uid'])
  check(host+' reader cannot retrieve password hashes','userPassword' not in r[0][1]);c.unbind_s()
  # Reset service must not alter the administrator or its own service credentials.
  c=connect(host,'cn=password-reset,ou=Services,'+BASE,D['reset'])
  for dn in ['uid=jamie-admin,'+PEOPLE,'cn=reader,ou=Services,'+BASE]:
   original=root(host).search_s(dn,ldap.SCOPE_BASE,'(objectClass=*)',['userPassword'])[0][1]['userPassword']
   denied=False
   try:c.modify_s(dn,[(ldap.MOD_REPLACE,'userPassword',original)])
   except ldap.INSUFFICIENT_ACCESS:denied=True
   check(host+' recovery cannot modify privileged credentials '+dn.split(',')[0],denied)
  c.unbind_s()
  context=ssl.create_default_context(cafile='/etc/ldap/identity/ca.crt')
  for path,needle in [('/','Your account, made simple'),('/admin/','LDAP'),('/password/?action=change','password'),('/password/?action=sendtoken','password')]:
   with urllib.request.urlopen('https://'+host+'.home.arpa'+path,context=context,timeout=15) as r:
    content=r.read().decode(errors='replace');check(host+' web '+path,r.status==200 and needle.lower() in content.lower() and 'Fatal error' not in content)
  for path in ['/admin/config/lam.conf','/admin/templates/config/mainlogin.php','/password/conf/config.inc.local.php']:
   try:urllib.request.urlopen('https://'+host+'.home.arpa'+path,context=context,timeout=10);blocked=False
   except urllib.error.HTTPError as e:blocked=e.code in [403,404]
   check(host+' blocks private/configuration web path '+path,blocked)
 uid='identity-check-'+secrets.token_hex(4);dn='uid='+uid+','+PEOPLE;p1=secrets.token_urlsafe(24);p2=secrets.token_urlsafe(24)
 c=root('auth-a')
 try:
  c.add_s(dn,[('objectClass',[b'inetOrgPerson']),('uid',[uid.encode()]),('cn',[b'Identity acceptance']),('sn',[b'Acceptance']),('mail',[b'identity-check@example.invalid']),('userPassword',[p1.encode()])])
  wait_auth('auth-b',dn,p1);check('new account replicates A to B',True)
  user=connect('auth-a',dn,p1);user.passwd_s(dn,p1,p2);user.unbind_s();wait_auth('auth-b',dn,p2)
  check('user password change replicates A to B',True)
  user=connect('auth-a',dn,p2);weak=False
  try:user.passwd_s(dn,p2,'short')
  except ldap.LDAPError:weak=True
  user.unbind_s();check('server enforces minimum password length',weak)
  r=connect('auth-b','cn=password-reset,ou=Services,'+BASE,D['reset']);r.passwd_s(dn,None,p1+'new');r.unbind_s();wait_auth('auth-a',dn,p1+'new')
  check('delegated ordinary-user reset replicates B to A',True)
 finally:
  try:c.delete_s(dn)
  except ldap.NO_SUCH_OBJECT:pass
  c.unbind_s()
 print('ACCEPTANCE COMPLETE',flush=True)
