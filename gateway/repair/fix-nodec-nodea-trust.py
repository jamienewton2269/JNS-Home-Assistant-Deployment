#!/usr/bin/env python3
"""Safe, attested SSH name repair for the JNS Node C runner."""
from pathlib import Path
import subprocess,shutil,datetime,os
def command(*args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=15,check=True)
    return p.stdout.strip()
root=Path.home()/'.ssh'
config=root/'config'
known=root/'known_hosts'
# Key fingerprint established independently through Node B:
# SHA256:XolW5ZavMlI1TkrqfUuz0bwKKljeGyw0fiW7y8Sgb2I
attested=command('ssh','-o','BatchMode=yes','nodeb',
    'ssh -o BatchMode=yes root@nodea.home.arpa cat /etc/ssh/ssh_host_ed25519_key.pub').split()
if len(attested)<2 or attested[0]!='ssh-ed25519':
    raise RuntimeError('Could not obtain verified public host key')
scan=command('ssh-keyscan','-T','5','-t','ed25519','nodea.home.arpa')
if not any(line.split()[1:3]==attested[:2] for line in scan.splitlines() if line and not line.startswith('#')):
    raise RuntimeError('Host identity mismatch; no SSH changes permitted')
if command('ssh','-o','BatchMode=yes','nodeb','hostname -s')!='nodeb':
    raise RuntimeError('Node B authentication mismatch')
text=config.read_text()
if '\nHost nodea\n' in '\n'+text:
    raise RuntimeError('Node A alias already present; refusing to override')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
cfgbackup=root/('config.backup-'+stamp)
khbackup=root/('known_hosts.backup-'+stamp)
shutil.copy2(config,cfgbackup)
if known.exists():shutil.copy2(known,khbackup)
try:
    existing=known.read_text() if known.exists() else ''
    if not any('nodea.home.arpa' in line and attested[1] in line for line in existing.splitlines()):
        with known.open('a') as f:f.write('nodea.home.arpa '+attested[0]+' '+attested[1]+'\n')
    with config.open('a') as f:
        f.write('\nHost nodea\n    HostName nodea.home.arpa\n    User root\n    BatchMode yes\n    StrictHostKeyChecking yes\n')
    os.chmod(config,0o600)
    for host,vm in [('nodea','900'),('nodeb','905')]:
        result=command('ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',host,'hostname -s; qm status '+vm)
        if host not in result: raise RuntimeError(host+' identification failed')
        print('VERIFIED',host,result,flush=True)
except Exception:
    shutil.copy2(cfgbackup,config)
    if khbackup.exists():shutil.copy2(khbackup,known)
    raise
print('NODEC_SSH_BOTH_NODES_OK')
