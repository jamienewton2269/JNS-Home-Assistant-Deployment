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

print("JNS_Z2M_TARGET_READONLY_CHECK",flush=True)
for id,script in (
 ("214", "printf 'TARGET_MAP '; grep -Fn 'Garden String Lights' /opt/zigbee2mqtt/data/configuration.yaml | head -3 || :;printf 'NODE_BIN ';for x in /usr/bin/node /usr/local/bin/node /opt/zigbee2mqtt/node_modules/.bin/node;do if test -x \"$x\";then echo yes;fi;done;printf 'Z2M_SERVICE ';systemctl is-active zigbee2mqtt || :"),
 ("212", "mosquitto_sub -h 127.0.0.1 -t 'zigbee2mqtt/Garden String Lights' -C 1 -W 3 >/dev/null 2>&1; code=$?; echo \"ANON_SUB_EXIT $code\"")
):
 try:
  print("DEVICE",id,ssh_host("nodeb",["pct","exec",id,"--","sh","-c",script])[:550],flush=True)
 except Exception as e:print("DEVICE_PROBE_BLOCKED",id,type(e).__name__,str(e)[:140],flush=True)

print("JNS_GUEST_AGENT_STATUS_SAFETY",flush=True)
try:
 raw=ssh_host("nodeb",["qm","guest","exec","905","--","ha","core","info"])
 obj=json.loads(raw)
 print("CORE_INFO_QGA",json.dumps({"keys":sorted(obj),"pid":obj.get("pid"),"exited":obj.get("exited"),"exitcode":obj.get("exitcode"),"error":str(obj.get("err-data") or "")[-270:],"out_tail":str(obj.get("out-data") or "")[-300:]}),flush=True)
except Exception as ex:print("CORE_INFO_QGA_ERROR",type(ex).__name__,str(ex)[:190],flush=True)
for cid,cmd in (
 ("214","printf 'DEVICE_CONFIG_CANDIDATES '; for p in /opt/zigbee2mqtt/data/devices.yaml /opt/zigbee2mqtt/data/configuration.yaml /opt/zigbee2mqtt/data/database.db;do if test -f \"$p\";then echo \"$p\"; fi;done; printf 'ID_HITS ';grep -Fl '0xa4c1388ba234f2e3' /opt/zigbee2mqtt/data/devices.yaml /opt/zigbee2mqtt/data/configuration.yaml 2>/dev/null || :;printf 'PYTHON ';command -v python3 || :;printf 'NODE_EXEC ';systemctl show zigbee2mqtt -p ExecStart --value | cut -c 1-180"),
 ("212","printf 'MOSQUITTO_AUTH_LINES ';grep -hE '^[[:space:]]*(allow_anonymous|password_file|listener)[[:space:]]' /etc/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/*.conf 2>/dev/null | cut -c 1-160 || :")
):
 try:print("TARGET_PROBE",cid,ssh_host("nodeb",["pct","exec",cid,"--","sh","-c",cmd])[:1200],flush=True)
 except Exception as e:print("TARGET_PROBE_BLOCKED",cid,type(e).__name__,str(e)[:120],flush=True)
