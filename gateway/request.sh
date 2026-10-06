#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'python3 - <<'"'"'PY'"'"'
from pathlib import Path
p=Path("/opt/natural-automation/natural_automation.py")
s=p.read_text()
p.with_suffix(".py.pre-apply-ui").write_text(s)

if "def build_automation_proposal(" not in s:
    marker="def analyse(text, progress=None):"
    insert=r"""
def build_automation_proposal(text, entity_id, display_name=None):
    import re
    low=" ".join(str(text).lower().split())
    tm=re.search(r"\bat\s+([01]?\d|2[0-3]):([0-5]\d)\b", low)
    dur=re.search(r"\bfor\s+(\d+)\s*(min|mins|minute|minutes|hr|hrs|hour|hours)\b", low)
    if not tm or not dur:
        return None
    domain=entity_id.split(".",1)[0] if "." in entity_id else ""
    if domain not in ("light","switch","fan","input_boolean"):
        return None
    amount=int(dur.group(1))
    if amount < 1:
        return None
    unit=dur.group(2)
    if unit in ("hr","hrs","hour","hours"):
        if amount > 24:
            return None
        delay={"hours":amount}
        duration_text=f"{amount} hour" + ("s" if amount != 1 else "")
    else:
        if amount > 1440:
            return None
        delay={"minutes":amount}
        duration_text=f"{amount} minute" + ("s" if amount != 1 else "")
    hh=int(tm.group(1)); mm=int(tm.group(2))
    at=f"{hh:02d}:{mm:02d}:00"
    name=display_name or entity_id
    alias=f"Natural Automation - {name} - {hh:02d}:{mm:02d} for {duration_text}"
    automation={
        "alias":alias,
        "description":f"Created by Natural Automation from request: {text}",
        "trigger":[{"platform":"time","at":at}],
        "condition":[],
        "action":[
            {"service":f"{domain}.turn_on","target":{"entity_id":entity_id}},
            {"delay":delay},
            {"service":f"{domain}.turn_off","target":{"entity_id":entity_id}},
        ],
        "mode":"single",
    }
    return {
        "summary":f"At {hh:02d}:{mm:02d}, turn on {entity_id} for {duration_text}, then turn it off.",
        "automation":automation,
        "unresolved":[],
    }

"""
    s=s.replace(marker,insert+marker,1)

old='''    result={"action":action,"request":text,"target_phrase":target,"target":chosen,
            "controllers":ctrls,"apply_enabled":ENABLE_APPLY,"logic":logic}
'''
new='''    proposal=build_automation_proposal(text,chosen["entity_id"],chosen.get("name")) if action=="create" else None
    if action=="create" and proposal:
        logic.append("A complete native Home Assistant automation proposal is ready for confirmation.")
    elif action=="create":
        logic.append("No Apply button is offered because this timing pattern is not yet fully supported or resolved.")
    result={"action":action,"request":text,"target_phrase":target,"target":chosen,
            "controllers":ctrls,"apply_enabled":ENABLE_APPLY,"logic":logic,"proposal":proposal}
'''
if old not in s:
    raise SystemExit("result marker not found")
s=s.replace(old,new,1)

s=s.replace("let activeRequest='';\nlet multiState=null;","let activeRequest='';\nlet multiState=null;\nlet currentProposal=null;",1)

