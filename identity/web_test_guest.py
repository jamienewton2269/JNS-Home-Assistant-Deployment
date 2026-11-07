#!/usr/bin/python3
"""Exercise upstream HTTP forms with a disposable user. Tokens never printed."""
import pathlib,json,secrets,time,ldap,ssl,urllib.request,urllib.parse,http.cookiejar,html.parser
R=pathlib.Path('/root/identity');D=json.loads((R/'bootstrap.json').read_text());BASE='dc=jnsystems,dc=xyz'
class Form(html.parser.HTMLParser):
 def __init__(self):super().__init__();self.fields={}
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag=='input' and d.get('name'):self.fields[d['name']]=d.get('value','')
def client():return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile='/etc/ldap/identity/ca.crt')),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def fields(body):f=Form();f.feed(body);return f.fields
def root():
 c=ldap.initialize('ldaps://auth-a.home.arpa');c.simple_bind_s('cn=admin,'+BASE,D['admin']);return c
def start():
 uid='identity-recovery-'+secrets.token_hex(4);pw=secrets.token_urlsafe(24);dn='uid='+uid+',ou=People,'+BASE
 c=root();c.add_s(dn,[('objectClass',[b'inetOrgPerson']),('uid',[uid.encode()]),('cn',[b'Recovery acceptance']),('sn',[b'Test']),('mail',[b'jamie@jnsystems.xyz']),('userPassword',[pw.encode()])]);c.unbind_s()
 state={'uid':uid,'dn':dn,'password':pw,'started':time.time()};(R/'web-test.json').write_text(json.dumps(state));(R/'web-test.json').chmod(0o600)
 op=client();url='https://auth-a.home.arpa/password/?action=sendtoken'
 body=op.open(url).read().decode();form=fields(body);assert form.get('formtoken'),'Recovery form token missing'
 form.update(login=uid,action='sendtoken');form.pop('mail',None)
 body=op.open(url,urllib.parse.urlencode(form).encode()).read().decode()
 if 'tokennotsent' in body or 'Error while sending' in body:raise AssertionError('Recovery mail failed')
 print('Recovery form submitted for a disposable user; awaiting private mailbox confirmation')
def finish(url):
 state=json.loads((R/'web-test.json').read_text());new=secrets.token_urlsafe(24);op=client()
 assert urllib.parse.urlsplit(url).hostname=='auth-a.home.arpa'
 body=op.open(url).read().decode();form=fields(body);assert form.get('token'),'Reset link did not open a password form'
 form.update(action='resetbytoken',newpassword=new,confirmpassword=new)
 op.open(url,urllib.parse.urlencode(form).encode()).read()
 for host in ['auth-a','auth-b']:
  for attempt in range(15):
   try:
    c=ldap.initialize('ldaps://'+host+'.home.arpa');c.simple_bind_s(state['dn'],new);c.unbind_s();break
   except ldap.LDAPError:time.sleep(1)
  else:raise AssertionError('Web reset did not update replicated password')
 print('PASS emailed recovery link changed the disposable password on both LDAP servers')
 replay=secrets.token_urlsafe(24);form.update(newpassword=replay,confirmpassword=replay)
 op.open(url,urllib.parse.urlencode(form).encode()).read()
 c=ldap.initialize('ldaps://auth-a.home.arpa');c.simple_bind_s(state['dn'],new);c.unbind_s()
 print('PASS used reset link cannot change the password a second time')
def cleanup():
 if (R/'web-test.json').exists():
  s=json.loads((R/'web-test.json').read_text());c=root()
  try:c.delete_s(s['dn'])
  except ldap.NO_SUCH_OBJECT:pass
  c.unbind_s();(R/'web-test.json').unlink()
