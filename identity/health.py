#!/usr/bin/python3
"""Publish aggregate health only. No passwords, DNs, tokens or user data."""
import ldap,json,pathlib,time,os
D=json.loads(pathlib.Path('/root/identity/bootstrap.json').read_text());B='dc=jnsystems,dc=xyz'
states=[]
for host in ['auth-a.home.arpa','auth-b.home.arpa']:
 try:
  c=ldap.initialize('ldaps://'+host);c.set_option(ldap.OPT_NETWORK_TIMEOUT,3)
  c.simple_bind_s('cn=reader,ou=Services,'+B,D['reader'])
  records=c.search_s(B,ldap.SCOPE_BASE,'(objectClass=*)',['contextCSN'])
  states.append(sorted(x.decode() for x in records[0][1].get('contextCSN',[])));c.unbind_s()
 except ldap.LDAPError:states.append(None)
out={'checked_at':int(time.time()),'online':sum(s is not None for s in states),'synced':bool(states[0]) and states[0]==states[1]}
p=pathlib.Path('/var/www/identity/health.json.tmp');p.write_text(json.dumps(out));p.chmod(0o644);p.replace('/var/www/identity/health.json')
