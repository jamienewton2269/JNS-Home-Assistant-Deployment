#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 18765
TOKEN = "a" * 64


def request(path: str, *, token: str | None = None, payload: dict | None = None):
    headers = {}
    data = None
    method = "GET"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cfg = td / "config.json"
        tok = td / "token"
        cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "listen_port": PORT,
            "command_timeout": 5,
            "max_output_bytes": 10000,
            "targets": {"local": {"mode": "local"}},
        }), encoding="utf-8")
        tok.write_text(TOKEN, encoding="utf-8")

        env = dict(os.environ)
        env["JNS_BRIDGE_CONFIG"] = str(cfg)
        env["JNS_BRIDGE_TOKEN_FILE"] = str(tok)

        proc = subprocess.Popen(
            [sys.executable, str(HERE / "server.py")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            for _ in range(40):
                try:
                    status, body = request("/health")
                    if status == 200 and body.get("ok") is True:
                        break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError("bridge did not become healthy")

            try:
                request("/api/targets")
                raise RuntimeError("unauthenticated request unexpectedly succeeded")
            except urllib.error.HTTPError as exc:
                if exc.code != 401:
                    raise

            status, body = request("/api/targets", token=TOKEN)
            assert status == 200
            assert body["targets"] == ["local"]

            status, body = request(
                "/api/run",
                token=TOKEN,
                payload={"target": "local", "command": "printf bridge-ok"},
            )
            assert status == 200
            assert body["exit_code"] == 0
            assert body["stdout"] == "bridge-ok"

            print("management bridge self-test: PASS")
            return 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
