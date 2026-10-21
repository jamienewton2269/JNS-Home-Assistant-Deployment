import base64, json, subprocess, time, uuid

class ApplyError(RuntimeError): pass

def _guest(vmid,args,timeout=120):
    p=subprocess.run(["qm","guest","exec",str(vmid),"--",*args],
      capture_output=True,text=True,timeout=timeout)
    if p.returncode!=0:
        raise ApplyError((p.stderr or p.stdout or "qm guest exec failed").strip())
    try: r=json.loads(p.stdout)
    except Exception as exc: raise ApplyError("Invalid qemu guest-agent response") from exc
    if r.get("exitcode",0)!=0:
        raise ApplyError((r.get("err-data") or r.get("out-data") or "guest command failed").strip())
    return r.get("out-data","")

def _core_check(vmid):
    return _guest(vmid,["ha","core","check"],timeout=180)

def _core_restart(vmid):
    return _guest(vmid,["ha","core","restart"],timeout=180)

def apply_automation(vmid,automation):
    if not isinstance(automation,dict):
        raise ApplyError("automation must be an object")
    if not automation.get("alias"):
        raise ApplyError("automation alias is required")
    if not automation.get("trigger"):
        raise ApplyError("automation trigger is required")
    if not automation.get("action"):
        raise ApplyError("automation action is required")
    automation=dict(automation)
    automation.setdefault("id","natural_"+uuid.uuid4().hex)
    automation.setdefault("mode","single")
    payload=base64.b64encode(json.dumps(automation,separators=(",",":")).encode()).decode()
    stamp=time.strftime("%Y%m%d-%H%M%S")
    code=f"""import base64,json,os,shutil,yaml
p='/config/automations.yaml'
b='/config/.steward-backups'
os.makedirs(b,exist_ok=True)
backup=f"{{b}}/natural_automation.{stamp}.yaml"
if os.path.exists(p): shutil.copy2(p,backup)
else: open(backup,'w').write('[]\\n')
obj=json.loads(base64.b64decode('{payload}'))
data=[]
if os.path.exists(p):
    data=yaml.safe_load(open(p)) or []
if not isinstance(data,list): raise RuntimeError('natural_automation.yaml is not a YAML list')
if any(str(x.get('id',''))==str(obj['id']) for x in data if isinstance(x,dict)):
    raise RuntimeError('automation id already exists')
data.append(obj)
tmp=p+'.steward.tmp'
with open(tmp,'w') as f: yaml.safe_dump(data,f,sort_keys=False,allow_unicode=True)
os.replace(tmp,p)
print(json.dumps({{'backup':backup,'path':p,'id':obj['id']}}))
"""
    out=_guest(vmid,["docker","exec","homeassistant","python3","-c",code])
    meta=json.loads(out)
    try:
        check=_core_check(vmid)
    except Exception:
        rb=f"""import shutil; shutil.copy2({meta['backup']!r},'/config/automations.yaml')"""
        _guest(vmid,["docker","exec","homeassistant","python3","-c",rb])
        raise
    # HA YAML automation includes are not guaranteed to hot-reload from an external host;
    # restart HA-General only after a successful config validation.
    _core_restart(vmid)
    return {"ok":True,"automation_id":automation["id"],"backup":meta["backup"],"check":check}
