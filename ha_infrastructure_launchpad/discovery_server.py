#!/usr/bin/env python3
import concurrent.futures
import html
import http.client
import ipaddress
import json
import os
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BIND_HOST = os.environ.get("JNS_DISCOVERY_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("JNS_DISCOVERY_PORT", "8765"))
NETWORK = ipaddress.ip_network(os.environ.get("JNS_DISCOVERY_NETWORK", "10.10.10.0/24"))
STATE_FILE = Path(os.environ.get("JNS_DISCOVERY_STATE", "/var/lib/jns-infrastructure-discovery/servers.json"))
MAX_WORKERS = int(os.environ.get("JNS_DISCOVERY_WORKERS", "128"))
CONNECT_TIMEOUT = float(os.environ.get("JNS_DISCOVERY_CONNECT_TIMEOUT", "0.22"))
HTTP_TIMEOUT = float(os.environ.get("JNS_DISCOVERY_HTTP_TIMEOUT", "1.4"))
MIN_SCAN_INTERVAL = float(os.environ.get("JNS_DISCOVERY_MIN_INTERVAL", "5"))

# Ports useful for identifying infrastructure and web-management surfaces.
SCAN_PORTS = (
    22, 53, 80, 443, 1883, 1884, 3000, 6638, 8000, 8006,
    8080, 8081, 8088, 8123, 8443, 8888, 9000, 9090, 9443,
)
WEB_PORTS = {80, 443, 3000, 8000, 8006, 8080, 8081, 8088, 8123, 8443, 8888, 9000, 9090, 9443}
HTTPS_PORTS = {443, 8006, 8443, 9443}
PORT_LABELS = {
    22: "SSH", 53: "DNS", 80: "HTTP", 443: "HTTPS",
    1883: "MQTT", 1884: "MQTT", 3000: "Web",
    6638: "Zigbee serial bridge", 8000: "Web", 8006: "Proxmox",
    8080: "Web", 8081: "Web", 8088: "Web", 8123: "Home Assistant",
    8443: "HTTPS", 8888: "Web", 9000: "Web", 9090: "Web", 9443: "HTTPS",
}
SERVICE_HINTS = {
    8006: ("compute", "Proxmox"),
    8123: ("ha", "Home Assistant"),
    1883: ("zigbee", "MQTT"),
    1884: ("zigbee", "MQTT"),
    6638: ("zigbee", "Zigbee serial bridge"),
    53: ("dns", "DNS"),
}

state_lock = threading.Lock()
scan_lock = threading.Lock()
last_scan_started = 0.0

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def is_private_client(addr):
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False

def probe_port(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(CONNECT_TIMEOUT)
    try:
        return ip, port, s.connect_ex((ip, port)) == 0
    except OSError:
        return ip, port, False
    finally:
        s.close()

def reverse_name(ip):
    try:
        return socket.gethostbyaddr(ip)[0].rstrip(".")
    except Exception:
        return None

def fetch_web(ip, port):
    scheme = "https" if port in HTTPS_PORTS else "http"
    conn = None
    try:
        if scheme == "https":
            ctx = ssl._create_unverified_context()
            conn = http.client.HTTPSConnection(ip, port, timeout=HTTP_TIMEOUT, context=ctx)
        else:
            conn = http.client.HTTPConnection(ip, port, timeout=HTTP_TIMEOUT)
        conn.request("GET", "/", headers={"User-Agent": "JNS-Infrastructure-Discovery/1.0", "Connection": "close"})
        resp = conn.getresponse()
        raw = resp.read(65536)
        text = raw.decode("utf-8", errors="ignore")
        lower = text.lower()
        title = None
        start = lower.find("<title")
        if start >= 0:
            start = lower.find(">", start)
            end = lower.find("</title>", start + 1)
            if start >= 0 and end > start:
                title = html.unescape(" ".join(text[start + 1:end].split()))[:120]
        return {
            "scheme": scheme,
            "url": f"{scheme}://{ip}:{port}" if port not in (80, 443) else f"{scheme}://{ip}",
            "http_status": resp.status,
            "server": (resp.getheader("Server") or "")[:120] or None,
            "title": title,
        }
    except Exception:
        return {
            "scheme": scheme,
            "url": f"{scheme}://{ip}:{port}" if port not in (80, 443) else f"{scheme}://{ip}",
            "http_status": None,
            "server": None,
            "title": None,
        }
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def classify_host(open_ports):
    for p in open_ports:
        if p in SERVICE_HINTS:
            return SERVICE_HINTS[p]
    if any(p in WEB_PORTS for p in open_ports):
        return ("discovered", "Web-managed host")
    return ("discovered", "LAN host")

def scan_network():
    global last_scan_started
    started_monotonic = time.monotonic()
    last_scan_started = started_monotonic
    started_at = utc_now()

    hosts = [str(ip) for ip in NETWORK.hosts()]
    open_by_host = {ip: [] for ip in hosts}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(probe_port, ip, port) for ip in hosts for port in SCAN_PORTS]
        for fut in concurrent.futures.as_completed(futures):
            ip, port, is_open = fut.result()
            if is_open:
                open_by_host[ip].append(port)

    discovered_ips = [ip for ip, ports in open_by_host.items() if ports]
    names = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(32, max(1, len(discovered_ips)))) as pool:
        future_map = {pool.submit(reverse_name, ip): ip for ip in discovered_ips}
        for fut in concurrent.futures.as_completed(future_map):
            ip = future_map[fut]
            try:
                names[ip] = fut.result()
            except Exception:
                names[ip] = None

    result_hosts = []
    for ip in sorted(discovered_ips, key=lambda x: ipaddress.ip_address(x)):
        ports = sorted(open_by_host[ip])
        group, role = classify_host(ports)
        services = []
        for port in ports:
            service = {
                "port": port,
                "label": PORT_LABELS.get(port, f"TCP {port}"),
                "web": port in WEB_PORTS,
            }
            if port in WEB_PORTS:
                service.update(fetch_web(ip, port))
            services.append(service)
        result_hosts.append({
            "ip": ip,
            "hostname": names.get(ip),
            "group": group,
            "role": role,
            "open_ports": ports,
            "services": services,
        })

    finished_at = utc_now()
    payload = {
        "schema": 1,
        "network": str(NETWORK),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        "host_count": len(result_hosts),
        "hosts": result_hosts,
    }

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)
    return payload

def read_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema": 1,
            "network": str(NETWORK),
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "host_count": 0,
            "hosts": [],
        }

class Handler(BaseHTTPRequestHandler):
    server_version = "JNSDiscovery/1.0"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def _json(self, code, obj):
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "jns-infrastructure-discovery", "network": str(NETWORK)})
            return
        if self.path in ("/", "/api/state"):
            self._json(200, read_state())
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path != "/api/scan":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        if not is_private_client(self.client_address[0]):
            self._json(403, {"ok": False, "error": "private_network_only"})
            return

        global last_scan_started
        now = time.monotonic()
        if scan_lock.locked():
            self._json(409, {"ok": False, "error": "scan_already_running"})
            return
        if last_scan_started and now - last_scan_started < MIN_SCAN_INTERVAL:
            self._json(429, {"ok": False, "error": "scan_rate_limited"})
            return

        with scan_lock:
            try:
                self._json(200, scan_network())
            except Exception as exc:
                self._json(500, {"ok": False, "error": "scan_failed", "detail": str(exc)[:200]})

def main():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print(f"JNS infrastructure discovery listening on {BIND_HOST}:{BIND_PORT}, scanning {NETWORK}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
