#!/usr/bin/python3
"""Local certificate renewal and encrypted directory export; no network services."""
import pathlib,json,subprocess,datetime,secrets,os,tarfile,tempfile
os.umask(0o077)
R=pathlib.Path('/root/identity');D=json.loads((R/'bootstrap.json').read_text())
def run(args,**kw):return subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kw)
cert='/etc/ldap/identity/server.crt'
if subprocess.run(['openssl','x509','-checkend','2592000','-noout','-in',cert],stdout=subprocess.DEVNULL).returncode:
 with tempfile.TemporaryDirectory(dir=R) as tmp:
  p=pathlib.Path(tmp);(p/'ca.key').write_text(D['ca_private_key']);(p/'ext').write_text('subjectAltName=DNS:'+D['name']+'.home.arpa\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n')
  run(['openssl','req','-new','-key','/etc/ldap/identity/server.key','-out',str(p/'server.csr'),'-subj','/CN='+D['name']+'.home.arpa'])
  run(['openssl','x509','-req','-in',str(p/'server.csr'),'-CA','/etc/ldap/identity/ca.crt','-CAkey',str(p/'ca.key'),'-set_serial',str(secrets.randbits(150)),'-days','365','-extfile',str(p/'ext'),'-out',str(p/'server.crt')])
  pathlib.Path(cert).write_bytes((p/'server.crt').read_bytes());os.chmod(cert,0o644)
  run(['systemctl','restart','slapd']);run(['systemctl','reload','nginx'])
backup=R/'backups';backup.mkdir(mode=0o700,exist_ok=True)
with tempfile.TemporaryDirectory(dir=R) as tmp:
 p=pathlib.Path(tmp);(p/'backup.key').write_text(D['backup_key'])
 with (p/'directory.ldif').open('wb') as f:subprocess.run(['slapcat','-f','/etc/ldap/slapd-identity.conf'],stdout=f,stderr=subprocess.DEVNULL,check=True)
 with tarfile.open(p/'export.tar.gz','w:gz',dereference=True) as t:
  t.add(p/'directory.ldif',arcname='directory.ldif')
  # Complete operational configuration: not just the directory data.
  # In particular nginx depends on identity-rate.conf and the site assets.
  required=[
   '/etc/ldap/slapd-identity.conf','/etc/ldap/identity','/etc/ldap/ldap.conf',
   '/etc/default/slapd','/var/lib/ldap-account-manager/config',
   '/etc/self-service-password','/etc/nginx/sites-available/identity',
   '/etc/nginx/conf.d/identity-rate.conf','/var/www/identity',
   '/root/identity/bootstrap.json','/usr/local/sbin/identity-password',
   '/etc/apt/sources.list.d/ltb-project.sources',
   '/usr/share/keyrings/ltb-project-debian-keyring.gpg',
   '/etc/systemd/system/identity-health.service',
   '/etc/systemd/system/identity-health.timer',
   '/etc/systemd/system/identity-maintenance.service',
   '/etc/systemd/system/identity-maintenance.timer']
  php_pools=list(pathlib.Path('/etc/php').glob('*/fpm/pool.d/www.conf'))
  if len(php_pools)!=1:raise RuntimeError('Expected exactly one PHP-FPM pool')
  for source in required+[str(php_pools[0])]:
   if not pathlib.Path(source).exists():raise FileNotFoundError(source)
   t.add(source,arcname=source.lstrip('/'))
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 run(['gpg','--batch','--yes','--pinentry-mode','loopback','--passphrase-file',str(p/'backup.key'),'--symmetric','--cipher-algo','AES256','--compress-algo','none','--output',str(backup/(stamp+'.tar.gz.gpg')),str(p/'export.tar.gz')])
for old in sorted(backup.glob('*.gpg'))[:-7]:old.unlink()
print('Identity certificate checked; encrypted export created.')
