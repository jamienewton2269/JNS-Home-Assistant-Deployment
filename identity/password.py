#!/usr/bin/python3
"""Local emergency/bootstrap password change. Never takes passwords as arguments."""
import os,sys,re,getpass,json,pathlib,ldap
if os.geteuid()!=0:sys.exit('Run as root inside auth-a or auth-b.')
if len(sys.argv)!=2 or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',sys.argv[1]):sys.exit('Usage: identity-password USERNAME')
p=getpass.getpass('New directory password (at least 14 characters): ')
if len(p)<14 or len(p)>128:sys.exit('Use between 14 and 128 characters.')
if p!=getpass.getpass('Repeat new directory password: '):sys.exit('Passwords did not match.')
D=json.loads(pathlib.Path('/root/identity/bootstrap.json').read_text());base='dc=jnsystems,dc=xyz'
try:
 c=ldap.initialize('ldaps://'+D['name']+'.home.arpa');c.set_option(ldap.OPT_NETWORK_TIMEOUT,5)
 c.simple_bind_s('cn=admin,'+base,D['admin'])
 c.passwd_s('uid='+sys.argv[1]+',ou=People,'+base,None,p);c.unbind_s()
except ldap.LDAPError:sys.exit('Directory rejected the change; check the username and password policy.')
print('Directory password changed. The change will replicate to the other server.')
