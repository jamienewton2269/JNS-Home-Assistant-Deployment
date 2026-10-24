#!/usr/bin/env python3
"""Drive standard Home Assistant integration configuration flows from a private plan.

One-time onboarding may use Tuya cloud-assisted key retrieval inside the existing
tuya_local integration. The completed local integration has no polling dependency
on Tuya cloud. Credential/flow inputs stay on the operator's machine.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class OnboardError(Exception):
    pass


def submit(base_url, token, route, payload):
    base = base_url.rstrip("/")
    if urlsplit(base).scheme not in ("http", "https"):
        raise OnboardError("HA URL must be http(s)")
    request = urllib.request.Request(
        base + "/api/" + route.lstrip("/"),
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise OnboardError("HA API rejected config flow: HTTP " + str(exc.code)) from None


def run(base_url, token, config, apply):
    if not apply:
        raise OnboardError("Read-only by default; add --apply --confirm ONBOARD")
    if config.get("handler") not in ("tuya_local", "localtuya"):
        raise OnboardError("Unsupported handler; install Tuya Local via HACS first")
    if not isinstance(config.get("devices"), list) or not config["devices"]:
        raise OnboardError("No device flow steps in the private manifest")
    for num, device in enumerate(config["devices"], 1):
        steps = device.get("steps")
        if not isinstance(steps, list) or not steps:
            raise OnboardError("Each device requires explicit form responses")
        res = submit(base_url, token, "config/config_entries/flow",
                     {"handler": config["handler"]})
        for step in steps:
            if res.get("type") != "form" or not isinstance(step, dict):
                raise OnboardError("Integration returned a non-form step before plan completion")
            fid = res.get("flow_id")
            if not fid:
                raise OnboardError("Integration supplied no flow identifier")
            res = submit(base_url, token, "config/config_entries/flow/" + fid,
                         {"user_input": step})
            # Deliberately do not print step results which might reflect secrets.
            if res.get("errors"):
                raise OnboardError("Device " + str(num) + " rejected a form response")
        if res.get("type") != "create_entry":
            raise OnboardError("Device " + str(num) +
                               " requires an additional config form; nothing was claimed complete")
        print("ONBOARDED_LOCAL_CONFIG_ENTRY", num)
    print("LOCAL_ONBOARDING_COMPLETE; cloud entries and device WAN access unchanged")


def main():
    ap = argparse.ArgumentParser(description="Guarded HA config-flow onboarding")
    ap.add_argument("--url", default="http://homeassistant.local:8123")
    ap.add_argument("--token-env", default="HA_TOKEN")
    ap.add_argument("--steps-file", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()
    if not args.apply or args.confirm != "ONBOARD":
        raise OnboardError("--apply --confirm ONBOARD required")
    p = Path(args.steps_file).expanduser()
    if p.is_symlink() or not p.is_file():
        raise OnboardError("Manifest must be a regular private local file")
    if stat.S_IMODE(p.stat().st_mode) & 0o077:
        raise OnboardError("Manifest contains sensitive data; chmod 600 the file")
    token = os.environ.get(args.token_env, "")
    if not token:
        raise OnboardError("Missing admin token in named environment variable")
    with p.open(encoding="utf-8") as f:
        config = json.load(f)
    run(args.url, token, config, True)


if __name__ == "__main__":
    try:
        main()
    except (OnboardError, OSError, ValueError) as exc:
        print("BLOCKED", type(exc).__name__, str(exc), file=sys.stderr)
        raise SystemExit(2)
