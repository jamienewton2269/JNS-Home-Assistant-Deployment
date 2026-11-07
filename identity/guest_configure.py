#!/usr/bin/env python3
import pathlib,json,subprocess,os,shutil,hashlib,base64,glob
os.umask(0o077)
D=json.loads(pathlib.Path('/root/identity/bootstrap.json').read_text())
BASE='dc=jnsystems,dc=xyz'; PEOPLE='ou=People,'+BASE
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def write(path,data,mode=0o644,owner=None):
 p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data);p.chmod(mode)
 if owner:shutil.chown(p,user=owner,group=owner)
def hashed(password):
 salt=os.urandom(16);return '{SSHA}'+base64.b64encode(hashlib.sha1(password.encode()+salt).digest()+salt).decode()
name,peer,sid=D['name'],D['peer'],D['sid']
pathlib.Path('/etc/ldap/identity').mkdir(parents=True,exist_ok=True)
os.chmod('/etc/ldap/identity',0o755)
write('/etc/ldap/identity/ca.crt',D['ca'])
write('/usr/local/share/ca-certificates/identity.crt',D['ca'])
write('/etc/ldap/identity/server.crt',D['certificate'])
write('/etc/ldap/identity/server.key',D['private_key'],0o640,'openldap')
run(['update-ca-certificates'])
write('/etc/ldap/ldap.conf','BASE '+BASE+'\nURI ldaps://'+name+'.home.arpa\nTLS_CACERT /etc/ldap/identity/ca.crt\nTLS_REQCERT demand\n')
admin_dn='uid=jamie-admin,'+PEOPLE
reset_dn='cn=password-reset,ou=Services,'+BASE
replica_dn='cn=replicator,ou=Services,'+BASE
reader_dn='cn=reader,ou=Services,'+BASE
cfg=f'''include /etc/ldap/schema/core.schema
include /etc/ldap/schema/cosine.schema
include /etc/ldap/schema/nis.schema
include /etc/ldap/schema/inetorgperson.schema
pidfile /run/slapd/slapd.pid
argsfile /run/slapd/slapd.args
modulepath /usr/lib/ldap
moduleload back_mdb
moduleload syncprov
moduleload ppolicy
serverID {sid}
TLSCACertificateFile /etc/ldap/identity/ca.crt
TLSCertificateFile /etc/ldap/identity/server.crt
TLSCertificateKeyFile /etc/ldap/identity/server.key
security simple_bind=128
loglevel stats sync
database mdb
maxsize 268435456
suffix "{BASE}"
rootdn "cn=admin,{BASE}"
rootpw {hashed(D['admin'])}
directory /var/lib/ldap
index objectClass eq
index uid,cn,mail,memberUid eq
index entryUUID eq
index entryCSN eq
access to dn.subtree="{PEOPLE}" filter=(!(uid=jamie-admin)) attrs=userPassword
 by dn.exact="{replica_dn}" read
 by dn.exact="{admin_dn}" write
 by dn.exact="{reset_dn}" write
 by self write
 by anonymous auth
 by * none
access to attrs=userPassword
 by dn.exact="{replica_dn}" read
 by dn.exact="{admin_dn}" write
 by self write
 by anonymous auth
 by * none
access to dn.subtree="ou=Services,{BASE}"
 by dn.exact="{replica_dn}" read
 by dn.exact="{admin_dn}" read
 by * none
access to *
 by dn.exact="{admin_dn}" write
 by dn.exact="{replica_dn}" read
 by dn.exact="{reader_dn}" read
 by dn.exact="{reset_dn}" read
 by users read
 by * none
syncrepl rid=00{sid}
 provider=ldaps://{peer}.home.arpa
 bindmethod=simple
 binddn="{replica_dn}"
 credentials="{D['replicator']}"
 searchbase="{BASE}"
 type=refreshAndPersist
 retry="5 5 30 +"
 timeout=5
 tls_reqcert=demand
 tls_cacert=/etc/ldap/identity/ca.crt
mirrormode TRUE
overlay syncprov
syncprov-checkpoint 20 5
syncprov-sessionlog 100
overlay ppolicy
ppolicy_default "cn=default,ou=Policies,{BASE}"
ppolicy_hash_cleartext
'''
write('/etc/ldap/slapd-identity.conf',cfg,0o640,'openldap')
write('/etc/default/slapd','SLAPD_CONF=/etc/ldap/slapd-identity.conf\nSLAPD_USER=openldap\nSLAPD_GROUP=openldap\nSLAPD_PIDFILE=/run/slapd/slapd.pid\nSLAPD_SERVICES="ldaps:/// ldapi:///"\nSLAPD_SENTINEL_FILE=/etc/ldap/noslapd\nSLAPD_OPTIONS=""\n')
run(['systemctl','stop','slapd'])
pathlib.Path('/var/lib/ldap').mkdir(exist_ok=True);shutil.chown('/var/lib/ldap','openldap','openldap')
run(['slaptest','-f','/etc/ldap/slapd-identity.conf','-u'])
if not pathlib.Path('/var/lib/ldap/data.mdb').exists() and sid==1:
 entries=[f'dn: {BASE}\nobjectClass: dcObject\nobjectClass: organization\no: JNSystems\ndc: jnsystems']
 for ou in ['People','Groups','Services','Policies']:
  entries.append(f'dn: ou={ou},{BASE}\nobjectClass: organizationalUnit\nou: {ou}')
 for cn,key in [('replicator','replicator'),('password-reset','reset'),('reader','reader')]:
  entries.append(f'dn: cn={cn},ou=Services,{BASE}\nobjectClass: organizationalRole\nobjectClass: simpleSecurityObject\ncn: {cn}\nuserPassword: {hashed(D[key])}')
 for uid,number in [('jamie',10000),('jamie-admin',10001)]:
  entries.append(f'dn: uid={uid},{PEOPLE}\nobjectClass: inetOrgPerson\nobjectClass: posixAccount\nuid: {uid}\ncn: Jamie Newton'+(' Administrator' if uid.endswith('admin') else '')+f'\nsn: Newton\nuidNumber: {number}\ngidNumber: 10000\nhomeDirectory: /home/{uid}\nloginShell: /bin/bash\nmail: '+('jamie@blundellsandssailingclub.co.uk' if uid=='jamie' else 'mailadmin@jnsystems.xyz')+f'\nuserPassword: {hashed(D[uid])}')
 for i,group in enumerate(['identity-admins','mail-users','proxmox-admins','linux-admins']):
  entries.append(f'dn: cn={group},ou=Groups,{BASE}\nobjectClass: posixGroup\ncn: {group}\ngidNumber: {10000+i}\nmemberUid: '+('jamie-admin' if group=='identity-admins' else 'jamie'))
 entries.append(f'dn: cn=default,ou=Policies,{BASE}\nobjectClass: organizationalRole\nobjectClass: pwdPolicy\ncn: default\npwdAttribute: userPassword\npwdMinLength: 14\npwdCheckQuality: 1\npwdInHistory: 5\npwdLockout: TRUE\npwdMaxFailure: 10\npwdFailureCountInterval: 300\npwdLockoutDuration: 300\npwdAllowUserChange: TRUE\npwdSafeModify: FALSE')
 run(['slapadd','-f','/etc/ldap/slapd-identity.conf'],input=('\n\n'.join(entries)+'\n').encode())
 for p in pathlib.Path('/var/lib/ldap').iterdir():shutil.chown(p,'openldap','openldap')
