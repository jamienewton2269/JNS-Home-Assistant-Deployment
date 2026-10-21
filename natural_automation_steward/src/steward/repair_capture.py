import hashlib
import json
import uuid


def fingerprint(recipe):
    core = {
        k: recipe.get(k)
        for k in (
            "title",
            "subsystem",
            "problem",
            "diagnosis",
            "repair_steps",
            "verification_steps",
            "rollback_steps",
            "applicability",
            "source_path",
            "source_sha256",
        )
    }
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def capture(store, recipe, success=True):
    r = dict(recipe)
    rid = r.setdefault("id", uuid.uuid4().hex)
    fp = fingerprint(r)
    return store.upsert_repair(
        repair_id=rid,
        fingerprint=fp,
        recipe=r,
        successful_runs=1 if success else 0,
        failed_runs=0 if success else 1,
    )
