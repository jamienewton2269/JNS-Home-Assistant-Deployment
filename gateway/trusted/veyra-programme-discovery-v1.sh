#!/usr/bin/env bash
# Veyra programme discovery UI v0.9.2-next — preserves kiosk graphics.
set -Eeuo pipefail
test "$(id -u)" = 0 || { echo "Use sudo"; exit 2; }
# End successful updates by asking Veyra's supervisor to replace the current
# provider Chrome session with the local Home dashboard. Preserve Cage and logins.
return_veyra_home() {
  echo "=== Returning Veyra to Home (Chrome provider session switches) ==="
  local code
  code="$(curl -sS --max-time 8 -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8767/home)" || {
    echo "ERROR: Veyra Home controller unavailable; do not restart Cage." >&2
    return 1
  }
  if [ "$code" != 204 ]; then
    echo "ERROR: Home controller returned HTTP $code" >&2
    return 1
  fi
  sleep 4
  echo "Veyra Home requested; verify dashboard is visible on laptop."
}
VIEW=/opt/veyra/veyra/view.py
test -s "$VIEW" || { echo "Missing $VIEW"; exit 3; }
if grep -q 'veyra-programme-discovery-v1' "$VIEW"; then echo "Already installed"; return_veyra_home; exit 0; fi
B=/var/backups/veyra-programme-discovery/$(date +%Y%m%d-%H%M%S)
mkdir -p "$B"
cp -a "$VIEW" "$B/view.py"
python3 - "$VIEW" <<'PY'
from pathlib import Path
import ast,sys
p=Path(sys.argv[1]); s=p.read_text()
marker='function addProgramme(){'
assert s.count(marker)==1, 'Unexpected view.py format'
# Inject into the Veyra page JS. Keep the existing submit and validation mechanism.
addition=r"""
// veyra-programme-discovery-v1
let vSearchTimer=0, vSearchAbort=null, vLastSearch='';
function vEsc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\u0027':'&#39;'}[c]));}
const vProviders={
  itvx:{label:'ITVX',url:'https://www.itv.com/watch'},
  iplayer:{label:'BBC iPlayer',url:'https://www.bbc.co.uk/iplayer'},
  channel4:{label:'Channel 4',url:'https://www.channel4.com/'},
  netflix:{label:'Netflix',url:'https://www.netflix.com/browse'},
  primevideo:{label:'Prime Video',url:'https://www.amazon.co.uk/gp/video/storefront'},
  disney:{label:'Disney+',url:'https://www.disneyplus.com/'}
};
function vEnhanceProgrammeDialog(){
  const title=document.getElementById('ptitle');
  if(!title||title.dataset.veyraDiscovery)return;
  title.dataset.veyraDiscovery='1';
  title.setAttribute('autocomplete','off');
  const wrap=document.createElement('div');
  wrap.id='vCatalogueResults';wrap.setAttribute('role','listbox');
  wrap.style='margin-top:9px;max-height:33vh;overflow:auto;display:grid;gap:6px';
  title.parentNode.appendChild(wrap);
  const note=document.createElement('p');note.style='font-size:13px;opacity:.8';
  note.textContent='Suggestions from TVmaze programme metadata. Provider availability and direct episode links must be checked; the provider homepage is not a direct programme link.';
  wrap.parentNode.appendChild(note);
  title.addEventListener('input',()=>{clearTimeout(vSearchTimer);vSearchTimer=setTimeout(()=>vSearchProgramme(title.value),300);});
  title.addEventListener('keydown',e=>{if(e.key==='Escape'&&wrap.textContent){wrap.replaceChildren();e.stopPropagation();}});
}
async function vSearchProgramme(q){
 const out=document.getElementById('vCatalogueResults');
 if(!out)return;
 q=q.trim();
 if(q.length<2){out.replaceChildren();return;}
 if(vSearchAbort)vSearchAbort.abort();
 vSearchAbort=new AbortController();
 out.textContent='Searching programme catalogue…';
 try{
  const r=await fetch('https://api.tvmaze.com/search/shows?q='+encodeURIComponent(q),{signal:vSearchAbort.signal});
  if(!r.ok)throw new Error('Catalogue unavailable');
  const results=(await r.json()).slice(0,10);
  out.replaceChildren();
  if(!results.length){out.textContent='No catalogue matches. You can enter a title manually.';return;}
  for(const row of results){
   const show=row.show||{}, name=show.name||'Unknown', date=show.premiered||'';
   const b=document.createElement('button');b.type='button';
   b.className='btn';
   b.style='text-align:left;white-space:normal;padding:10px;';
   b.textContent=name+(date?' ('+date.slice(0,4)+')':'')+(show.network?.name?' · '+show.network.name:show.webChannel?.name?' · '+show.webChannel.name:'');
   b.addEventListener('click',()=>{
     const input=document.getElementById('ptitle');if(input)input.value=name;
     const url=document.getElementById('purl');
     if(url&&show.officialSite&&/^https:\/\//.test(show.officialSite)){url.value=show.officialSite;}
     out.replaceChildren();
   });
   out.appendChild(b);
  }
 }catch(e){if(e.name!=='AbortError')out.textContent='Catalogue unavailable. Manual entry is still supported.';}
}
function vSetProviderLanding(){
 const sel=document.getElementById('pprovider'),url=document.getElementById('purl');
 if(!sel||!url)return;
 const p=vProviders[sel.value];
 if(p && !url.value.trim())url.value=p.url;
}
function vWatchAddDialog(){
 const wrap=document.getElementById('modalWrap');
 if(!wrap)return;
 const observer=new MutationObserver(()=>{
  if(document.getElementById('ptitle')&&!document.getElementById('vCatalogueResults')) {
   vEnhanceProgrammeDialog();
   const sel=document.getElementById('pprovider');
   if(sel && !sel.dataset.veyraLanding){
    sel.dataset.veyraLanding='1';
    sel.addEventListener('change',vSetProviderLanding);
   }
  }
 });
 observer.observe(wrap,{childList:true,subtree:true});
}
document.addEventListener('DOMContentLoaded',vWatchAddDialog);
setTimeout(vWatchAddDialog,0);
"""
# Inject before function addProgramme in existing inline script (no change to other controllers).
s=s.replace(marker,addition+'\n'+marker,1)
ast.parse(s)
p.write_text(s)
print('Veyra catalogue UI patched')
PY
/opt/veyra/.venv/bin/python -m py_compile "$VIEW"
echo "Backup: $B"
echo "The Python UI source was updated. No Cage/seatd/systemd change."
return_veyra_home
echo "The browser has been asked to reopen Veyra Home with the updated interface."