run(['systemctl','enable','--now','slapd'])

# Package-provided LAM, restricted to the named directory administrator.
lam=pathlib.Path('/etc/ldap-account-manager/lam.conf')
if not lam.exists():
 samples=list(pathlib.Path('/usr/share/ldap-account-manager').rglob('lam.conf.sample'))
 if samples:shutil.copy2(samples[0],lam)
text=lam.read_text() if lam.exists() else ''
def setting(key,value):
 global text
 import re
 line=key+': '+value
 if re.search(r'^'+re.escape(key)+r':.*$',text,re.M):text=re.sub(r'^'+re.escape(key)+r':.*$',lambda m:line,text,flags=re.M)
 else:text+='\n'+line+'\n'
for k,v in {'ServerURL':'ldaps://'+name+'.home.arpa','useTLS':'no','treesuffix':BASE,'Admins':admin_dn,'defaultLanguage':'en_GB.utf8','Passwd':hashlib.sha256(D['lam-config'].encode()).hexdigest(),'types: active':'user,group','types: suffix_user':PEOPLE,'types: suffix_group':'ou=Groups,'+BASE,'modules: user':'inetOrgPerson,posixAccount','modules: group':'posixGroup','loginMethod':'list','hideLAMLogo':'true'}.items():setting(k,v)
write(str(lam),text,0o640,'www-data')

