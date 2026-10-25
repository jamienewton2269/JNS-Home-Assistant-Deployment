#!/usr/bin/env python3
"""VEYRA OBS v1.3.3: local, authenticated obs-websocket v5 control; stdlib only.

Never connects to a remote machine, changes OBS settings, or handles provider credentials.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import sys
import time
import uuid

PORT = 24593
HOST = "127.0.0.1"
SOURCE = "ITVX XSHM :92"
SCENE = "ITVX Quality"


class Wire:
    def __init__(self, sock, carry=b""):
        self.sock = sock
        self.carry = carry

    def read(self, n):
        while len(self.carry) < n:
            data = self.sock.recv(max(4096, n - len(self.carry)))
            if not data:
                raise RuntimeError("OBS disconnected")
            self.carry += data
        out, self.carry = self.carry[:n], self.carry[n:]
        return out

    def send(self, obj):
        data = json.dumps(obj, separators=(",", ":")).encode()
        mask = os.urandom(4)
        if len(data) < 126:
            hdr = bytes((0x81, 0x80 | len(data)))
        elif len(data) < 65536:
            hdr = bytes((0x81, 0x80 | 126)) + struct.pack("!H", len(data))
        else:
            hdr = bytes((0x81, 0x80 | 127)) + struct.pack("!Q", len(data))
        self.sock.sendall(hdr + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))

    def recv(self):
        while True:
            first, second = self.read(2)
            op = first & 15
            length = second & 127
            if length == 126:
                length = struct.unpack("!H", self.read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self.read(8))[0]
            if length > 1024 * 1024:
                raise RuntimeError("OBS websocket frame too large")
            mask = self.read(4) if second & 128 else None
            payload = self.read(length)
            if mask:
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
            if op == 8:
                raise RuntimeError("OBS websocket closed")
            if op == 9:  # Ping. OBS normally does not send these in a 20-second test.
                raise RuntimeError("unexpected OBS websocket ping")
            if op != 1:
                continue
            return json.loads(payload)


def connect(password):
    s = socket.create_connection((HOST, PORT), timeout=4)
    s.settimeout(7)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET / HTTP/1.1\r\nHost: {HOST}:{PORT}\r\n"
           f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    s.sendall(req.encode())
    raw = b""
    while b"\r\n\r\n" not in raw and len(raw) < 16384:
        data = s.recv(4096)
        if not data:
            raise RuntimeError("websocket handshake failed")
        raw += data
    head, sep, rest = raw.partition(b"\r\n\r\n")
    expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
    if not sep or b" 101 " not in head.splitlines()[0] or expected.lower() not in head.lower():
        raise RuntimeError("websocket handshake refused or invalid")
    w = Wire(s, rest)
    hello = w.recv()
    if hello.get("op") != 0:
        raise RuntimeError("unexpected OBS handshake")
    auth = hello.get("d", {}).get("authentication")
    identify = {"rpcVersion": 1}
    if auth:
        secret = base64.b64encode(hashlib.sha256((password + auth["salt"]).encode()).digest()).decode()
        identify["authentication"] = base64.b64encode(hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode()
    else:
        raise RuntimeError("OBS websocket authentication is not enabled; refusing insecure control")
    w.send({"op": 1, "d": identify})
    identified = w.recv()
    if identified.get("op") != 2:
        raise RuntimeError("OBS websocket authentication failed")
    return w


def request(w, name, data=None):
    req_id = str(uuid.uuid4())
    w.send({"op": 6, "d": {"requestType": name, "requestId": req_id, "requestData": data or {}}})
    for _ in range(20):
        obj = w.recv()
        if obj.get("op") != 7:
            continue
        result = obj.get("d", {})
        if result.get("requestId") != req_id:
            continue
        status = result.get("requestStatus", {})
        if not status.get("result"):
            raise RuntimeError(f"OBS {name} failed: {status.get('code')} {status.get('comment','')}")
        return result.get("responseData", {})
    raise RuntimeError("OBS request response missing")


def verify(w):
    inputs = request(w, "GetInputList").get("inputs", [])
    found = [x for x in inputs if x.get("inputName") == SOURCE]
    if len(found) != 1 or found[0].get("inputKind") != "xshm_input":
        raise RuntimeError(f"XSHM input absent or wrong kind: {found}")
    settings = request(w, "GetInputSettings", {"inputName": SOURCE}).get("inputSettings", {})
    if settings.get("advanced") is not True or settings.get("server") != ":92" or settings.get("screen") != 0:
        raise RuntimeError(f"OBS XSHM settings do not target :92: {settings}")
    audio = [x for x in inputs if x.get("inputName") == "ITVX monitor audio"]
    if len(audio) != 1 or audio[0].get("inputKind") != "pulse_output_capture":
        raise RuntimeError("OBS PulseAudio capture source missing")
    audio_settings = request(w, "GetInputSettings", {"inputName": "ITVX monitor audio"}).get("inputSettings", {})
    if audio_settings.get("device_id") != "veyra_virtual_capture.monitor":
        raise RuntimeError("OBS audio input is not the existing ITVX monitor")
    current = request(w, "GetCurrentProgramScene").get("currentProgramSceneName")
    if current != SCENE:
        raise RuntimeError(f"OBS active scene mismatch: {current}")
    items = request(w, "GetSceneItemList", {"sceneName": SCENE}).get("sceneItems", [])
    video = [x for x in items if x.get("sourceName") == SOURCE and x.get("sceneItemEnabled")]
    if len(video) != 1:
        raise RuntimeError("XSHM source missing or hidden in active scene")
    rec = request(w, "GetRecordStatus")
    if rec.get("outputActive") is not True:
        raise RuntimeError(f"OBS recording did not start: {rec}")
    print("OBS_SOURCE_VERIFIED kind=xshm_input server=:92 screen=0 scene=ITVX_Quality")
    print("OBS_RECORDING_ACTIVE verified")


def stop(w):
    rec = request(w, "GetRecordStatus")
    if not rec.get("outputActive"):
        print("OBS_RECORDING_ALREADY_STOPPED")
        return
    response = request(w, "StopRecord")
    for _ in range(12):
        if not request(w, "GetRecordStatus").get("outputActive"):
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("OBS did not confirm recording stopped")
    path = response.get("outputPath", "")
    print("OBS_RECORD_STOP_CONFIRMED")
    print("OBS_OUTPUT_PATH=" + path)


def stats(w):
    """Read OBS render+encoder frame counters while recording, before StopRecord."""
    d = request(w, "GetStats")
    numeric = ("renderTotalFrames", "renderSkippedFrames",
               "outputTotalFrames", "outputSkippedFrames",
               "activeFps", "averageFrameRenderTime", "cpuUsage", "memoryUsage")
    for k in numeric:
        print(f"OBS_STATS_{k}={d.get(k, 'missing')}")
    total = d.get("renderTotalFrames")
    skipped = d.get("renderSkippedFrames")
    out_total = d.get("outputTotalFrames")
    out_skipped = d.get("outputSkippedFrames")
    if not isinstance(total, (int, float)) or total < 100:
        raise RuntimeError("OBS GetStats insufficient rendered frames")
    if not isinstance(skipped, (int, float)) or skipped < 0:
        raise RuntimeError("OBS GetStats missing rendering-skip data")
    pct = 100.0 * skipped / total
    print(f"OBS_RENDER_LAG_PERCENT={pct:.2f}")
    if isinstance(out_total, (int,float)) and out_total > 0 and isinstance(out_skipped, (int,float)):
        enc_pct = 100 * out_skipped / out_total
        print(f"OBS_ENCODER_LAG_PERCENT={enc_pct:.2f}")
    else:
        enc_pct = None
        print("OBS_ENCODER_LAG_PERCENT=unknown")
    if pct > 5 or (enc_pct is not None and enc_pct > 5):
        raise RuntimeError("OBS real-time render or encoder losses exceed 5%")
    print("OBS_PERFORMANCE_GATE_PASS renderer and encoder losses <=5%")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("verify", "stop", "stats"))
    p.add_argument("--config", required=True)
    a = p.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    if not cfg.get("auth_required") or not cfg.get("server_enabled") or cfg.get("server_port") != PORT:
        raise RuntimeError("Private OBS control is not configured as expected")
    password = cfg.get("server_password")
    if not isinstance(password, str) or len(password) < 24:
        raise RuntimeError("OBS websocket password missing/weak")
    w = connect(password)
    try:
        {"verify": verify, "stop": stop, "stats": stats}[a.action](w)
    finally:
        w.sock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"VEYRA_OBS_CONTROL_FAIL: {exc}", file=sys.stderr)
        sys.exit(2)
