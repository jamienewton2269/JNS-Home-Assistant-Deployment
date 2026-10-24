#!/usr/bin/env python3
"""Repair only old Node C runner Host nodeb alias, with backup and verification.

No SSH keys, known_hosts, server configuration or authentication are altered.
"""
from pathlib import Path
import datetime, os, re, subprocess

cfg=Path.home()/".ssh"/"config"
print("JNS_SSH_REPAIR_START",flush=True)
if not cfg.is_file(): raise SystemExit("BLOCKED: runner SSH config absent")
def verify(command):
    p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=14)
    if p.returncode: raise RuntimeError("SSH check failed "+p.stderr[:250])
    return p.stdout.strip()
ident=verify(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
              "root@nodeb.home.arpa","hostname -s"])
if ident!="nodeb":raise SystemExit("BLOCKED: DNS endpoint does not identify as nodeb")
before=cfg.read_text()
lines=before.splitlines(keepends=True)
starts=[i for i,l in enumerate(lines) if re.match(r"^\s*Host\s+nodeb\s*(?:#.*)?$",l,re.I)]
if len(starts)!=1:raise SystemExit("BLOCKED: Host nodeb stanza missing or ambiguous")
start=starts[0]
end=next((j for j in range(start+1,len(lines)) if re.match(r"^\s*(Host|Match)\s+",lines[j],re.I)),len(lines))
stanza=lines[start+1:end]
hits=[j for j,line in enumerate(stanza) if re.match(r"^\s*HostName\s+",line,re.I)]
if len(hits)!=1:raise SystemExit("BLOCKED: expected exactly one HostName directive")
idx=hits[0]
m=re.match(r"^(\s*HostName\s+)(\S+)(.*?)(\r?\n?)$",stanza[idx],re.I)
if not m:raise SystemExit("BLOCKED: malformed HostName directive")
old=m.group(2)
if old not in ("10.10.10.235","nodeb.home.arpa"):
    raise SystemExit("BLOCKED: unexpected HostName value; refusing to override")
if old=="nodeb.home.arpa":
    print("JNS_SSH_ALREADY_CORRECT",flush=True)
else:
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=cfg.with_name("config.jns-nodeb-before-"+stamp)
    with backup.open("x") as b:
        b.write(before)
    os.chmod(backup,0o600)
    stanza[idx]=m.group(1)+"nodeb.home.arpa"+m.group(3)+m.group(4)
    lines[start+1:end]=stanza
    changed="".join(lines)
    staged=cfg.with_name("config.jns-nodeb-stage")
    with staged.open("x") as t:
        t.write(changed)
    os.chmod(staged,0o600)
    try:
        os.replace(staged,cfg)
        os.chmod(cfg,0o600)
        result=verify(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5","nodeb","hostname -s"])
        if result!="nodeb":raise RuntimeError("SSH alias returned unexpected identity")
        print("JNS_SSH_ALIAS_UPDATED",flush=True)
    except Exception:
        cfg.write_text(before)
        os.chmod(cfg,0o600)
        print("JNS_SSH_ROLLBACK_COMPLETE",flush=True)
        raise
result=verify(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
               "nodeb","qm status 905"])
print("NODEB_VERIFIED",result,flush=True)
print("JNS_SSH_REPAIR_OK",flush=True)
