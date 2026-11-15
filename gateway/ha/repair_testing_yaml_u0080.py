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

    try:
        original = source.decode("utf-8")
    except UnicodeDecodeError as ex:
        if source[ex.start:ex.end] != b"\x80" or source.count(b"\x80") != 1:
            raise RuntimeError("Unexpected invalid encoding; refusing automatic repair") from ex
        repaired = source.replace(b"\x80", b"", 1)
        repaired_text = repaired.decode("utf-8")
        removed = 1
    else:
        removed = original.count("\u0080")
        positions = [i for i, char in enumerate(original) if ord(char) == 128]
        print("U+0080 count:", removed, "character positions:", positions[:50])
        repaired_text = original.replace("\u0080", "")
        repaired = repaired_text.encode("utf-8")
        if removed > 4:
            from collections import Counter
            illegal = [(i, ord(char)) for i, char in enumerate(original)
                       if ((ord(char) < 32 and char not in ("\\t", "\\n", "\\r"))
                           or (0x7f <= ord(char) < 0xa0 and ord(char) != 0x85))]
            totals = Counter(hex(code) for _pos, code in illegal)
            print("AUDIT invalid Unicode codepoint counts:", dict(totals))
            print("AUDIT invalid character positions:", illegal[:85])
            clean = "".join(char for char in original if
                            ((ord(char) >= 32 and not 0x7f <= ord(char) < 0xa0)
                             or char in ("\\t", "\\n", "\\r", "\\u0085")))
            try:
                docs = list(yaml.compose_all(clean))
                print("AUDIT: all invalid controls stripped -> parses, docs:", len(docs),
                      "characters_removed:", len(original)-len(clean))
            except yaml.YAMLError as exc:
                print("AUDIT: still invalid after control stripping:",
                      type(exc).__name__, str(exc)[:200])
            raise RuntimeError("Safety limit exceeded; diagnosis only, no changes")

    if removed == 0:
        yaml.compose(repaired_text)
        print("No U+0080 found; dashboard YAML already valid. Nothing changed.")
        return
    if removed > 4:
        raise RuntimeError("Refusing bulk change")
    if len(repaired) >= len(source):
        raise RuntimeError("No targeted bytes removed")
    yaml.compose(repaired_text)
    print("Removed invalid control character(s):", removed,
          "; YAML structure parsed successfully")
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
