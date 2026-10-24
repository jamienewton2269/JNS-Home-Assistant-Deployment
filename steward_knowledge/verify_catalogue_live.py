#!/usr/bin/env python3
"""Read-only verification of committed repair catalogue in on-site Steward SQLite."""
import json,sqlite3,sys
from pathlib import Path
if len(sys.argv)!=3:raise SystemExit("expected commit and minimum records")
commit,min_count=sys.argv[1],int(sys.argv[2])
db=sqlite3.connect("file:/opt/natural-automation/data/steward.db?mode=ro",uri=True)
row=db.execute("SELECT value_json FROM facts WHERE namespace=? AND key=?",
 ("repair_catalogue","manifest")).fetchone()
assert row is not None,"missing catalogue manifest"
manifest=json.loads(row[0])
assert manifest["repo_commit"]==commit
count=manifest["record_count"]
assert count>=min_count>=100
assert manifest["source_inspection_only"] and manifest["execution_authority"]=="none"
total=db.execute("SELECT count(*) FROM repairs").fetchone()[0]
fts=db.execute("SELECT count(*) FROM repair_search").fetchone()[0]
assert total>=count+17,(total,count)
assert fts>=count,(fts,count)
old_id="f8"
legacy=db.execute("SELECT count(*) FROM repairs WHERE recipe_json LIKE '%Historical online repair/test procedure retained%'").fetchone()[0]
assert legacy>=17,legacy
fact=db.execute("SELECT count(*) FROM facts").fetchone()[0]
assert fact>=6,fact
print("JNS_STEWARD_LIVE_CATALOGUE_VERIFIED "+json.dumps({
 "repo_commit":commit,"indexed":count,"repair_total":total,
 "fts_rows":fts,"historical_repair_records_preserved":legacy,
 "facts":fact},sort_keys=True),flush=True)
