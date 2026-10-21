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
