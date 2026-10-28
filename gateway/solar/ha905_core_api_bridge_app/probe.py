#!/usr/bin/env python3
"""One-shot Core-API read-only probe. Intended only for a manual-only HAOS app.

The app has admin-capable homeassistant_api permission at the Supervisor proxy.
It deliberately executes only fixed GETs, never touches credentials, HA config,
device states, config flows or registries, and does not print HTTP bodies.
"""
import json
import os
import urllib.error
import urllib.request

ROOT = "http://supervisor/core/api/"
ENDPOINTS = {"core_root": ROOT, "core_config": ROOT + "config"}


def get_status(url, token, opener=urllib.request.urlopen):
    if url not in ENDPOINTS.values():
        raise ValueError("unapproved_endpoint")
    if not token:
        return "no_app_token"
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token}, method="GET"
    )
    try:
        with opener(req, timeout=8) as response:
            # Never consume or log the response body.
            return response.status
    except urllib.error.HTTPError as err:
        return err.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return "unavailable"


def run(token, opener=urllib.request.urlopen):
    return {name: get_status(url, token, opener) for name, url in ENDPOINTS.items()}


def main():
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    result = run(token)
    print("JNS_HA905_TRUSTED_APP_CORE_PREFLIGHT=" + json.dumps({
        "core_root_http": result["core_root"],
        "core_config_http": result["core_config"],
        "read_only": True, "flows_created": False,
        "esphome_enrolled": False, "token_logged": False,
        "production_config_changed": False,
    }, sort_keys=True), flush=True)
    return 0 if result["core_root"] == 200 and result["core_config"] == 200 else 2


if __name__ == "__main__":
    raise SystemExit(main())
