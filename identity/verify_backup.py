#!/usr/bin/python3
"""Decrypt and restore an export into a separate temporary MDB; live LDAP untouched."""
import pathlib,subprocess,tempfile,json,tarfile,re
R=pathlib.Path('/root/identity');D=json.loads((R/'bootstrap.json').read_text())
subprocess.run(['python3',str(R/'maintenance.py')],check=True)
backup=sorted((R/'backups').glob('*.gpg'))[-1]
with tempfile.TemporaryDirectory(dir=R) as tmp:
 p=pathlib.Path(tmp);(p/'key').write_text(D['backup_key']);(p/'key').chmod(0o600)
 subprocess.run(['gpg','--batch','--yes','--pinentry-mode','loopback','--passphrase-file',str(p/'key'),'--output',str(p/'export.tar.gz'),'--decrypt',str(backup)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 with tarfile.open(p/'export.tar.gz') as t:t.extractall(p/'export',filter='data')
 # A working HTTPS recovery needs the surrounding service configuration too.
 required=[
  'etc/ldap/slapd-identity.conf','etc/ldap/identity/ca.crt',
  'etc/nginx/sites-available/identity','etc/nginx/conf.d/identity-rate.conf',
  'etc/self-service-password/config.inc.local.php',
  'var/lib/ldap-account-manager/config/lam.conf',
  'var/www/identity/index.html',
  'etc/default/slapd',
  'etc/apt/sources.list.d/ltb-project.sources',
  'usr/share/keyrings/ltb-project-debian-keyring.gpg']
 for item in required:
  assert (p/'export'/item).is_file(), 'Missing recovery component: '+item
 assert len(list((p/'export/etc/php').glob('*/fpm/pool.d/www.conf')))==1
 (p/'db').mkdir()
 cfg=(p/'export/etc/ldap/slapd-identity.conf').read_text().replace('directory /var/lib/ldap','directory '+str(p/'db'))
 (p/'restore.conf').write_text(cfg)
 subprocess.run(['slapadd','-f',str(p/'restore.conf'),'-l',str(p/'export/directory.ldif')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 restored=subprocess.check_output(['slapcat','-f',str(p/'restore.conf')],stderr=subprocess.DEVNULL).decode()
 original=(p/'export/directory.ldif').read_text()
 assert sorted(re.findall(r'^uid: (.+)$',restored,re.M))==sorted(re.findall(r'^uid: (.+)$',original,re.M))
 assert 'uid: jamie\n' in restored and 'uid: jamie-admin\n' in restored
 assert json.loads((p/'export/root/identity/bootstrap.json').read_text())['backup_key']==D['backup_key']
print('PASS encrypted directory restored and complete HTTPS recovery configuration present')
