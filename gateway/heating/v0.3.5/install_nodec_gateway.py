#!/usr/bin/env python3
"""Root-local installer for dormant JNS heating v0.3.5 gateway capability.

Never called by GitHub Actions or the active JNS gateway. Default: dry-run.
Installation does NOT touch VM905, invoke a HA command, or create approval.
"""
import argparse
import ast
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=Path("/usr/local/sbin/jns-gateway-exec")
PRIOR=Path("/usr/local/sbin/jns-gateway-exec.pre-heating-v035")
DEST=Path("/usr/local/libexec/jns-heating-v035")
PERMIT_DIR=Path("/etc/jns/heating-v035")
ROOT_SHA="9d4f853b2e8264cb10a25a5ee5f23bd92c521e86f447de8c7278644d8caa7f8a"
REQUIRED=("transaction.py","promotion_policy.py","root_owned_promotion.py","approval_once.py")
WRAPPER="jns-gateway-exec-wrapper-v4-heating.sh"
OLD_WRAPPER=HERE.parent.parent/"trusted/jns-gateway-exec-wrapper-v3.sh"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def preflight():
    if ROOT.is_symlink() or not ROOT.is_file() or sha(ROOT.read_bytes())!=ROOT_SHA:
        raise RuntimeError("Node C trusted gateway changed; installation blocked")
    if DEST.exists() or PRIOR.exists():
        raise RuntimeError("Heating root capability already installed, refusing overwrite")
    before=OLD_WRAPPER.read_text()
    after=(HERE/WRAPPER).read_text()
    needle='  *)\n    exec /usr/local/sbin/jns-gateway-exec.base "$REAL"\n    ;;'
    extension=('  ha_heating_v035_promote)\n'
      '    exec /usr/local/libexec/jns-heating-v035/root_owned_promotion.py "$REAL"\n'
      '    ;;\n')
    if before.count(needle)!=1 or after!=before.replace(needle,extension+needle):
        raise RuntimeError("Unexpected root wrapper differences")
    for name in REQUIRED:
        path=HERE/name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Missing or symlinked handler dependency")
        ast.parse(path.read_text())
    subprocess.run(["bash","-n",str(HERE/WRAPPER)],check=True)


def install(path,destination,mode):
    fd,tmp=tempfile.mkstemp(prefix=".jns-heating-install-",dir=destination.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(path.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(tmp,0,0)
        os.chmod(tmp,mode)
        os.replace(tmp,destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    preflight()
    print("JNS_HEATING_NODEC_GATE_PLAN dormant=true one_allowlisted_type=true "
          "restart=false no_vm905_changes=true",flush=True)
    if not args.apply:
        return
    if os.geteuid()!=0 or not sys.stdin.isatty():
        raise RuntimeError("Root-owned local interactive terminal required")
    reply=input("Type INSTALL HEATING GATE ONLY to install dormant capability: ")
    if reply!="INSTALL HEATING GATE ONLY":
        raise RuntimeError("Local root confirmation absent")
    if PERMIT_DIR.exists():
        raise RuntimeError("Approval directory exists: review previous state first")
    DEST.mkdir(mode=0o750)
    os.chown(DEST,0,0)
    PERMIT_DIR.mkdir(parents=True,mode=0o700)
    os.chown(PERMIT_DIR,0,0)
    for name in REQUIRED:
        mode=0o750 if name in ("root_owned_promotion.py","approval_once.py") else 0o640
        install(HERE/name,DEST/name,mode)
    install(ROOT,PRIOR,0o500)
    try:
        install(HERE/WRAPPER,ROOT,0o755)
        subprocess.run(["bash","-n",str(ROOT)],check=True)
        if ROOT.stat().st_uid!=0 or ROOT.stat().st_mode & 0o022:
            raise RuntimeError("Installed wrapper permissions wrong")
    except BaseException:
        install(PRIOR,ROOT,0o755)
        raise
    print("JNS_HEATING_NODEC_GATE_INSTALLED dormant=true root_approval_required=true")


if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("JNS_HEATING_NODEC_GATE_BLOCKED",type(e).__name__,str(e)[:180],file=sys.stderr)
        sys.exit(2)
