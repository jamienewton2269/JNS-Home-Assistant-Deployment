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
 (p/'db').mkdir()
 cfg=(p/'export/etc/ldap/slapd-identity.conf').read_text().replace('directory /var/lib/ldap','directory '+str(p/'db'))
 (p/'restore.conf').write_text(cfg)
 subprocess.run(['slapadd','-f',str(p/'restore.conf'),'-l',str(p/'export/directory.ldif')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 restored=subprocess.check_output(['slapcat','-f',str(p/'restore.conf')],stderr=subprocess.DEVNULL).decode()
 original=(p/'export/directory.ldif').read_text()
 assert sorted(re.findall(r'^uid: (.+)$',restored,re.M))==sorted(re.findall(r'^uid: (.+)$',original,re.M))
 assert 'uid: jamie\n' in restored and 'uid: jamie-admin\n' in restored
 assert json.loads((p/'export/root/identity/bootstrap.json').read_text())['backup_key']==D['backup_key']
print('PASS encrypted export decrypted and restored into isolated MDB; both identities preserved')
