#!/usr/bin/python3
"""Copy encrypted guest exports to existing WD storage; refuse an unmounted NAS."""
import sys,subprocess,pathlib,re,os
ct=int(sys.argv[1]);name=sys.argv[2]
if (ct,name) not in [(251,'auth-a'),(252,'auth-b')]:sys.exit('Unexpected guest')
def out(args):return subprocess.check_output(args,text=True)
if 'hostname: '+name+'\n' not in out(['pct','config',str(ct)]):sys.exit('Guest identity mismatch')
mount=pathlib.Path('/mnt/pve/WD-BACKUP')
if subprocess.run(['mountpoint','-q',str(mount)]).returncode:sys.exit('WD-BACKUP is not mounted; no local fallback copy was made')
subprocess.run(['pct','exec',str(ct),'--','python3','/root/identity/maintenance.py'],check=True)
dest=mount/'identity'/name;dest.mkdir(parents=True,exist_ok=True);dest.chmod(0o700)
names=out(['pct','exec',str(ct),'--','python3','-c','import pathlib;print("\\n".join(p.name for p in pathlib.Path("/root/identity/backups").glob("*.gpg")))']).splitlines()
for filename in names:
 if not re.fullmatch(r'\d{8}T\d{6}Z\.tar\.gz\.gpg',filename):sys.exit('Unexpected export name')
 subprocess.run(['pct','pull',str(ct),'/root/identity/backups/'+filename,str(dest/filename)],check=True,stdout=subprocess.DEVNULL)
 (dest/filename).chmod(0o600)
for p in sorted(dest.glob('*.gpg'))[:-7]:p.unlink()
print('Encrypted off-host directory exports copied:',name,len(names))
