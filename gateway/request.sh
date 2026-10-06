#!/usr/bin/env bash
set -euo pipefail
echo "=== INSTALL NATURAL AUTOMATION + STEWARD ON NODE B / HA-GENERAL ==="
date -Is

ssh nodeb 'bash -s' <<'NODEB'
set -euo pipefail
ROOT=/opt/natural-automation
TS=$(date +%Y%m%d-%H%M%S)
BACKUP="$ROOT/backup-$TS"
mkdir -p "$BACKUP"
cp -a "$ROOT/natural_automation.py" "$BACKUP/"
cp -a /etc/systemd/system/natural-automation.service "$BACKUP/" 2>/dev/null || true
cp -a "$ROOT/data" "$BACKUP/data" 2>/dev/null || true
echo "backup=$BACKUP"

mkdir -p "$ROOT/steward" "$ROOT/data/repair_packs"

cat > "$ROOT/steward/__init__.py" <<'PY'
__version__ = "0.4-live"
PY

cat > "$ROOT/steward/store.py" <<'PY'
import json, sqlite3, time
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS facts(
  namespace TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at REAL NOT NULL,
  PRIMARY KEY(namespace,key)
);
CREATE TABLE IF NOT EXISTS observations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repairs(
  id TEXT PRIMARY KEY,
  fingerprint TEXT UNIQUE,
  title TEXT NOT NULL,
  subsystem TEXT NOT NULL,
  recipe_json TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5,
  successful_runs INTEGER NOT NULL DEFAULT 0,
  failed_runs INTEGER NOT NULL DEFAULT 0,
  portable INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS repair_search USING fts5(
  repair_id UNINDEXED,title,subsystem,problem,symptoms,diagnosis,steps
);
"""

class StewardStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path)
        self.db.execute("PRAGMA busy_timeout=3000")
        self.db.executescript(SCHEMA)
    def set_fact(self,namespace,key,value):
        self.db.execute("""INSERT INTO facts(namespace,key,value_json,updated_at)
          VALUES(?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET
          value_json=excluded.value_json,updated_at=excluded.updated_at""",
          (namespace,key,json.dumps(value,sort_keys=True),time.time()))
        self.db.commit()
    def observe(self,kind,source,payload):
        self.db.execute("INSERT INTO observations(ts,kind,source,payload_json) VALUES(?,?,?,?)",
          (time.time(),kind,source,json.dumps(payload,sort_keys=True)))
        self.db.commit()
    def status(self):
        return {
          "facts":self.db.execute("SELECT count(*) FROM facts").fetchone()[0],
          "observations":self.db.execute("SELECT count(*) FROM observations").fetchone()[0],
          "repairs":self.db.execute("SELECT count(*) FROM repairs").fetchone()[0],
        }
PY

cat > "$ROOT/steward/writer.py" <<'PY'
import base64, json, subprocess, time, uuid

class ApplyError(RuntimeError): pass

def _guest(vmid,args,timeout=120):
    p=subprocess.run(["qm","guest","exec",str(vmid),"--",*args],
      capture_output=True,text=True,timeout=timeout)
    if p.returncode!=0:
        raise ApplyError((p.stderr or p.stdout or "qm guest exec failed").strip())
    try: r=json.loads(p.stdout)
    except Exception as exc: raise ApplyError("Invalid qemu guest-agent response") from exc
    if r.get("exitcode",0)!=0:
        raise ApplyError((r.get("err-data") or r.get("out-data") or "guest command failed").strip())
    return r.get("out-data","")

def _core_check(vmid):
    return _guest(vmid,["ha","core","check"],timeout=180)

def _core_restart(vmid):
    return _guest(vmid,["ha","core","restart"],timeout=180)

def apply_automation(vmid,automation):
    if not isinstance(automation,dict):
        raise ApplyError("automation must be an object")
    if not automation.get("alias"):
        raise ApplyError("automation alias is required")
    if not automation.get("trigger"):
        raise ApplyError("automation trigger is required")
    if not automation.get("action"):
        raise ApplyError("automation action is required")
    automation=dict(automation)
    automation.setdefault("id","natural_"+uuid.uuid4().hex)
    automation.setdefault("mode","single")
    payload=base64.b64encode(json.dumps(automation,separators=(",",":")).encode()).decode()
    stamp=time.strftime("%Y%m%d-%H%M%S")
    code=f"""import base64,json,os,shutil,yaml
p='/config/natural_automation.yaml'
b='/config/.steward-backups'
os.makedirs(b,exist_ok=True)
backup=f"{{b}}/natural_automation.{stamp}.yaml"
if os.path.exists(p): shutil.copy2(p,backup)
else: open(backup,'w').write('[]\\n')
obj=json.loads(base64.b64decode('{payload}'))
data=[]
if os.path.exists(p):
    data=yaml.safe_load(open(p)) or []
if not isinstance(data,list): raise RuntimeError('natural_automation.yaml is not a YAML list')
if any(str(x.get('id',''))==str(obj['id']) for x in data if isinstance(x,dict)):
    raise RuntimeError('automation id already exists')
data.append(obj)
tmp=p+'.steward.tmp'
with open(tmp,'w') as f: yaml.safe_dump(data,f,sort_keys=False,allow_unicode=True)
os.replace(tmp,p)
print(json.dumps({{'backup':backup,'path':p,'id':obj['id']}}))
"""
    out=_guest(vmid,["docker","exec","homeassistant","python3","-c",code])
    meta=json.loads(out)
    try:
        check=_core_check(vmid)
    except Exception:
        rb=f"""import shutil; shutil.copy2({meta['backup']!r},'/config/natural_automation.yaml')"""
        _guest(vmid,["docker","exec","homeassistant","python3","-c",rb])
        raise
    # HA YAML automation includes are not guaranteed to hot-reload from an external host;
    # restart HA-General only after a successful config validation.
    _core_restart(vmid)
    return {"ok":True,"automation_id":automation["id"],"backup":meta["backup"],"check":check}
PY

cat > "$ROOT/steward/repair_capture.py" <<'PY'
import hashlib,json,time,uuid

def fingerprint(recipe):
    core={k:recipe.get(k) for k in ("title","subsystem","problem","diagnosis","repair_steps","verification_steps","rollback_steps","applicability")}
    return hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def capture(store,recipe,success=True):
    r=dict(recipe)
    rid=r.setdefault("id",uuid.uuid4().hex)
    fp=fingerprint(r)
    row=store.db.execute("SELECT id,recipe_json,successful_runs,failed_runs FROM repairs WHERE fingerprint=?",(fp,)).fetchone()
    if row:
        old=json.loads(row[1]); old.update({k:v for k,v in r.items() if v not in (None,[],{},'')})
        sr=row[2]+(1 if success else 0); fr=row[3]+(0 if success else 1)
        store.db.execute("UPDATE repairs SET recipe_json=?,successful_runs=?,failed_runs=?,updated_at=? WHERE id=?",
          (json.dumps(old,sort_keys=True),sr,fr,time.time(),row[0])); rid=row[0]
    else:
        store.db.execute("""INSERT INTO repairs(id,fingerprint,title,subsystem,recipe_json,confidence,successful_runs,failed_runs,portable,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",(rid,fp,r.get("title","Repair"),r.get("subsystem","unknown"),json.dumps(r,sort_keys=True),
          float(r.get("confidence",0.5)),1 if success else 0,0 if success else 1,int(bool(r.get("portable",False))),time.time()))
    store.db.commit()
    return rid
PY

python3 - <<'PY'
from pathlib import Path
p=Path("/opt/natural-automation/natural_automation.py")
s=p.read_text()
s=s.replace("VMID=902","VMID=int(os.environ.get('NA_VMID','905'))",1)
if "from steward.store import StewardStore" not in s:
    marker='from real_progress import ProgressModel, JobTracker\n'
    insert='from steward.store import StewardStore\nfrom steward.writer import apply_automation, ApplyError\n'
    s=s.replace(marker,marker+insert,1)
if 'STEWARD=StewardStore(DATA/"steward.db")' not in s:
    marker='PROGRESS_STATS=DATA/"progress_stats.json"\n'
    s=s.replace(marker,marker+'STEWARD=StewardStore(DATA/"steward.db")\n',1)

old='''            if path=="/api/admin/removal-review":
                if not admin_allowed(self): return self.sendj({"error":"Admin review is available only from the local management LAN."},403)
                return self.sendj(review_removal(str(p.get("proposal_id","")),str(p.get("decision",""))))
            self.send_error(404)'''
new='''            if path=="/api/admin/removal-review":
                if not admin_allowed(self): return self.sendj({"error":"Admin review is available only from the local management LAN."},403)
                return self.sendj(review_removal(str(p.get("proposal_id","")),str(p.get("decision",""))))
            if path=="/api/steward/status":
                if not admin_allowed(self): return self.sendj({"error":"Steward status is available only from the local management LAN."},403)
                st=STEWARD.status(); st.update({"ok":True,"vmid":VMID,"apply_enabled":ENABLE_APPLY})
                return self.sendj(st)
            if path=="/api/apply-automation":
                if not admin_allowed(self): return self.sendj({"error":"Automation apply is available only from the local management LAN."},403)
                if not ENABLE_APPLY: return self.sendj({"error":"Controlled automation write gate is closed."},403)
                unresolved=p.get("unresolved") or []
                if unresolved: return self.sendj({"error":"Unresolved targets remain; refusing to apply.","unresolved":unresolved},409)
                result=apply_automation(VMID,p.get("automation"))
                audit("automation_applied",vmid=VMID,automation_id=result.get("automation_id"),backup=result.get("backup"),logic=["Targets resolved.","Configuration written transactionally.","Home Assistant configuration check passed.","HA-General restarted after validation."])
                STEWARD.observe("automation_applied","natural_automation",{"vmid":VMID,"automation_id":result.get("automation_id")})
                return self.sendj(result)
            self.send_error(404)'''
if old not in s:
    raise SystemExit("POST route patch marker not found")
s=s.replace(old,new,1)
p.write_text(s)
PY

# Update service narrowly: HA-General + automation writes.
python3 - <<'PY'
from pathlib import Path
p=Path("/etc/systemd/system/natural-automation.service")
s=p.read_text()
s=s.replace("Environment=NA_ENABLE_APPLY=0","Environment=NA_ENABLE_APPLY=1")
if "Environment=NA_VMID=" in s:
    import re
    s=re.sub(r"Environment=NA_VMID=\d+","Environment=NA_VMID=905",s)
else:
    s=s.replace("Environment=NA_PORT=8099","Environment=NA_PORT=8099\nEnvironment=NA_VMID=905")
p.write_text(s)
PY

# Initialize local offline Steward database with node facts.
cd "$ROOT"
python3 - <<'PY'
from steward.store import StewardStore
s=StewardStore("/opt/natural-automation/data/steward.db")
s.set_fact("system","node",{"hypervisor":"nodeb","vmid":905,"name":"ha-s2-general","ip":"10.10.10.223"})
s.set_fact("policy","write",{"intent":"automate","target_vmid":905,"repairs":False,"pairing":False,"service_migration":False})
s.observe("install","steward",{"version":"0.4-live","mode":"offline-first","merged_with":"Natural Automation"})
print(s.status())
PY

python3 -m py_compile "$ROOT/natural_automation.py" "$ROOT/steward/store.py" "$ROOT/steward/writer.py" "$ROOT/steward/repair_capture.py"
systemctl daemon-reload
systemctl restart natural-automation.service
sleep 2

echo "=== SERVICE ==="
systemctl --no-pager --full status natural-automation.service | sed -n '1,25p'
echo
echo "=== LOCAL STATUS ==="
curl -fsS http://127.0.0.1:8099/api/status; echo
echo "=== STEWARD STATUS ==="
curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8099/api/steward/status; echo
echo
echo "=== HA-GENERAL PRECHECK ==="
qm status 905
qm guest exec 905 -- ha core info | sed -n '1,80p'
echo
echo "=== HA CONFIG CHECK ==="
qm guest exec 905 -- ha core check | sed -n '1,80p'
echo
echo "INSTALL_OK backup=$BACKUP"
NODEB
