#!/usr/bin/env python3
"""Search Steward's offline repair knowledge without running any repair script."""
import argparse,json,re,sqlite3
from pathlib import Path

DB="/opt/natural-automation/data/steward.db"

def repair_lookup(path, query, limit):
    words=re.findall(r"[\w]+",query)[:12]
    if not words:raise ValueError("Specify repair name, symptom or subsystem")
    # FTS5 query assembled strictly from alphanumeric tokens, no raw user syntax.
    q=" OR ".join('"'+w+'"' for w in words if len(w)>1)
    if not q:raise ValueError("Search too short")
    db=sqlite3.connect("file:"+str(Path(path).resolve())+"?mode=ro",uri=True,timeout=8)
    try:
        rows=db.execute("""SELECT r.recipe_json
           FROM repair_search s JOIN repairs r ON r.id=s.repair_id
           WHERE repair_search MATCH ?
           ORDER BY bm25(repair_search),r.confidence DESC
           LIMIT ?""",(q,min(max(int(limit),1),20))).fetchall()
        result=[]
        for (raw,) in rows:
            v=json.loads(raw)
            ev=v.get("evidence") or {}
            entry={
                "title":v.get("title"),"subsystem":v.get("subsystem"),
                "source_path":v.get("source_path"),
                "source_sha256":v.get("source_sha256"),
                "why":v.get("why") or v.get("problem"),
                "why_evidence":ev.get("purpose_provenance") or "legacy_unverified",
                "how":v.get("how") or v.get("repair_steps") or [],
                "workflow_references":ev.get("workflow_references",[]),
                "verified_execution":ev.get("execution_result","not_recorded"),
                "verification_guidance":v.get("verification_steps",[]),
                "rollback_guidance":v.get("rollback_steps",[]),
                "confidence":v.get("confidence",0.5),
                "safety_class":v.get("safety_class","unknown"),
                "needs_human_review":True,
                "never_auto_execute":True,
            }
            result.append(entry)
        return {"query":query,"count":len(result),"results":result,
                "execution_authority":"none","offline":True}
    finally:db.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("query",help="repair subsystem or problem")
    p.add_argument("--db",default=DB)
    p.add_argument("--limit",type=int,default=5)
    a=p.parse_args()
    print(json.dumps(repair_lookup(a.db,a.query,a.limit),sort_keys=True))
if __name__=="__main__":main()
