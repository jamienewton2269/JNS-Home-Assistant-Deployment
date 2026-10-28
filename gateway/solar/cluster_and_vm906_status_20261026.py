#!/usr/bin/env python3
"""JNS Proxmox cluster readiness and VM906 handover verification.
READ ONLY. Never outputs guest network addresses, MACs or service secrets.
"""
import json,os,pathlib,re,shlex,socket,subprocess,urllib.error,urllib.request

SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
def local(cmd,timeout=13):
 try: return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def remote(host,script,timeout=35):
 p=local(SSH+[host,shlex.join(["python3","-c",script])],timeout=timeout)
 if not p or p.returncode:return {"reachable":False}
 lines=[x.split("=",1)[1] for x in p.stdout.splitlines() if x.startswith("JNS_NODE_AUDIT_JSON=")]
 if len(lines)!=1:return {"reachable":True,"valid_output":False}
 try:return json.loads(lines[0])
 except ValueError:return {"reachable":True,"valid_output":False}
REMOTE=r'''
import json,re,subprocess,pathlib,os,socket
host=os.uname().nodename.split(".")[0]
def run(cmd,timeout=12):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
out={"host":host,"reachable":True}
out["corosync_conf_present"]=pathlib.Path("/etc/pve/corosync.conf").exists()
# Node A production VM905 placement (and Node B source) checks; do not print
# network addresses, volume serials or MACs from raw Proxmox configuration.
p=run(["qm","config","905"])
q=run(["qm","status","905"])
out["vm905_definition_present"]=bool(p and p.returncode==0)
out["vm905_state"]=q.stdout.strip().removeprefix("status: ") if q and q.returncode==0 else "unavailable"
if p and p.returncode==0:
 cfg=p.stdout
 out["vm905_config_nonempty"]=bool(cfg.strip())
 out["vm905_config_field_keys"]=sorted(set(k for k in re.findall(r"(?m)^([a-z][a-z0-9_]*):",cfg) if k in ("name","memory","balloon","onboot","scsi0","efidisk0","agent","cores","net0")))
 out["vm905_memory_mib"]=int(re.search(r"(?m)^memory:\s*(\d+)$",cfg).group(1)) if re.search(r"(?m)^memory:\s*(\d+)$",cfg) else None
 out["vm905_balloon_disabled"]=bool(re.search(r"(?m)^balloon:\s*0$",cfg))
 out["vm905_onboot_disabled"]=bool(re.search(r"(?m)^onboot:\s*0$",cfg))
 out["vm905_disk_definitions"]=len(re.findall(r"(?m)^(?:scsi|virtio|sata|ide|efidisk)\d+:",cfg))
 out["vm905_storage_ids"]=sorted(set(re.findall(r"(?m)^(?:scsi|virtio|sata|ide|efidisk)\d+:\s*([A-Za-z0-9_-]+):",cfg)))
 out["vm905_ha_general_role"]=bool(re.search(r"(?m)^name:\s*ha-s2-general$",cfg))
z=run(["zfs","list","-Hp","-o","available","vmdata"])
if z and z.returncode==0:
 try:out["vmdata_available_gib"]=round(int(z.stdout.strip())/1073741824,1)
 except ValueError:pass
p=run(["pvecm","status"])
out["pvecm_status_ok"]=bool(p and p.returncode==0)
if p:
 m=re.search(r"Quorate:\s+(Yes|No)",p.stdout)
 out["quorate"]=m.group(1) if m else "unavailable"
 m=re.search(r"Nodes:\s+(\d+)",p.stdout)
 if m:out["cluster_nodes"]=int(m.group(1))
def guests(command):
 p=run(command)
 if not p or p.returncode:return []
 lines=p.stdout.splitlines()[1:]
 ids=[]
 for row in lines:
  item=row.strip().split()
  if item and item[0].isdigit():ids.append(int(item[0]))
 return sorted(set(ids))
out["vm_ids"]=guests(["qm","list"])
out["ct_ids"]=guests(["pct","list"])
if host=="nodea":
 p=run(["qm","status","906"])
 out["ha_security_vm906_running"]=bool(p and p.stdout.strip()=="status: running")
 p=run(["qm","config","906"])
 out["ha_security_vm906_onboot"]=bool(p and re.search(r"^onboot:\s+1\s*$",p.stdout,re.M))
 out["ha_security_vm906_autostart_off"]=bool(p and re.search(r"^onboot:\s+0\s*$",p.stdout,re.M))
 p=run(["qm","status","902"])
 out["ha_primary_vm902_running"]=bool(p and p.returncode==0 and p.stdout.strip()=="status: running")
 p=run(["systemctl","is-active","jns-ha906-recovery-20261028.timer"])
 out["ha_security_recovery_timer_active"]=bool(p and p.returncode==0 and p.stdout.strip()=="active")
 p=run(["systemctl","is-failed","jns-ha906-recovery-20261028.service"])
 out["ha_security_recovery_service_failed"]=bool(p and p.stdout.strip()=="failed")
 p=run(["free","-m"])
 if p:
  row=[x for x in p.stdout.splitlines() if x.startswith("Mem:")]
  if row:
   b=row[0].split()
   if len(b)>6:out["available_memory_mib"]=int(b[6])
if host=="nodeb":
 p=run(["qm","status","905"])
 out["ha_general_vm905_running"]=bool(p and p.returncode==0 and p.stdout.strip()=="status: running")
 p=run(["qm","status","903"])
 out["plant_manager_vm903_running"]=bool(p and p.returncode==0 and p.stdout.strip()=="status: running")
 for ct,kind in ((212,"mqtt"),(214,"zigbee2mqtt"),(216,"time"),(248,"dns_dhcp")):
  p=run(["pct","status",str(ct)])
  out["ct"+str(ct)+"_"+kind+"_running"]=bool(p and p.returncode==0 and p.stdout.strip()=="status: running")
 p=run(["free","-m"])
 if p:
  row=[x for x in p.stdout.splitlines() if x.startswith("Mem:")]
  if row:
   b=row[0].split()
   if len(b)>6:out["available_memory_mib"]=int(b[6])
 p=run(["free","-m"])
 if p:
  row=[x for x in p.stdout.splitlines() if x.startswith("Mem:")]
  if row:
   b=row[0].split()
   if len(b)>6:out["available_memory_mib"]=int(b[6])
print("JNS_NODE_AUDIT_JSON="+json.dumps(out,sort_keys=True))
'''
def endpoint():
 d={}
 try:
  with socket.create_connection(("ha-security.home.arpa",8123),timeout=4):
   d["tcp_8123"]=True
 except OSError:d["tcp_8123"]=False
 if d["tcp_8123"]:
  try:
   req=urllib.request.Request("http://ha-security.home.arpa:8123/",method="GET")
   with urllib.request.urlopen(req,timeout=7) as res:d["http_status"]=res.status
  except urllib.error.HTTPError as e:d["http_status"]=e.code
  except Exception:d["http_status"]="not_responding"
 return d
