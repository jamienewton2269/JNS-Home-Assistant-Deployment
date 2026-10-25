"""Read-only offline repair knowledge UI for JNS Natural Automation / Steward.

Source library only: no arbitrary code execution, HA writes or access escalation.
"""
from __future__ import annotations

import re
from typing import Any

def search_repair_catalogue(store: Any, phrase: str, limit: int = 12) -> dict:
    if not isinstance(phrase, str) or len(phrase) > 240:
        raise ValueError("Search must be plain text of at most 240 characters")
    terms = re.findall(r"[a-zA-Z0-9_]{2,50}", phrase.lower())[:9]
    if not terms:
        raise ValueError("Enter a component or symptom, such as Zigbee, lux, MQTT or camera")
    # Construct fixed syntax; never interpolate untrusted FTS5 special operators.
    query = " OR ".join('"' + x + '"' for x in terms)
    hits = store.search_repairs(query, min(15, max(1, int(limit))))
    output = []
    for record in hits:
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        result = {
            "title": str(record.get("title") or "Untitled procedure")[:160],
            "subsystem": str(record.get("subsystem") or "unknown")[:70],
            "why": str(record.get("why") or record.get("problem") or "Unverified historical purpose")[:800],
            "how": str(record.get("how") or "; ".join(str(x) for x in record.get("repair_steps", [])))[:1200],
            "source_path": str(record.get("source_path") or "historical-entry")[:360],
            "source_sha256": str(record.get("source_sha256") or "")[:64],
            "purpose_provenance": str(evidence.get("purpose_provenance") or "legacy_unverified")[:80],
            "execution_evidence": str(evidence.get("execution_result") or "not_recorded")[:100],
            "verification": [str(x)[:300] for x in record.get("verification_steps", [])[:6]],
            "rollback": [str(x)[:300] for x in record.get("rollback_steps", [])[:6]],
            "related_workflows": [str(x)[:340] for x in evidence.get("workflow_references", [])[:8]],
            "manual_review": True,
            "executable_from_interface": False,
        }
        output.append(result)
    return {
        "ok": True,
        "query": phrase,
        "results": output,
        "result_count": len(output),
        "execution_authority": "none",
        "fixes_applied": 0,
        "notice": "Evidence-based advisory knowledge. Execution requires separately approved JNS gateway transaction.",
    }

