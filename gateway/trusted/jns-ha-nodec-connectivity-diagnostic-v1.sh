#!/usr/bin/env bash
set -u
echo "JNS HA902/HA905 connectivity diagnostics - $(date -Is)"
echo "Node C: $(hostname)"; echo
for ip in 10.10.10.220 10.10.10.223; do
 echo "=== $ip ==="
 ip route get "$ip" 2>&1
 ping -c 1 -W 2 "$ip" 2>&1 | tail -3
 for port in 8123 4357 22; do
  if timeout 3 bash -c 'exec 3<>/dev/tcp/"$1"/"$2"' bash "$ip" "$port" 2>/dev/null; then echo "TCP $port open"; else echo "TCP $port closed/unreachable"; fi
 done
 curl -sS --connect-timeout 3 --max-time 7 -o /dev/null -w 'HTTP 8123 status=%{http_code} remote=%{remote_ip} reason=%{errormsg}\n' "http://$ip:8123/" 2>&1 || :
 curl -ksS --connect-timeout 3 --max-time 7 -o /dev/null -w 'HTTPS 8123 status=%{http_code} reason=%{errormsg}\n' "https://$ip:8123/" 2>&1 || :
 echo
done
echo "=== Node B SSH reachability (read-only) ==="
for host in nodeb 10.10.10.235; do
 echo "Checking $host"
 timeout 8 ssh -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=yes root@"$host" 'hostname; qm status 902; qm status 905' 2>&1 || :
done
echo "No services or VMs were changed."
