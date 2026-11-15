#!/usr/bin/env python3
"""Repair only the U+0080 character in HA-General Testing dashboard.

Runs on Node C via a restricted GitHub Actions workflow. Does not modify
automations, other dashboard files, services, or Home Assistant Core.
"""
import base64
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone

import yaml

TARGET = "/mnt/data/supervisor/homeassistant/dashboards/testing.yaml"
NODE = "root@nodeb.home.arpa"
VMID = "905"


def remote(*argv, stdin=None):
    command = "qm guest exec " + VMID
    if stdin is not None:
        command += " --pass-stdin 1"
    command += " -- " + " ".join(shlex.quote(a) for a in argv)
    proc = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
         NODE, command],
        input=stdin, capture_output=True, text=True, timeout=60, check=False
    )
    if proc.returncode:
        raise RuntimeError("SSH/guest-agent transport failed (no file replaced)")
    item = json.loads(proc.stdout)
    if not item.get("exited") or item.get("out-truncated"):
        raise RuntimeError("Guest process did not finish or its output truncated")
    if item.get("exitcode") != 0:
        raise RuntimeError("Guest command returned failure (no diagnostic payload printed)")
    return item.get("out-data", "")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = base64.b64decode(remote("/bin/sh", "-c",
                                    "base64 " + shlex.quote(TARGET)))
    original_sha = digest(source)
    print("Testing dashboard bytes:", len(source))
    print("Original SHA256 prefix:", original_sha[:12])

    # Repair is permitted only for the inspected, unchanged file.
    if not original_sha.startswith("e0ab9171911c"):
        raise RuntimeError("Live YAML checksum changed since audit; refusing replacement")
    try:
        original = source.decode("utf-8")
    except UnicodeDecodeError as ex:
        raise RuntimeError("Unexpected UTF-8 corruption; no changes") from ex

    # The audit found 51 isolated C1 controls, in five known codepoints.
    # Keep every other byte and every valid Unicode character unchanged.
    invalid_codes = {0x80, 0x94, 0x97, 0x9A, 0x9F}
    matches = [(index, ord(char)) for index, char in enumerate(original)
               if ord(char) in invalid_codes]
    other_invalid = [(index, ord(char)) for index, char in enumerate(original)
                     if ((ord(char) < 32 and char not in ("\t", "\n", "\r"))
                         or (0x7f <= ord(char) < 0xa0 and ord(char) != 0x85))
                     and ord(char) not in invalid_codes]
    if other_invalid or len(matches) != 51:
        raise RuntimeError("Control characters differ from audit; no changes")
    repaired_text = "".join(char for char in original
                            if ord(char) not in invalid_codes)
    repaired = repaired_text.encode("utf-8")
    documents = list(yaml.compose_all(repaired_text))
    if len(documents) != 1 or "views:" not in repaired_text:
        raise RuntimeError("Expected Testing dashboard structure not found")
    removed = len(matches)
    if len(repaired) >= len(source):
        raise RuntimeError("No targeted characters removed")
    print("Removed exactly 51 audited invalid C1 codepoints; YAML parses.")
    print("All valid Unicode and dashboard configuration retained.")
    stage = TARGET + ".u0080-repair-stage"
    backup = TARGET + ".pre-u0080-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".bak"

    remote("/bin/sh", "-c", "base64 -d > " + shlex.quote(stage),
           stdin=base64.b64encode(repaired).decode("ascii") + "\n")
    if remote("/usr/bin/sha256sum", stage).split()[0] != digest(repaired):
        raise RuntimeError("Staged checksum mismatch; live file not replaced")
    if remote("/usr/bin/sha256sum", TARGET).split()[0] != original_sha:
        raise RuntimeError("Live file changed during repair; refusing replacement")
    mode = remote("/bin/stat", "-c", "%a", TARGET).strip()
    owner = remote("/bin/stat", "-c", "%u:%g", TARGET).strip()
    if not mode.isdigit() or len(owner.split(":")) != 2 or not all(
        item.isdigit() for item in owner.split(":")
    ):
        raise RuntimeError("Unable to preserve file ownership/mode")
    command = ("cp -p " + shlex.quote(TARGET) + " " + shlex.quote(backup)
               + " && chmod " + shlex.quote(mode) + " " + shlex.quote(stage)
               + " && chown " + shlex.quote(owner) + " " + shlex.quote(stage)
               + " && mv " + shlex.quote(stage) + " " + shlex.quote(TARGET))
    remote("/bin/sh", "-c", command)
    if remote("/usr/bin/sha256sum", TARGET).split()[0] != digest(repaired):
        raise RuntimeError("Post-replacement checksum verification failed")
    print("REPAIR SUCCESS: YAML validated, backup preserved, target replaced.")
    print("Repaired SHA256 prefix:", digest(repaired)[:12])
    print("Home Assistant Core restart was NOT requested.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("REPAIR FAILED:", type(exc).__name__, str(exc)[:210], file=sys.stderr)
        sys.exit(1)
