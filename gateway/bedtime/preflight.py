#!/usr/bin/env python3
"""Read-only Node C -> Node B -> HA905 bedtime preflight."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
def guest(args):
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
 for _ in range(45):
  if r.get("exited"):return r
  if not isinstance(r.get("pid"),int):raise RuntimeError("No guest PID")
  time.sleep(2)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
 raise RuntimeError("Guest timeout")
src="""import pathlib,hashlib,json,yaml
p=pathlib.Path('/config/packages/jns_bedtime_controller.yaml')
d=yaml.safe_load(p.read_text())
assert 'jns_bedtime_shutdown' in d['script']
assert any(a.get('id')=='jns_bedtime_clear_scene_at_sunrise' for a in d['automation'])
es=json.loads(pathlib.Path('/config/.storage/core.entity_registry').read_text())['data']['entities']
assert len([e for e in es if e.get('entity_id')=='switch.0xa4c1388ba234f2e3' and not e.get('disabled_by')])==1
print('PREFLIGHT_OK',hashlib.sha256(p.read_bytes()).hexdigest())
"""
print("JNS_BEDTIME_READONLY_PREFLIGHT",flush=True)
print("VM905",ssh_host("nodeb",["qm","status","905"]).strip(),flush=True)
r=guest(["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode("+repr(base64.b64encode(src.encode()).decode())+"))"])
print("PACKAGE",r.get("exitcode"),(r.get("out-data") or "")[-450:],(r.get("err-data") or "")[-250:],flush=True)
if r.get("exitcode")!=0:raise SystemExit(2)
test='if [ -z "$SUPERVISOR_TOKEN" ]; then echo TOKEN_ABSENT; exit 3;fi; code=$(curl -sS -o /dev/null --max-time 9 -w "%{http_code}" -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/) || code=transport_error; echo "CORE_API_STATUS $code"; test "$code" = 200'
for c in ("app_core_ssh","hassio_cli"):
 try:
  r=guest(["docker","exec",c,"sh","-c",test])
  print("AUTH",c,r.get("exitcode"),(r.get("out-data") or "")[-250:],(r.get("err-data") or "")[-100:],flush=True)
 except Exception as e:print("AUTH_BLOCKED",c,type(e).__name__,flush=True)

print("JNS_Z2M_MQTT_DIAGNOSTIC",flush=True)
for container,cmd in [
 ("214","printf 'Z2M_ROOT ';systemctl show zigbee2mqtt -p WorkingDirectory --value;printf 'NODE ';command -v node || :; printf 'DATA ';for p in /opt/zigbee2mqtt/data/configuration.yaml /app/data/configuration.yaml /var/lib/zigbee2mqtt/configuration.yaml; do if test -f \"$p\"; then echo \"$p\";fi; done; printf 'MQTT_CLI '; command -v mosquitto_pub || :"),
 ("212","printf 'MQTT_PUB ';command -v mosquitto_pub || :;printf 'MQTT_SUB ';command -v mosquitto_sub || :;printf 'MOSQUITTO ';systemctl is-active mosquitto || :")
]:
 try:
  result=ssh_host("nodeb",["pct","exec",container,"--","sh","-c",cmd])
  print("CONTAINER",container,result[:1300],flush=True)
 except Exception as e:print("CONTAINER_BLOCKED",container,type(e).__name__,str(e)[:110],flush=True)
