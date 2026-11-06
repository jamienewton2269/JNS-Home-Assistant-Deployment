#!/usr/bin/env python3
"""Change one existing local mailbox password without logging it."""
import argparse,getpass,pathlib,subprocess,os,sys,json,tempfile,fcntl,stat
parser=argparse.ArgumentParser()
parser.add_argument("mailbox",choices=["jamie@jnsystems.xyz","jamie@sailing-uk.org"])
args=parser.parse_args()
if os.geteuid()!=0:sys.exit("Run as root inside the mail container.")
if not sys.stdin.isatty():sys.exit("Open an interactive mail-container console first: pct enter 250")
password=getpass.getpass("New password: ")
confirm=getpass.getpass("Repeat new password: ")
if not password:sys.exit("Password was empty; nothing changed.")
if password!=confirm:sys.exit("Passwords did not match; nothing changed.")
if any(c in password for c in "\r\n\0"):sys.exit("Unsupported control character; nothing changed.")
result=subprocess.run(["doveadm","pw","-s","SHA512-CRYPT"],input=password+"\n"+password+"\n",capture_output=True,text=True)
hashed=result.stdout.strip()
if result.returncode or not hashed.startswith("{SHA512-CRYPT}"):sys.exit("Password hashing failed; nothing changed.")
def atomic(path,data,info):
    fd,tmp=tempfile.mkstemp(prefix=".jns-password-",dir=path.parent)
    try:
        os.fchmod(fd,stat.S_IMODE(info.st_mode));os.fchown(fd,info.st_uid,info.st_gid)
        with os.fdopen(fd,"wb") as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
with open("/run/jns-mail-password.lock","w") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    users=pathlib.Path("/etc/dovecot/jns-users")
    original=users.read_bytes();info=users.stat()
    lines=original.decode().splitlines()
    matches=[i for i,line in enumerate(lines) if line.split(":",1)[0]==args.mailbox]
    if len(matches)!=1:sys.exit("Expected exactly one existing mailbox entry; nothing changed.")
    fields=lines[matches[0]].split(":");fields[1]=hashed
    lines[matches[0]]=":".join(fields)
    creds=pathlib.Path("/root/jns-mail/credentials.json")
    oldcreds=creds.read_bytes() if creds.exists() else None
    if oldcreds is not None:
        saved=json.loads(oldcreds)
        if args.mailbox not in saved:sys.exit("Saved credential record is inconsistent; nothing changed.")
        saved[args.mailbox]=password
        credinfo=creds.stat()
    atomic(users,("\n".join(lines)+"\n").encode(),info)
    try:
        if oldcreds is not None:atomic(creds,(json.dumps(saved,indent=2)+"\n").encode(),credinfo)
    except BaseException:
        atomic(users,original,info)
        raise
subprocess.run(["doveadm","auth","cache","flush",args.mailbox],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print("Password changed for "+args.mailbox+". Use it for both IMAP and SMTP login.")
print("The aliases use this mailbox; they do not have separate passwords.")
