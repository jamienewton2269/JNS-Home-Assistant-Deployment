#!/usr/bin/env python3
"""Read-only identity discovery for KC868 MAC; no IP scans or relay commands."""
import subprocess,shlex,time
MAC="78:1c:3c:ce:82:5b"
def probe(node,script,timeout=25):
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",node,shlex.join(["/bin/sh","-c",script])],capture_output=True,text=True,timeout=timeout)
    print("QUERY",node,"rc",p.returncode,"output",(p.stdout or "")[-6500:],"error",p.stderr[-200:],flush=True)
print("KC868_MAC_IDENTITY_SURVEY",time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),flush=True)
probe("nodeb", "bridge -s fdb show | grep -i '"+MAC+"' || true; ip -4 neigh show | grep -i '"+MAC+"' || true; ip -6 neigh show | grep -i '"+MAC+"' || true; command -v tcpdump || true")
probe("nodea", "bridge -s fdb show | grep -i '"+MAC+"' || true; ip -4 neigh show | grep -i '"+MAC+"' || true; ip -6 neigh show | grep -i '"+MAC+"' || true")
for host,ct in (("nodea",247),("nodeb",248)):
    # Only print lines matching controller identity; do not export general DHCP lease data.
    query="for p in /var/lib/misc/dnsmasq.leases /var/lib/dnsmasq/dnsmasq.leases /run/dnsmasq/dnsmasq.leases /etc/dnsmasq.leases; do if test -r \"$p\"; then echo LEASE_FILE_PRESENT:$p; grep -iE '78:1c:3c:ce:82:5b|alarmpanel|kc868|esphome' \"$p\" | head -20; fi; done"
    probe(host,"pct exec "+str(ct)+" -- /bin/sh -c "+shlex.quote(query))
probe("nodeb","command -v tcpdump >/dev/null && timeout 12 tcpdump -l -nn -e -i vmbr0 -c 12 'ether host "+MAC+"' 2>&1 || true",timeout=22)
print("KC868_MAC_SURVEY_DONE",flush=True)
