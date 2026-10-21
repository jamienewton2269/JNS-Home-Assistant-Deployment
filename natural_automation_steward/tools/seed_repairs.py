from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve()
SRC = HERE.parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from steward.repair_capture import fingerprint
from steward.store import StewardStore


PATTERNS = (
    "management_bridge/jns-zigbee-*.sh",
    "management_bridge/jns_zigbee_phone_tester.py",
    "ha_testing_dashboard/apply*.py",
    "ha_testing_dashboard/audit*.sh",
    "ha_testing_dashboard/deploy*.sh",
    "gateway/trusted/ha-*.sh",
    "gateway/trusted/*tuya*.sh",
    "gateway/trusted/*zigbee*.sh",
    "tools/*selftest*.py",
)

SKIP_PARTS = {
    "__pycache__",
    ".git",
}


def subsystem_for(path: Path) -> str:
    name = path.name.lower()
    if "zigbee" in name:
        return "zigbee"
    if "tuya" in name:
        return "tuya"
    if "dns" in name:
        return "dns"
    if "audio" in name or "chime" in name:
        return "audio"
    if "lux" in name or "light" in name:
        return "lighting"
    if "network" in name or "dhcp" in name:
        return "network"
    if "config" in name:
        return "home_assistant_config"
    return "home_assistant"


def title_for(path: Path) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(word.capitalize() for word in stem.split())


def candidate_paths(repo_root: Path) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in PATTERNS:
        for path in repo_root.glob(pattern):
            if not path.is_file():
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            rel = path.relative_to(repo_root).as_posix()
            found[rel] = path
    return [found[k] for k in sorted(found)]


def build_record(repo_root: Path, path: Path) -> dict:
    content = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(repo_root).as_posix()
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    subsystem = subsystem_for(path)
    return {
        "id": uuid.uuid5(uuid.NAMESPACE_URL, f"jns-repair:{rel}:{sha}").hex,
        "title": title_for(path),
        "subsystem": subsystem,
        "problem": "Historical online repair/test procedure retained for offline reference.",
        "symptoms": [],
        "diagnosis": "",
        "preconditions": [
            "Review applicability against the current node before use.",
            "Resolve current entities, hardware identities and service names before execution.",
        ],
        "repair_steps": [],
        "verification_steps": [
            "Run the procedure's own validation/test steps where present.",
            "Verify Home Assistant and the affected subsystem after any proposed change.",
        ],
        "rollback_steps": [
            "Use the current JNS transactional backup/rollback path before applying changes.",
        ],
        "applicability": {
            "source_family": rel.split("/", 1)[0],
            "subsystem": subsystem,
        },
        "exclusions": [
            "Imported historical knowledge is advisory only.",
            "Do not execute automatically from this record.",
        ],
        "confidence": 0.5,
        "portable": False,
        "safety_class": "manual_review",
        "source_path": rel,
        "source_sha256": sha,
        "artifact": {
            "kind": path.suffix.lstrip(".") or "text",
            "content": content,
        },
    }


def export_seed(repo_root: Path, output: Path) -> int:
    records = [build_record(repo_root, p) for p in candidate_paths(repo_root)]
    payload = {
        "schema": "steward-repair-seed-v1",
        "generated_from": str(repo_root),
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return len(records)


def import_seed(db_path: Path, seed_path: Path) -> int:
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "steward-repair-seed-v1":
        raise ValueError("Unsupported repair seed schema")
    store = StewardStore(db_path)
    count = 0
    for raw in payload.get("records", []):
        recipe = dict(raw)
        recipe["safety_class"] = "manual_review"
        recipe["portable"] = False
        rid = str(recipe.get("id") or uuid.uuid4().hex)
        fp = fingerprint(recipe)
        store.upsert_repair(
            repair_id=rid,
            fingerprint=fp,
            recipe=recipe,
            successful_runs=0,
            failed_runs=0,
        )
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--export-json", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--import-json", type=Path)
    args = parser.parse_args()

    if args.repo_root and args.export_json:
        count = export_seed(args.repo_root.resolve(), args.export_json.resolve())
        print(f"exported={count}")
        return 0
    if args.db and args.import_json:
        count = import_seed(args.db.resolve(), args.import_json.resolve())
        print(f"imported={count}")
        return 0

    parser.error("use --repo-root + --export-json or --db + --import-json")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
