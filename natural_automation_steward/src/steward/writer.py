from __future__ import annotations

import base64
import json
import time
import uuid

from .target import TargetResolver


class ApplyError(RuntimeError):
    pass


def _out(result: dict) -> str:
    return str(result.get("out-data") or "")


def _guest(resolver: TargetResolver, args: list[str], timeout: float = 180.0) -> str:
    try:
        return _out(resolver.guest_exec(args, timeout=timeout))
    except Exception as exc:
        raise ApplyError(str(exc)) from exc


def _restore(resolver: TargetResolver, backup: str, *, existed: bool) -> None:
    code = (
        "import os,shutil;"
        f"p='/config/automations.yaml';b={backup!r};"
        + (
            "shutil.copy2(b,p)"
            if existed
            else "os.path.exists(p) and os.unlink(p)"
        )
    )
    _guest(resolver, ["docker", "exec", "homeassistant", "python3", "-c", code], timeout=60)


def apply_automation(resolver: TargetResolver, automation: dict) -> dict:
    if not isinstance(automation, dict):
        raise ApplyError("automation must be an object")
    if not automation.get("alias"):
        raise ApplyError("automation alias is required")
    if not automation.get("trigger"):
        raise ApplyError("automation trigger is required")
    if not automation.get("action"):
        raise ApplyError("automation action is required")

    automation = dict(automation)
    automation.setdefault("id", "natural_" + uuid.uuid4().hex)
    automation.setdefault("mode", "single")

    payload = base64.b64encode(
        json.dumps(automation, separators=(",", ":")).encode()
    ).decode()
    stamp = time.strftime("%Y%m%d-%H%M%S")

    code = f"""import base64,json,os,shutil,yaml
p='/config/automations.yaml'
b='/config/.steward-backups'
os.makedirs(b,exist_ok=True)
existed=os.path.exists(p)
backup=f"{{b}}/automations.{stamp}.yaml"
if existed:
    shutil.copy2(p,backup)
else:
    open(backup,'w').write('[]\\n')
obj=json.loads(base64.b64decode('{payload}'))
data=yaml.safe_load(open(p)) if existed else []
data=data or []
if not isinstance(data,list):
    raise RuntimeError('automations.yaml is not a YAML list')
if any(str(x.get('id',''))==str(obj['id']) for x in data if isinstance(x,dict)):
    raise RuntimeError('automation id already exists')
data.append(obj)
tmp=p+'.steward.tmp'
with open(tmp,'w') as f:
    yaml.safe_dump(data,f,sort_keys=False,allow_unicode=True)
os.replace(tmp,p)
print(json.dumps({{'backup':backup,'path':p,'id':obj['id'],'existed':existed}}))
"""

    meta_raw = _guest(
        resolver,
        ["docker", "exec", "homeassistant", "python3", "-c", code],
        timeout=90,
    )
    try:
        meta = json.loads(meta_raw)
    except json.JSONDecodeError as exc:
        raise ApplyError("Writer did not return valid transaction metadata") from exc

    try:
        check = _guest(resolver, ["ha", "core", "check"], timeout=300)
        _guest(resolver, ["ha", "core", "restart"], timeout=300)

        deadline = time.monotonic() + 120
        last_error = ""
        while time.monotonic() < deadline:
            try:
                _guest(resolver, ["ha", "core", "info"], timeout=30)
                break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(2)
        else:
            raise ApplyError(f"Home Assistant did not return after restart: {last_error}")

        verify_code = (
            "import yaml;"
            "p='/config/automations.yaml';"
            "d=yaml.safe_load(open(p)) or [];"
            f"assert any(str(x.get('id',''))=={automation['id']!r} for x in d if isinstance(x,dict));"
            "print('verified')"
        )
        verify = _guest(
            resolver,
            ["docker", "exec", "homeassistant", "python3", "-c", verify_code],
            timeout=60,
        )
    except Exception:
        try:
            _restore(resolver, meta["backup"], existed=bool(meta.get("existed", True)))
            _guest(resolver, ["ha", "core", "restart"], timeout=300)
        finally:
            raise

    return {
        "ok": True,
        "automation_id": automation["id"],
        "backup": meta["backup"],
        "path": meta["path"],
        "check": check,
        "verify": verify.strip(),
        "target": resolver.status(),
    }