def nodec():
 d={"host":os.uname().nodename.split(".")[0]}
 try:d["source_vm906_qemu_pid_present"]=pathlib.Path("/run/qemu-server/906.pid").exists()
 except PermissionError:d["source_vm906_qemu_pid_present"]="unreadable"
 try:d["local_corosync_conf_present"]=pathlib.Path("/etc/pve/corosync.conf").exists()
 except PermissionError:d["local_corosync_conf_present"]="unreadable"
 p=local(["ps","-eo","args="])
 d["source_vm906_qemu_process_detected"]=bool(p and any(
  ("qemu-system" in row or "kvm " in row) and re.search(r" -id 906(?:\s|$)",row)
  for row in p.stdout.splitlines()))
 p=local(["pvecm","status"])
 d["pvecm_status_ok"]=bool(p and p.returncode==0)
 p=local(["qm","status","906"])
 d["qm906_local_readable"]=bool(p and p.returncode==0)
 if p and p.returncode==0:d["qm906_status"]=p.stdout.strip()[:40]
 d["ha_security_endpoint"]=endpoint()
 d["nfs_staging_present"]=pathlib.Path("/mnt/pve/nfs-ct").is_mount()
 for kind,command in (("vm",["qm","list"]),("ct",["pct","list"])):
  p=local(command)
  if p and p.returncode==0:
   d[kind+"_ids"]=sorted(set(int(parts[0]) for row in p.stdout.splitlines()[1:]
     if (parts:=row.strip().split()) and parts[0].isdigit()))
  else:d[kind+"_inventory_readable"]=False
 return d
