"""Offline, metadata-only analysis of the existing gateway index.

No network access, command execution, or publication of raw job output.
"""
import argparse
import collections
import json
from pathlib import Path

FIELDS = ("job_id", "state", "exit_code", "started", "finished")

def summarize(index_text):
    counts = collections.Counter()
    exits = collections.Counter()
    seen = set()
    duplicates = 0
    invalid = 0
    for line in index_text.splitlines():
        # Existing historical index has used both literal backslash-t and tabs.
        parts = line.replace("\\t", "\t").split("\t")
        if tuple(parts) == FIELDS or not line.strip():
            continue
        if len(parts) != 5 or not parts[0] or parts[1] not in ("done", "failed", "running", "queued"):
            invalid += 1
            continue
        job_id, state, exit_code, _, _ = parts
        if job_id in seen:
            duplicates += 1
            continue
        seen.add(job_id)
        counts[state] += 1
        if state == "failed":
            exits[exit_code] += 1
    return {
        "total_unique_jobs": len(seen),
        "states": dict(sorted(counts.items())),
        "failed_exit_codes": dict(sorted(exits.items())),
        "duplicate_job_ids": duplicates,
        "invalid_rows": invalid,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.index.read_text(encoding="utf-8")), sort_keys=True))

if __name__ == "__main__":
    main()