# Package-provided password recovery, with a narrowly scoped LDAP account.
def php(v):return json.dumps(v)
ssp={
 'ldap_url':'ldaps://'+name+'.home.arpa','ldap_binddn':reset_dn,'ldap_bindpw':D['reset'],
 'ldap_base':PEOPLE,'ldap_login_attribute':'uid','ldap_filter':'(&(objectClass=inetOrgPerson)(uid={login})(!(uid=jamie-admin)))',
 'ldap_use_exop_passwd':True,'ldap_use_ppolicy_control':True,'who_change_password':'user',
 'hash':'SSHA','pwd_min_length':14,'pwd_max_length':128,'pwd_min_upper':0,'pwd_min_lower':0,'pwd_min_digit':0,'pwd_min_special':0,
 'use_questions':False,'use_sms':False,'use_tokens':True,'crypt_tokens':True,'keyphrase':D['keyphrase'],'token_lifetime':900,
 'mail_address_use_ldap':True,'notify_on_change':True,'mail_protocol':'smtp','mail_smtp_host':'mail-eu.smtp2go.com','mail_smtp_port':587,
 'mail_smtp_auth':True,'mail_smtp_user':D['smtp_user'],'mail_smtp_pass':D['smtp_password'],'mail_smtp_secure':'tls',
 'mail_from':'mailadmin@jnsystems.xyz','mail_from_name':'JNSystems Account Services','mail_smtp_debug':0,
 'reset_url':'https://'+name+'.home.arpa/password/index.php','reset_request_log':'/dev/null',
 'show_menu':True,'use_recaptcha':False,'debug':False,'lang':'en','logo':'',
}
write('/etc/self-service-password/config.inc.local.php','<?php\n'+''.join('$'+k+' = '+php(v)+';\n' for k,v in ssp.items()),0o640,'www-data')
# Minimal web footprint: nginx and an on-demand PHP pool, no Apache or database service.
for service in ['apache2','mariadb']:
 subprocess.run(['systemctl','disable','--now',service],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
versions=glob.glob('/etc/php/*/fpm/pool.d/www.conf');assert len(versions)==1
pool=pathlib.Path(versions[0]);s=pool.read_text()
import re
for key,value in [('pm','ondemand'),('pm.max_children','3'),('pm.process_idle_timeout','15s'),('php_admin_flag[log_errors]','on')]:
 pattern=r'^;?'+re.escape(key)+r'\s*=.*$'
 if re.search(pattern,s,re.M):s=re.sub(pattern,lambda m:key+' = '+value,s,flags=re.M)
 else:s+='\n'+key+' = '+value+'\n'
s+='\nphp_admin_flag[session.cookie_secure] = on\nphp_admin_flag[session.cookie_httponly] = on\nphp_admin_value[session.cookie_samesite] = Lax\nphp_admin_value[session.use_strict_mode] = 1\n'
pool.write_text(s)
socket=glob.glob('/run/php/php*-fpm.sock')[0]
ssp_root='/usr/share/self-service-password/htdocs'
if not pathlib.Path(ssp_root).is_dir():ssp_root='/usr/share/self-service-password'
lam_root='/usr/share/ldap-account-manager'
write('/etc/nginx/conf.d/identity-rate.conf','limit_req_zone $binary_remote_addr zone=identity:1m rate=10r/m;\n')
write('/etc/nginx/sites-available/identity',f'''server {{
 listen 80 default_server; listen [::]:80 default_server;
 server_name {name}.home.arpa;
 location = /identity-ca.crt {{ root /var/www/identity; }}
 location / {{ return 308 https://{name}.home.arpa$request_uri; }}
}}
server {{
 listen 443 ssl default_server; listen [::]:443 ssl default_server;
 server_name {name}.home.arpa;
 ssl_certificate /etc/ldap/identity/server.crt;
 ssl_certificate_key /etc/ldap/identity/server.key;
 ssl_protocols TLSv1.2 TLSv1.3;
 root /var/www/identity; index index.html;
 add_header X-Content-Type-Options nosniff always;
 add_header Referrer-Policy no-referrer always;
 add_header X-Frame-Options SAMEORIGIN always;
 client_max_body_size 1m;
 location / {{ try_files $uri $uri/ =404; }}
 location /admin/ {{ alias {lam_root}/; index index.html index.php;
   location ~ ^/admin/(config|sess|tmp|locale|lib)/ {{ deny all; }}
   location ~ ^/admin/(.+\\.php)$ {{
     limit_req zone=identity burst=15 nodelay;
     include fastcgi_params; fastcgi_param SCRIPT_FILENAME {lam_root}/$1;
     fastcgi_param HTTPS on; fastcgi_pass unix:{socket};
   }}
 }}
 location /password/ {{ alias {ssp_root}/; index index.php;
   access_log off;
   location ~ ^/password/(conf|vendor|cache|templates|templates_c)/ {{ deny all; }}
   location ~ ^/password/(.+\\.php)$ {{
     limit_req zone=identity burst=5 nodelay;
     include fastcgi_params; fastcgi_param SCRIPT_FILENAME {ssp_root}/$1;
     fastcgi_param HTTPS on; fastcgi_pass unix:{socket};
   }}
 }}
 location ~ /\\. {{ deny all; }}
}}
''')
pathlib.Path('/etc/nginx/sites-enabled/default').unlink(missing_ok=True)
link=pathlib.Path('/etc/nginx/sites-enabled/identity');link.unlink(missing_ok=True);link.symlink_to('/etc/nginx/sites-available/identity')
shutil.copy2('/etc/ldap/identity/ca.crt','/var/www/identity/identity-ca.crt');os.chmod('/var/www/identity/identity-ca.crt',0o644)
run(['nginx','-t']);run(['systemctl','restart','php'+pool.parts[3]+'-fpm','nginx'])
print('Identity services configured',name)