a=remote("nodea",REMOTE)
b=remote("nodeb",REMOTE)
c=nodec()
def ids(d):
 return set(d.get("vm_ids",[]))|set(d.get("ct_ids",[]))
ab=sorted(ids(a)&ids(b))
cross_types_a=set(a.get("vm_ids",[]))&set(a.get("ct_ids",[]))
cross_types_b=set(b.get("vm_ids",[]))&set(b.get("ct_ids",[]))
print("JNS_CLUSTER_AND_VM906_READONLY_CHECK")
print("NODEA="+json.dumps({k:v for k,v in a.items() if k not in ("vm_ids","ct_ids")},sort_keys=True))
print("NODEB="+json.dumps({k:v for k,v in b.items() if k not in ("vm_ids","ct_ids")},sort_keys=True))
print("NODEC="+json.dumps(c,sort_keys=True))
print("NODE_A_B_GUEST_VMID_COLLISIONS="+json.dumps(ab))
print("NODEA_LOCAL_VMID_COLLISIONS="+json.dumps(sorted(cross_types_a)))
print("NODEB_LOCAL_VMID_COLLISIONS="+json.dumps(sorted(cross_types_b)))
nodec_inventory_known="vm_ids" in c and "ct_ids" in c
print("NODE_A_C_GUEST_VMID_COLLISIONS="+json.dumps(sorted(ids(a)&ids(c)) if nodec_inventory_known else "unknown_nodec_inventory_unreadable"))
print("NODE_B_C_GUEST_VMID_COLLISIONS="+json.dumps(sorted(ids(b)&ids(c)) if nodec_inventory_known else "unknown_nodec_inventory_unreadable"))
print("JNS_CLUSTER_MIGRATION_GATES="+json.dumps({
 "nodea_standalone":a.get("reachable")==True and a.get("corosync_conf_present")==False,
 "nodeb_standalone":b.get("reachable")==True and b.get("corosync_conf_present")==False,
 "nodec_runner":c.get("host")=="nodec",
 "nodec_guest_inventory_verified":nodec_inventory_known,
 "nodea_ha_primary_running":a.get("ha_primary_vm902_running"),
 "nodea_security_running":a.get("ha_security_vm906_running"),
 "nodea_security_recovery_timer_active":a.get("ha_security_recovery_timer_active"),
 "nodeb_general_running":b.get("ha_general_vm905_running"),
 "nodea_vm905_collision_present":a.get("vm905_definition_present"),
 "nodea_vm905_stopped":a.get("vm905_state")=="stopped",
 "nodea_vm905_available_storage_gib":a.get("vmdata_available_gib"),
 "nodeb_vm905_source_storage_gib":b.get("vmdata_available_gib"),
 "nodeb_plant_vm903_running":b.get("plant_manager_vm903_running"),
 "nodeb_essential_lxcs_running":all(b.get("ct"+str(n)+"_"+role+"_running")==True for n,role in
  ((212,"mqtt"),(214,"zigbee2mqtt"),(216,"time"),(248,"dns_dhcp"))),
 "a_b_guest_id_collisions":len(ab),
 "a_c_guest_id_collisions":len(ids(a)&ids(c)) if nodec_inventory_known else None,
 "b_c_guest_id_collisions":len(ids(b)&ids(c)) if nodec_inventory_known else None,
 "cluster_changes_permitted":False
},sort_keys=True))
print("JNS_CLUSTER_AND_VM906_READONLY_COMPLETE")
