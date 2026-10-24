#!/usr/bin/env python3
"""JNS Steward repair/maintenance knowledge v2.

Static repo-wide inventory -> evidence-graded dossiers -> transactional SQLite.
No imported script runs; no HA service restarts; no secrets or live HA configuration
are consulted. Old Steward repairs, learning counters and private facts are retained.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
import uuid

SCHEMA="jns-steward-repair-catalogue-v2"
SUFFIXES={".py",".sh",".bash",".ps1"}
TOPS={"gateway","management_bridge","ha_testing_dashboard",
      "natural_automation_steward","tools","custom_components"}
SKIP={"__pycache__","node_modules",".git",".venv","vendor",
      "testdata","site-packages"}
MAX_SCRIPT_BYTES=300000
REFS=[
    ("Proxmox guest operations",r"\bqm\s+(?:guest|status|config|clone|restore|rollback)\b|pvesh\b"),
    ("LXC operations",r"\bpct\s+(?:exec|config|restore|snapshot|status|push)\b"),
    ("Home Assistant validation",r"\bha\s+core\s+check\b"),
    ("Home Assistant automation reload",r"automation/reload|automation\.reload"),
    ("Home Assistant configuration",r"/config/|automations\.yaml|configuration\.yaml"),
    ("Home Assistant registry access",r"core\.entity_registry|core\.config_entries"),
    ("MQTT or Zigbee interactions",r"mosquitto|zigbee2mqtt|coordinator|zigbee"),
    ("SSH/remote execution",r"\bssh\b|\bscp\b|StrictHostKeyChecking"),
    ("HTTP/REST calls",r"\bcurl\b|urllib\.request|requests\.(?:get|post)|https?://"),
    ("Process/service management",r"systemctl|service\s+(?:restart|stop|start)|ha\s+core\s+restart"),
    ("Container execution",r"docker\s+exec|docker\s+ps"),
    ("Transactional file updates",r"os\.replace|tempfile\.mkstemp|mv\s+|install\s+-m"),
    ("SQLite access",r"sqlite3|steward\.db"),
]
DOMAINS=[
    ("zigbee",r"zigbee|z2m|coordinator|serial.bridge"),
    ("tuya",r"tuya"),
    ("doorbell_security",r"doorbell|kc868|alarm|security"),
    ("lighting",r"lux|lighting|light|dimmer|bedtime|porch"),
    ("heating",r"heat|thermal|temperature|honeywell"),
    ("cameras",r"camera|tapo|webrtc|go2rtc|rtsp"),
    ("media",r"veyra|itvx|obs|capture|ffmpeg|audio|chime"),
    ("dns_network",r"dns|dhcp|route|ssh|network|mqtt|proxmox|nodea|nodeb|nodec"),
    ("steward",r"steward|natural.automation|knowledge|repair.catalogue"),
]
PRIVATE_KEY=re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA|PRIVATE) PRIVATE KEY-----")
SECRET_ASSIGN=re.compile(r"""(?im)^\s*(?:api_key|private_key|password|access_token|bearer_token)\s*[:=]\s*["'][A-Za-z0-9._-]{25,}["']\s*$""")
def sha256(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def classified(path:str,text:str)->str:
    name=path.lower()
    for label,pattern in DOMAINS:
        if re.search(pattern,name):return label
    for label,pattern in DOMAINS:
        if re.search(pattern,text[:1000],re.I):return label
    return "infrastructure"
def eligible(path:Path, root:Path)->bool:
    if not path.is_file() or path.is_symlink():return False
    rel=path.relative_to(root).as_posix()
    if any(part in SKIP for part in path.relative_to(root).parts):return False
    if rel.startswith(".github/workflows/"):
        return path.suffix.lower() in (".yml",".yaml")
    if rel.split("/",1)[0] not in TOPS:return False
    if rel.startswith("custom_components/") and not re.search(
        r"(repair|audit|recover|diagnos|deploy|setup|validate)",rel,re.I
    ):return False
    if path.suffix.lower() in SUFFIXES:return True
    # Configuration fragments are only indexed where explicitly recovery related.
    if path.suffix.lower() in (".yaml",".yml") and re.search(
        r"repair|recover|restore|rollback|doorbell|migration|lux.manual",rel,re.I
    ):return True
    return False
def candidates(root:Path)->list[Path]:
    paths=[]
    for base in sorted(TOPS|{".github"}):
        folder=root/base
        if folder.is_dir():
            for file in folder.rglob("*"):
                if eligible(file,root):paths.append(file)
    return sorted(set(paths))
def heading(path:str)->str:
    return re.sub(r"\s+"," ",re.sub(r"[-_.]+"," ",Path(path).stem)).strip().title()
def source_claim(text:str,path:str)->tuple[str,str]:
    if path.endswith(".py"):
        try:
            doc=ast.get_docstring(ast.parse(text))
            if doc:
                first=" ".join(doc.strip().split("\n\n",1)[0].split())
                if first:return first[:600],"python_module_docstring"
        except (SyntaxError,ValueError):pass
    if path.endswith((".yml",".yaml")) and path.startswith(".github/workflows/"):
        match=re.search(r"(?m)^name:\s*['\"]?(.+?)['\"]?\s*$",text)
        if match:return "Workflow: "+match.group(1).strip(),"workflow_name"
    comments=[]
    for line in text.splitlines()[:32]:
        clean=line.strip()
        if not clean or clean.startswith("#!") or clean.startswith("# shellcheck"):continue
        if clean.startswith("#"):
            comment=clean.lstrip("#").strip()
            if comment and not re.search(r"(copyright|license|encoding|coding[:=])",comment,re.I):
                comments.append(comment)
            if len(comments)>=4:break
        elif not comments and len(line)>100:break
    if comments:return " ".join(comments)[:600],"leading_source_comments"
    return "Undocumented purpose; inferred from filename only: "+heading(path),"filename_only_inference"
def workflows(root:Path)->dict[str,list[str]]:
    files=[p for p in (root/".github/workflows").glob("*.y*ml") if p.is_file()]
    script_paths=[p.relative_to(root).as_posix() for p in candidates(root)
                  if not p.relative_to(root).as_posix().startswith(".github/workflows/")]
    relationships={}
    for wf in files:
        s=wf.read_text(encoding="utf-8",errors="replace")
        wf_rel=wf.relative_to(root).as_posix()
        for rel in script_paths:
            if rel in s:relationships.setdefault(rel,[]).append(wf_rel)
    return relationships
def explain(repo_root:Path,p:Path,connections:dict)->dict:
    rel=p.relative_to(repo_root).as_posix()
    raw=p.read_bytes()
    if len(raw)>MAX_SCRIPT_BYTES:
        raise ValueError("oversized script cannot safely be imported: "+rel)
    if b"\x00" in raw:raise ValueError("binary-like source: "+rel)
    text=raw.decode("utf-8",errors="replace")
    if PRIVATE_KEY.search(text) or SECRET_ASSIGN.search(text):
        raise ValueError("possible embedded credential: "+rel)
    purpose,purpose_evidence=source_claim(text,rel)
    domain=classified(rel,text)
    operations=[name for name,pattern in REFS if re.search(pattern,text,re.I)]
    verified_patterns=[name for name,pattern in (
        ("explicit assertions/exit gates",r"\bassert\b|set -e|exit\s+[1-9]|raise\s+\w+"),
        ("configuration check",r"\bha\s+core\s+check\b"),
        ("smoke/acceptance probes",r"smoke|acceptance|health.check|read.back|verify"),
    ) if re.search(pattern,text,re.I)]
    recovery_patterns=[name for name,pattern in (
        ("rollback/restore implementation",r"rollback|restore|revert"),
        ("backup/snapshot operation",r"\bbackup\b|\bsnapshot\b|\.jns.backups"),
    ) if re.search(pattern,text,re.I)]
    is_workflow=rel.startswith(".github/workflows/")
    archived="live_recovered" in rel or "/queue/" in rel or "/results/" in rel
    how=["Source inspection indicates: "+", ".join(operations)]
    if not operations:how=["No recognised operational primitives extracted; inspect source before using."]
    how.append("Source is read-only knowledge; do not execute from this catalogue.")
    evidence={
        "source_path":rel,
        "source_sha256":sha256(raw),
        "purpose_provenance":purpose_evidence,
        "how_provenance":"static_code_inspection",
        "workflow_references":sorted(connections.get(rel,[])),
        "execution_result":"not_established_from_repository_source",
        "observed_production_success":False,
        "observed_production_failure":False,
        "source_class":"orchestration_workflow" if is_workflow else "source_script",
        "lifecycle":"historical_snapshot_or_queue" if archived else "repository_current",
        "repository":"jamienewton2269/JNS-Home-Assistant-Deployment",
    }
    return {
        "id":uuid.uuid5(uuid.NAMESPACE_URL,"jns-steward-catalogue-v2:"+rel).hex,
        "title":heading(rel),
        "subsystem":domain,
        "problem":purpose,
        "diagnosis":"Why/source evidence: "+purpose_evidence
            +". HOW evidence: "+", ".join(operations or ["requires inspection"])
            +". Execution success has NOT been verified from source alone.",
        "symptoms":[],
        "preconditions":[
            "Identify current target node, VM/CT and owner by live role resolution.",
            "Check current hardware, HA state, configuration and dependencies.",
            "Obtain operator approval and a backup before any write or restart.",
        ],
        "repair_steps":how,
        "verification_steps":(
            ["Source includes "+", ".join(verified_patterns)+
             "; adapt these checks and independently validate live behaviour."]
            if verified_patterns else
            ["Source has no recognised verification gate; require explicit acceptance checks before any use."]
        ),
        "rollback_steps":(
            ["Source references "+", ".join(recovery_patterns)+
             "; review exact rollback before applying."]
            if recovery_patterns else
            ["No rollback was demonstrated by static source inspection; build and test one first."]
        ),
        "why":purpose,
        "how":"; ".join(how),
        "evidence":evidence,
        "applicability":{"repository_root":str(repo_root.name),"source_family":rel.split("/")[0],
            "workflow_references":evidence["workflow_references"],
            "current_target":"must_resolve","historical_snapshot":archived},
        "exclusions":[
            "Manual-review knowledge only; does not grant execution permission.",
            "Presence in GitHub does not mean deployment, successful test or production use.",
            "Never copy recovered snapshots blindly onto production guests.",
        ],
        "confidence":0.55 if purpose_evidence not in ("filename_only_inference",) else 0.25,
        "portable":False,
        "safety_class":"manual_review",
        "source_path":rel,
        "source_sha256":evidence["source_sha256"],
        "artifact":{"kind":"workflow" if is_workflow else p.suffix.lstrip("."),
                    "content":text},
    }
def build(repo_root:Path)->dict:
    relationships=workflows(repo_root)
    records=[];excluded=[]
    for path in candidates(repo_root):
        try:records.append(explain(repo_root,path,relationships))
        except (ValueError,UnicodeError,OSError) as e:
            excluded.append({"path":path.relative_to(repo_root).as_posix(),
                             "reason":str(e).split(":")[0][:120]})
    if excluded:raise RuntimeError("Fail closed: source items excluded: "+json.dumps(excluded))
    if not records:raise RuntimeError("No repair sources found")
    if len({x["source_path"] for x in records})!=len(records):
        raise RuntimeError("duplicate source paths")
    repo_commit=subprocess.run(["git","rev-parse","HEAD"],cwd=repo_root,text=True,
        capture_output=True,check=True).stdout.strip()
    return {"schema":SCHEMA,"repo_commit":repo_commit,
            "source_repository":"jamienewton2269/JNS-Home-Assistant-Deployment",
            "record_count":len(records),"records":records}
def export(payload:dict,path:Path)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".jns-repair-")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(payload,f,sort_keys=True,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def import_catalogue(seed:Path,db_path:Path)->dict:
    payload=json.loads(seed.read_text(encoding="utf-8"))
    if payload.get("schema")!=SCHEMA:raise RuntimeError("Unexpected catalogue schema")
    records=payload["records"]
    if not records or len(records)!=payload["record_count"]:raise RuntimeError("Manifest count mismatch")
    if len({x["source_path"] for x in records})!=len(records):raise RuntimeError("Nonunique catalogue source")
    if not db_path.is_file():raise RuntimeError("Existing Steward DB is missing")
    connection=sqlite3.connect(str(db_path),timeout=20)
    connection.execute("PRAGMA busy_timeout=20000")
    try:
        for tbl in ("repairs","repair_search","facts"):
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name=?",(tbl,)).fetchone():
                raise RuntimeError("Expected live Steward table missing: "+tbl)
        backup=db_path.with_name("steward.repair-catalogue-v2-"+time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+"-"+uuid.uuid4().hex[:8]+".sqlite")
        if backup.exists():raise RuntimeError("Refusing to replace an existing DB backup")
        dest=sqlite3.connect(str(backup))
        try:connection.backup(dest,pages=256,sleep=.05)
        finally:dest.close()
        os.chmod(backup,0o600)
        before=connection.execute("SELECT count(*) FROM repairs").fetchone()[0]
        fts_before=connection.execute("SELECT count(*) FROM repair_search").fetchone()[0]
        now=time.time()
        connection.execute("BEGIN IMMEDIATE")
        for record in records:
            record=dict(record)
            rid=record["id"]
            fp=sha256((SCHEMA+":"+record["source_path"]+":"+record["source_sha256"]).encode())
            content=json.dumps(record,sort_keys=True)
            search=record["source_path"]+" "+record["how"]
            existing=connection.execute("SELECT successful_runs,failed_runs FROM repairs WHERE id=?",(rid,)).fetchone()
            success,failed=existing if existing else (0,0)
            connection.execute("""INSERT INTO repairs(
                id,fingerprint,title,subsystem,recipe_json,confidence,
                successful_runs,failed_runs,portable,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                fingerprint=excluded.fingerprint,title=excluded.title,
                subsystem=excluded.subsystem,recipe_json=excluded.recipe_json,
                confidence=excluded.confidence,portable=excluded.portable,
                updated_at=excluded.updated_at""",
                (rid,fp,record["title"],record["subsystem"],content,
                 record["confidence"],success,failed,0,now))
            connection.execute("DELETE FROM repair_search WHERE repair_id=?",(rid,))
            connection.execute("""INSERT INTO repair_search
                (repair_id,title,subsystem,problem,symptoms,diagnosis,steps)
                VALUES(?,?,?,?,?,?,?)""",
                (rid,record["title"],record["subsystem"],record["problem"],
                search,record["diagnosis"]," ".join(record["repair_steps"]+
                    record["verification_steps"]+record["rollback_steps"])))
        manifest={
            "schema":SCHEMA,"source_repository":payload["source_repository"],
            "repo_commit":payload["repo_commit"],"record_count":len(records),
            "imported_utc":datetime.now(timezone.utc).isoformat(),
            "source_inspection_only":True,"execution_authority":"none",
            "backup":str(backup)
        }
        connection.execute("""INSERT INTO facts(namespace,key,value_json,updated_at)
            VALUES('repair_catalogue','manifest',?,?)
            ON CONFLICT(namespace,key) DO UPDATE SET value_json=excluded.value_json,
              updated_at=excluded.updated_at""",(json.dumps(manifest,sort_keys=True),now))
        indexed=connection.execute("SELECT count(*) FROM repair_search WHERE repair_id=?",
            (records[0]["id"],)).fetchone()[0]
        if indexed<1:raise RuntimeError("FTS validation failed")
        if connection.execute("SELECT count(*) FROM repair_search").fetchone()[0]<fts_before:
            raise RuntimeError("FTS unexpectedly shrank")
        if connection.execute("SELECT count(*) FROM repairs").fetchone()[0]<before:
            raise RuntimeError("Repair catalogue unexpectedly shrank")
        connection.commit()
        after=connection.execute("SELECT count(*) FROM repairs").fetchone()[0]
        return {"ok":True,"imported":len(records),"repairs_before":before,
                "repairs_after":after,"backup":str(backup),"repo_commit":payload["repo_commit"]}
    except BaseException:
        connection.rollback()
        raise
    finally:connection.close()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path)
    ap.add_argument("--export-json",type=Path)
    ap.add_argument("--import-json",type=Path)
    ap.add_argument("--db",type=Path)
    args=ap.parse_args()
    if args.repo_root and args.export_json:
        payload=build(args.repo_root.resolve())
        export(payload,args.export_json)
        stats={}
        for record in payload["records"]:
            stats[record["evidence"]["purpose_provenance"]]=stats.get(record["evidence"]["purpose_provenance"],0)+1
        print("JNS_REPAIR_CATALOGUE_V2_EXPORT "+json.dumps({
            "records":len(payload["records"]),"purpose_provenance":stats,
            "repo_commit":payload["repo_commit"]},sort_keys=True))
    elif args.import_json and args.db:
        print("JNS_REPAIR_CATALOGUE_V2_IMPORT "+json.dumps(
            import_catalogue(args.import_json.resolve(),args.db.resolve()),sort_keys=True))
    else:ap.error("Specify --repo-root + --export-json OR --import-json + --db")
if __name__=="__main__":main()
