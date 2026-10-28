#!/usr/bin/env python3
"""Read-only verify privately staged ESPHome integration is eligible for native flow.

Never emit host, port, password, noise PSK, device identifiers, title or paths.
"""
import base64,json,os,shlex,subprocess
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
HOST=r'''
import json,os,pathlib,re,socket,hashlib
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
stage=root/"esphome-enrolment-private.json"
manifest=root/"manifest.json"
if not manifest.is_file() or not stage.is_file() or stage.is_symlink() or manifest.is_symlink():raise SystemExit(71)
m=json.loads(manifest.read_text())
if m.get("source_vm")!=906 or m.get("target_vm")!=905:raise SystemExit(72)
entry=json.loads(stage.read_text())
if entry.get("domain")!="esphome":raise SystemExit(73)
data=entry.get("data",{})
if not isinstance(data,dict):raise SystemExit(74)
host=data.get("host") or data.get("ip_address")
port=data.get("port",6053)
key=data.get("noise_psk")
password=data.get("password")
keys={"host","port","noise_psk","password"}
other=[x for x in data if x not in keys]
host_ok=isinstance(host,str) and len(host)<255 and bool(host)
port_ok=isinstance(port,int) and 1<=port<=65535
key_ok=key is None or (isinstance(key,str) and len(key)>=40)
password_ok=password is None or isinstance(password,str)
tcp=False
if host_ok and port_ok:
 try:
  with socket.create_connection((host,port),timeout=5):tcp=True
 except OSError:pass
out={"source_identity_verified":m.get("source_vm")==906,
"one_enrolment_record":True,
"native_host_available":host_ok,
"native_port_valid":port_ok,
"encrypted_secret_staged":isinstance(key,str) and len(key)>=40,
"secret_field_syntax_valid":key_ok and password_ok,
"legacy_password_present":bool(password),
"extra_data_keys_count":len(other),
"tcp_open_from_node_b":tcp,
"source_archive_present":bool(root/"manifest.json"),
"raw_secret_emitted":False,
"guest_config_changed":False}
print("JNS_ESP_NATIVE_FLOW_PRIVATE_SCHEMA="+json.dumps(out,sort_keys=True))
raise SystemExit(0 if host_ok and port_ok and key_ok and password_ok and tcp else 1)
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 code=base64.b64encode(HOST.encode()).decode()
 try:p=subprocess.run(SSH+["nodeb",shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+code+"'))"])],
                      capture_output=True,text=True,timeout=45)
 except (OSError,subprocess.TimeoutExpired):return 1
 for line in p.stdout.splitlines():
  if line.startswith("JNS_ESP_NATIVE_FLOW_PRIVATE_SCHEMA="):print(line,flush=True)
 return 0 if p.returncode==0 else 1
if __name__=="__main__":raise SystemExit(main())
