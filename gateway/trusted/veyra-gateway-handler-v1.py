#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = Path("/root/veyra-v0.9/source071/veyra")
ALLOWED = {"veyra_source_audit", "veyra_build_v092"}

def load_job(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("job_type") not in ALLOWED:
        raise SystemExit("wrong job_type")
    return data

def audit() -> int:
    print("=== VEYRA SOURCE AUDIT ===")
    for rel in [
        "veyra/__init__.py",
        "veyra/state.py",
        "veyra/models.py",
        "veyra/app.py",
        "veyra/view.py",
        "veyra/providers/catalog.py",
        "browser-extension/content.js",
        "installer/install_orchestrator.py",
    ]:
        p = BASE / rel
        print(f"===== {rel} =====")
        if not p.is_file():
            print("MISSING")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if rel in {"veyra/state.py", "veyra/models.py", "veyra/providers/catalog.py"}:
            print(text[:24000])
        else:
            lines = text.splitlines()
            if rel == "veyra/app.py":
                picks = [x for x in lines if x.startswith("@app.") or x.startswith("async def ") or x.startswith("def ")]
                print("\n".join(picks))
            elif rel == "veyra/view.py":
                picks = [x for x in lines if any(k in x for k in ("function ", "Continue", "provider", "Home", "home"))]
                print("\n".join(picks[:240]))
            elif rel == "browser-extension/content.js":
                picks = [x for x in lines if any(k in x for k in ("keydown", "Escape", "Backspace", "ctrlKey", "shiftKey", "Alt", "Home"))]
                print("\n".join(picks[:160]))
            else:
                print(text[:16000])
    print("VEYRA_SOURCE_AUDIT_OK")
    return 0

def build_v092() -> int:
    runner = Path("/usr/local/libexec/jns-veyra-build-v092")
    if not runner.is_file() or not os.access(runner, os.X_OK):
        print("Veyra v0.9.2 build runner not installed", file=sys.stderr)
        return 78
    return subprocess.call([str(runner)])

def main() -> int:
    if len(sys.argv) != 2:
        print("job json required", file=sys.stderr)
        return 64
    job = load_job(sys.argv[1])
    if job["job_type"] == "veyra_source_audit":
        return audit()
    if job["job_type"] == "veyra_build_v092":
        return build_v092()
    return 64

if __name__ == "__main__":
    raise SystemExit(main())
