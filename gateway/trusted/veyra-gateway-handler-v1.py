#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path("/root/veyra-v0.9/source071/veyra").resolve()
BACKUPS = Path("/root/veyra-v0.9/backups")
ALLOWED = {"veyra_source_audit", "veyra_source_full", "veyra_apply_release", "veyra_build_v092", "veyra_pxe_prepare"}
EDITABLE = {
    "veyra/__init__.py",
    "veyra/models.py",
    "veyra/app.py",
    "veyra/view.py",
    "veyra/programmes.py",
    "browser-extension/content.js",
    "browser-extension/manifest.json",
}

def load_job(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("job_type") not in ALLOWED:
        raise SystemExit("wrong job_type")
    return data

def audit(full=False):
    files=[
        "veyra/__init__.py","veyra/state.py","veyra/models.py","veyra/app.py",
        "veyra/view.py","veyra/providers/catalog.py","browser-extension/content.js",
        "browser-extension/manifest.json","installer/install_orchestrator.py"
    ]
    print("=== VEYRA SOURCE AUDIT ===")
    for rel in files:
        p=BASE/rel
        print(f"===== {rel} =====")
        if not p.is_file():
            print("MISSING"); continue
        txt=p.read_text(encoding="utf-8",errors="replace")
        if full or rel in {"veyra/state.py","veyra/models.py","veyra/providers/catalog.py"}:
            print(txt[:120000])
        elif rel=="veyra/app.py":
            print("\n".join(x for x in txt.splitlines() if x.startswith("@app.") or x.startswith("async def ") or x.startswith("def ")))
        elif rel=="veyra/view.py":
            print("\n".join(x for x in txt.splitlines() if any(k in x for k in ("function ","Continue","provider","Home","home","render"))))
        elif rel=="browser-extension/content.js":
            print("\n".join(x for x in txt.splitlines() if any(k in x for k in ("keydown","Escape","Backspace","ctrlKey","shiftKey","Alt","Home"))))
        else:
            print(txt[:30000])
    print("VEYRA_SOURCE_AUDIT_OK")
    return 0

def target(rel):
    if rel not in EDITABLE:
        raise ValueError(f"path not allow-listed: {rel}")
    p=(BASE/rel).resolve()
    p.relative_to(BASE)
    return p

def validate():
    subprocess.run(["python3","-m","compileall","-q",str(BASE/"veyra")],check=True,timeout=120)
    manifest=BASE/"browser-extension/manifest.json"
    if manifest.exists():
        json.loads(manifest.read_text(encoding="utf-8"))
    app=(BASE/"veyra/app.py").read_text(encoding="utf-8")
    if "/api/admin-console/io" in app:
        raise RuntimeError("obsolete web-shell route detected")

def apply_release(job):
    files=job.get("files")
    if not isinstance(files,dict) or not files:
        raise ValueError("files mapping required")
    if len(files)>len(EDITABLE):
        raise ValueError("too many files")
    job_id=str(job.get("job_id","release")).replace("/","_")
    backup=BACKUPS/job_id
    if backup.exists():
        raise RuntimeError("backup already exists")
    backup.mkdir(parents=True,mode=0o700)
    changed=[]
    try:
        for rel,text in files.items():
            if not isinstance(text,str) or len(text.encode("utf-8"))>500000:
                raise ValueError(f"invalid file payload: {rel}")
            dst=target(rel)
            saved=backup/rel
            saved.parent.mkdir(parents=True,exist_ok=True)
            existed=dst.exists()
            if existed:
                shutil.copy2(dst,saved)
                mode=dst.stat().st_mode & 0o777
            else:
                mode=0o644
            dst.parent.mkdir(parents=True,exist_ok=True)
            tmp=dst.with_name(dst.name+".veyra-new")
            tmp.write_text(text,encoding="utf-8")
            os.chmod(tmp,mode)
            os.replace(tmp,dst)
            changed.append((rel,dst,existed))
        validate()
    except Exception:
        for rel,dst,existed in reversed(changed):
            saved=backup/rel
            if existed:
                shutil.copy2(saved,dst)
            else:
                dst.unlink(missing_ok=True)
        validate()
        raise
    print(f"VEYRA_RELEASE_APPLY_OK backup={backup}")
    return 0

def build_v092():
    runner=Path("/usr/local/libexec/jns-veyra-build-v092")
    if not runner.is_file() or not os.access(runner,os.X_OK):
        print("Veyra v0.9.2 build runner not installed",file=sys.stderr)
        return 78
    return subprocess.call([str(runner)])

def pxe_prepare():
    runner=Path("/usr/local/libexec/jns-veyra-pxe-v092")
    if not runner.is_file() or not os.access(runner,os.X_OK):
        print("Veyra v0.9.2 PXE publisher not installed",file=sys.stderr)
        return 78
    return subprocess.call([str(runner)])

def main():
    if len(sys.argv)!=2:
        return 64
    try:
        job=load_job(sys.argv[1])
        kind=job["job_type"]
        if kind=="veyra_source_audit": return audit(False)
        if kind=="veyra_source_full": return audit(True)
        if kind=="veyra_apply_release": return apply_release(job)
        if kind=="veyra_build_v092": return build_v092()
        if kind=="veyra_pxe_prepare": return pxe_prepare()
    except Exception as exc:
        print(f"VEYRA_GATEWAY_ERROR: {exc}",file=sys.stderr)
        return 1
    return 64

if __name__=="__main__":
    raise SystemExit(main())