show_start=s.index("function show(d){")
show_end=s.index("\nrefreshInlineAdmin();\nsetInterval",show_start)
old_show=s[show_start:show_end]
new_show=r'''async function applyCurrentProposal(){
  if(!currentProposal||!currentProposal.automation){return}
  if(!window.confirm("Apply this automation to HA-General?\n\n"+currentProposal.summary)){return}
  let o=document.getElementById('o');
  o.className='card progress';
  o.innerHTML='<h3>Applying automation…</h3><p class="muted">Writing transactionally, validating Home Assistant and preserving a rollback copy.</p>';
  let d=await post('/api/apply-automation',{automation:currentProposal.automation,unresolved:currentProposal.unresolved||[]});
  if(!d._http_ok){
    show({action:'error',error:d.error||'Automation apply failed.',suggestion:'The controlled write path did not complete. Review the audit log; rollback protection remains in effect.'});
    return
  }
  o.className='card';
  o.innerHTML='<h3>APPLIED</h3><p><b>'+esc(currentProposal.summary)+'</b></p>'+
    '<p>Automation ID: <code>'+esc(d.automation_id||'created')+'</code></p>'+
    '<p class="muted">Home Assistant configuration validation passed and the automation was written to HA-General.</p>';
  currentProposal=null;
  await refreshInlineAdmin()
}

function show(d){
  let o=document.getElementById('o');o.className='card';
  currentProposal=null;
  if((d._http_ok===false)||d.error||d.action==='error'){o.className='card error';o.innerHTML='<h3>ERROR - request not understood</h3><p><b>'+(d.error||'Unknown error')+'</b></p>'+(d.suggestion?'<p>'+d.suggestion+'</p>':'')+'<p class="muted">Nothing has been changed in Home Assistant.</p>';return}
  if(d.action==='select_devices'){showMulti(d);return}
  if(d.action==='multi_selection_confirmed'){
    let h='<h3>MULTIPLE DEVICES CONFIRMED</h3><p>'+d.selected.length+' device(s) selected:</p><ul>'+d.selected.map(x=>'<li><b>'+x.name+'</b> · '+x.entity_id+(x.area?' · '+x.area:'')+'</li>').join('')+'</ul>';
    if(d.logic)h+='<h4>What I understood</h4><ol>'+d.logic.map(x=>'<li>'+x+'</li>').join('')+'</ol>';
    o.innerHTML=h;return
  }
  if(d.action==='clarify'){
    o.innerHTML='<h3>Which device?</h3><p>I need you to confirm what you mean before I continue.</p>';
    d.candidates.forEach(c=>{let b=document.createElement('button');b.className='cand';b.textContent=c.name+' · '+c.entity_id+' · '+c.score;b.onclick=async()=>{await post('/api/alias',{phrase:d.target_phrase,entity_id:c.entity_id});await analyseText(activeRequest,false)};o.appendChild(b)});
    return
  }
  let h='<h3>'+d.action.replaceAll('_',' ').toUpperCase()+'</h3><p>Target: <b>'+d.target.entity_id+'</b></p>';
  if(d.controllers.length){h+='<p>Existing controllers found:</p><div id="controllers"></div>'}
  if(d.action==='conflict')h+='<p><b>No new automation will be created until this conflict is resolved.</b></p><p class="muted">If one of these automations is obsolete, propose its removal for admin review.</p>';
  if(d.logic){h+='<h4>What I understood</h4><ol>'+d.logic.map(x=>'<li>'+x+'</li>').join('')+'</ol>'}
  if(d.action==='create'&&d.proposal&&d.apply_enabled){
    currentProposal=d.proposal;
    h+='<div class="admincard"><h4>Proposed automation</h4><p><b>'+esc(d.proposal.summary)+'</b></p>'+
       '<details><summary>Show native Home Assistant automation</summary><pre>'+esc(JSON.stringify(d.proposal.automation,null,2))+'</pre></details>'+
       '<button class="primary" onclick="applyCurrentProposal()">Apply automation</button>'+
       '<p class="muted">Nothing is written until you press Apply automation and confirm.</p></div>'
  }else if(d.action==='create'&&!d.proposal){
    h+='<p class="muted">Apply is unavailable until the schedule can be translated without assumptions.</p>'
  }
  o.innerHTML=h;
  let box=document.getElementById('controllers');
  if(box){d.controllers.forEach(c=>{let row=document.createElement('div');row.className='stage';row.textContent=c.alias+' · '+c.role.toUpperCase()+' · '+c.source;if(d.controllers.length>1){let b=document.createElement('button');b.className='remove';b.textContent='Propose removal';b.onclick=()=>proposeRemoval(c,b);row.appendChild(b)}box.appendChild(row)})}
  refreshInlineAdmin()
}
'''
s=s[:show_start]+new_show+s[show_end:]
p.write_text(s)
PY
python3 -m py_compile /opt/natural-automation/natural_automation.py
systemctl restart natural-automation
sleep 2
curl -fsS http://127.0.0.1:8099/api/status
echo'