REPAIR_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JNS Steward | Repair Centre</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;background:#0b121c;color:#e8f0fa}
*{box-sizing:border-box} body{margin:0;padding:22px}
main{max-width:1100px;margin:auto}
h1{font-size:1.7rem;margin:.5rem 0}h2{font-size:1.1rem}
p{line-height:1.55}.muted{color:#9db0c4}
header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;border-bottom:1px solid #324255;padding-bottom:12px}
a{color:#8ecafc}
section,.result{background:#121e2c;border:1px solid #2a3c52;border-radius:12px;padding:18px;margin-top:16px}
input,textarea{width:100%;padding:12px;background:#091523;color:white;border:1px solid #48607c;border-radius:8px;font:inherit}
textarea{min-height:100px;resize:vertical}label{font-size:.95rem;font-weight:650;display:block;margin:12px 0 7px}
button{background:#2775a9;color:white;padding:11px 16px;border:0;border-radius:8px;cursor:pointer;font:inherit;margin:12px 12px 0 0}
button:disabled{opacity:.55;cursor:default}.secondary{background:#253950}
.meta{font-size:.84rem;color:#a8bad1;overflow-wrap:anywhere;margin:7px 0}
strong{color:#e1f2ff}.warning{border-left:3px solid #e8a63d;padding:12px;background:#251e14;border-radius:5px}
.result{margin-top:12px}.result h3{margin:0 0 4px;font-size:1.08rem}
ul{padding-left:22px}li{margin:5px 0}
code{overflow-wrap:anywhere;color:#b5dffc}
details summary{cursor:pointer;margin:10px 0}
#info{margin-top:14px}#info.error{color:#ffb1a9}
</style></head><body><main>
<header><div><h1>JNS Steward Repair Centre</h1><div class="muted">Local offline repair knowledge · HA-General</div></div><nav><a href="/">Natural Automation</a> · <a href="/admin">Admin</a></nav></header>
<section><h2>Describe a Home Assistant fault</h2>
<p class="muted">Search the locally stored diagnostics, repair procedures, verification steps and rollback information. You can prepare a guided repair request for the existing JNS deployment gateway.</p>
<label for="issue">What is not working?</label>
<textarea id="issue" placeholder="e.g. The garden string lights stayed on after bedtime and the morning reset."></textarea>
<button id="search" onclick="search()">Find relevant repairs</button>
<button class="secondary" onclick="prepare()">Copy assisted repair request</button>
<div id="info" role="status" aria-live="polite">Ready. Try: Zigbee, lux, bedtime, MQTT, Tuya, camera or security.</div>
</section>
<section><h2>Repair knowledge</h2><p class="warning"><strong>Safe mode:</strong> Searching does not fix anything. Steward will not run historic scripts or change Home Assistant without a separately validated, approved, reversible deployment. A previous successful run is never inferred from the presence of script code.</p><div id="results"></div></section>
</main><script>
const esc = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
let current = [];
async function search(){
 const term=document.getElementById('issue').value.trim();
 const btn=document.getElementById('search'), info=document.getElementById('info'), out=document.getElementById('results');
 if(!term){info.textContent='Describe the fault first.';return}
 btn.disabled=true;info.textContent='Searching local repair knowledge…';out.innerHTML='';
 try{
  const response=await fetch('/api/steward/repair-search',{
   method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:term})});
  const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Search failed');
  current=data.results||[];
  info.textContent=current.length+' relevant procedures found. All require human review before any fix.';
  out.innerHTML=current.length?current.map((x,i)=>'<article class="result"><h3>'+esc(x.title)+'</h3>'+
   '<div class="meta">'+esc(x.subsystem)+' · '+esc(x.source_path)+'</div>'+
   '<p><strong>Why:</strong> '+esc(x.why)+'</p><p><strong>How:</strong> '+esc(x.how)+'</p>'+
   '<div class="meta">Purpose evidence: '+esc(x.purpose_provenance)+' · Previous execution: '+esc(x.execution_evidence)+'</div>'+
   '<details><summary>Verification, rollback and source evidence</summary>'+
    '<p><strong>Source SHA-256:</strong> <code>'+esc(x.source_sha256)+'</code></p>'+
    '<p><strong>Verification:</strong></p><ul>'+(x.verification||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul>'+
    '<p><strong>Rollback:</strong></p><ul>'+(x.rollback||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul>'+
    '<p><strong>Related workflows:</strong></p><ul>'+(x.related_workflows||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul>'+
   '</details></article>').join(''):'<p class="muted">No matching entry. This is not proof a fix is unavailable; try a different component or describe the fault for a new investigation.</p>';
 }catch(e){info.textContent='Cannot search: '+e.message;info.className='error';}
 finally{btn.disabled=false}
}
async function prepare(){
 const term=document.getElementById('issue').value.trim();
 if(!term){document.getElementById('info').textContent='Enter a fault description first.';return}
 const evidence=current.slice(0,4).map(x=>'- '+x.title+' ['+x.source_path+'] ('+x.purpose_provenance+')').join('\n');
 const request='JNS HA Steward assisted repair request:\nIssue: '+term+
 '\nTarget: resolve current Home Assistant service/host/guest before changes.'+
 '\nRelevant offline knowledge (advisory; not proof of repair success):\n'+(evidence||'- None yet; investigate first.')+
 '\nRequired workflow: read-only diagnosis → evidence-based proposal → backups → approval → guarded apply → live verification → rollback on failure.'+
 '\nNever restart Home Assistant or reuse an outdated script without explicit need and validation.';
 try{await navigator.clipboard.writeText(request);
  document.getElementById('info').textContent='Repair request copied. Paste it into your JNS ChatGPT conversation to arrange an authorised deployment.';
 }catch(e){document.getElementById('info').textContent='Clipboard is unavailable; copy the issue and source references manually.'}
}
document.getElementById('issue').addEventListener('keydown',e=>{
 if(e.key==='Enter' && (e.ctrlKey||e.metaKey)){e.preventDefault();search();}
});
</script></body></html>"""
