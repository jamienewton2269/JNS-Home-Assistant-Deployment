#!/usr/bin/env python3
"""Read-only Node B HA Steward historical repair coverage; never prints source or secrets."""
import json,subprocess,sys
from pathlib import Path
src=Path("/opt/natural-automation/data/steward.db")
assert src.exists(), "Steward SQLite missing"
import sqlite3
db=sqlite3.connect("file:"+str(src)+"?mode=ro",uri=True,timeout=8)
print("JNS_STEWARD_DB_REPAIRS",db.execute("SELECT count(*) FROM repairs").fetchone()[0])
for table in ("facts","observations","repair_search"):
 try:print("JNS_STEWARD_DB_"+table.upper(),db.execute("SELECT count(*) FROM "+table).fetchone()[0])
 except sqlite3.OperationalError:print("JNS_STEWARD_DB_"+table.upper(),"absent")
rows=db.execute("SELECT recipe_json,successful_runs,failed_runs FROM repairs").fetchall()
sources={};classify={};problems=0;diagnoses=0;verified=0
for raw,success,fail in rows:
 item=json.loads(raw)
 key=(item.get("source_path") or "nonrepository").split("/")[0]
 sources[key]=sources.get(key,0)+1
 cls=item.get("safety_class","unspecified");classify[cls]=classify.get(cls,0)+1
 if item.get("problem") and item["problem"]!="Historical online repair/test procedure retained for offline reference.":problems+=1
 if item.get("diagnosis"):diagnoses+=1
 if success or fail:verified+=1
print("JNS_STEWARD_DB_SOURCE_FAMILIES",json.dumps(sources,sort_keys=True))
print("JNS_STEWARD_DB_SAFETY_CLASSES",json.dumps(classify,sort_keys=True))
print("JNS_STEWARD_DB_SPECIFIC_PURPOSE",problems)
print("JNS_STEWARD_DB_DIAGNOSIS",diagnoses)
print("JNS_STEWARD_DB_RECORDED_RUNS",verified)
print("JNS_STEWARD_DB_HISTORICAL_PATHS",json.dumps(sorted(item.get("source_path") for (raw,s,f) in rows if (item:=json.loads(raw)).get("source_path"))[:60]))
print("JNS_STEWARD_DB_RO_COMPLETE")
