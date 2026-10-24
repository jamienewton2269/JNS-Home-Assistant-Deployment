#!/usr/bin/env python3
"""Build protected, human-readable service retirement register from the private,
checksum-pinned VM900 manifest on Node C. Never prints container details to CI.
Does not uninstall, modify, contact or restart any service/VM.
"""
import datetime,hashlib,json,os,pathlib,re,sys,tempfile

SHA="77555d0defa1574c7e4d22e63130a42e8958766264b713b2e9f361524a221e82"
def fail(code):
    print("HA900_SERVICE_REGISTER_BLOCKED="+code)
    sys.exit(1)
def clean(v):
    return str(v or "").replace("|","\\|").replace("\r"," ").replace("\n"," ")[:270]
def role(name,image):
    s=(str(name)+" "+str(image)).lower()
    for k,title in [
      ("esphome","ESPHome device services"),
      ("piper","Piper speech synthesis"),
      ("whisper","Speech recognition"),
      ("openwakeword","Voice wake-word"),
      ("audio","Audio transport"),
      ("music","Media playback"),
      ("dns","DNS/name resolution"),
      ("adguard","DNS filtering"),
      ("multicast","Multicast discovery"),
      ("mqtt","MQTT"),
      ("zigbee","Zigbee services"),
      ("matter","Matter bridge"),
      ("supervisor","HA Supervisor"),
      ("observer","HA Observer"),
      ("ssh","Remote access"),
      ("samba","File sharing"),
      ("go2rtc","Video stream"),
      ("camera","Camera integration"),
      ("mariadb","Database"),
      ("influxdb","Time series database"),
      ("node-red","Automation flows"),
      ("nodered","Automation flows"),
      ("homeassistant","Home Assistant Core")]:
        if k in s:return title
    return "Other / review required"
def main():
    if os.uname().nodename.split(".")[0]!="nodec" or os.geteuid()==0:fail("wrong_identity")
    root=pathlib.Path.home()/".local/share/jns-solar/ha900/evidence"
    mf=root/("vm900-services-"+SHA[:16]+".json")
    if root.is_symlink() or mf.is_symlink():fail("untrusted_path")
    if not mf.is_file() or mf.stat().st_mode & 0o077:fail("no_protected_manifest")
    raw=mf.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:fail("digest_failed")
    doc=json.loads(raw)
    if doc.get("schema")!="jns.solar.vm900.services.v1":fail("wrong_schema")
    containers=doc.get("containers",[])
    if len(containers)!=21:fail("unexpected_count")
    lines=[
      "# HA900 legacy support services — protected retirement register",
      "",
      "This is a **private audit record**; not approved for public GitHub.",
      "",
      "**Source:** Node A HA900 | **Target:** stopped historical reference on Node C",
      "**Manifest SHA-256:** "+SHA,
      "**Inventory:** 21 legacy containers, 19 running at capture",
      "",
      "**Removal gate:** BLOCKED. No container is approved for deletion.",
      "**Full VM recovery backup:** NOT YET VERIFIED.",
      "**Replacement consumers:** NOT YET VERIFIED.",
      "",
      "A container can be removed from the disposable HA900 staging copy only after:",
      "the config and data were independently backed up; consumers were",
      "checked against HA-General/HA-Primary/HA-Security and JNS infrastructure;",
      "the replacement was verified; a restoration test succeeded.",
      "",
      "## Captured services",
      "",
      "| Container | Service purpose (candidate) | Image | Captured state | Ports (metadata) | Replacement verified | Cleanup |",
      "|---|---|---|---|---|---|---|",
    ]
    counts={}
    for c in sorted(containers,key=lambda x:str(x.get("name","")).casefold()):
        candidate=role(c.get("name"),c.get("image"))
        counts[candidate]=counts.get(candidate,0)+1
        fields=[clean(c.get("name")),clean(candidate),clean(c.get("image")),
                clean(c.get("status")),clean(c.get("ports")),"NO","BLOCKED"]
        lines.append("| "+" | ".join(fields)+" |")
    lines += [
       "",
       "## Config capture and consumer disposition",
       "",
       "For each entry, record in protected Steward storage: source add-on/config",
       "path, image digest and installed version, secret-bearing settings exported",
       "to encrypted private backup, caller/consumer references, replacement",
       "host/service, equivalence test, rollback path and operator approval.",
       "The current manifest contains Docker metadata (including mounts and port",
       "bindings) **but not the contents of secrets or add-on configuration**.",
       "",
       "## Retained copies",
       "",
       "- Original untouched HA900 source VM: currently on Node A (not retired).",
       "- Source manifest: root-owned Node A /var/lib/jns-solar/ha900/evidence.",
       "- Duplicate manifest and this register: private runner-owned Node C staging.",
       "- Steward root-owned import: PENDING (restricted importer not installed).",
       "- Full offline recoverable VM backup: PENDING.",
       "- Node C cold reference VM: PENDING (storage capacity unverified).",
       "- Service removal and disk compaction: NOT STARTED.",
       "",
       "## Candidate roles (for prioritisation only)",
       "",
    ]
    for name,n in sorted(counts.items()):lines.append("- "+clean(name)+": "+str(n))
    lines.append("")
    payload=("\n".join(lines)+"\n").encode()
    target=root/"HA900_SERVICE_RETIREMENT_REGISTER_PRIVATE.md"
    if target.exists() and target.is_symlink():fail("destination_is_symlink")
    if target.exists() and target.stat().st_uid!=os.geteuid():fail("destination_owner_invalid")
    fd,tmp=tempfile.mkstemp(prefix=".ha900-retirement-",dir=str(root))
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(payload);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600)
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("HA900_PRIVATE_RETIREMENT_REGISTER_CREATED")
    print("SERVICES_DOCUMENTED="+str(len(containers)))
    print("CANDIDATE_SERVICE_ROLE_GROUPS="+str(len(counts)))
    print("REGISTER_SHA256="+hashlib.sha256(payload).hexdigest())
    print("PRIVATE_NODEC_STAGING=yes")
    print("FULL_CONFIG_EXPORT_COMPLETE=no")
    print("CLEANUP_GATE=blocked")
if __name__=="__main__":main()
