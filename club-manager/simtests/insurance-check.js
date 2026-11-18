'use strict';
const q=s=>document.querySelector(s), status=q('#status');
q('#preflight').addEventListener('submit',async e=>{
 e.preventDefault();
 const f=q('[name=document]').files[0];
 if(!f||f.size>512*1024){status.textContent='Please select a PDF no larger than 512 KiB.';return}
 const data=Object.fromEntries(new FormData(e.target));
 try{
  status.textContent='Checking document without saving it…';
  const bytes=new Uint8Array(await f.arrayBuffer());
  let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.slice(i,i+8192));
  const payload={filename:f.name,pdf_base64:btoa(binary)};
  for(const key of ['vessel_name','insurer','policy_ref','cover_from','cover_until'])payload[key]=data[key];
  const r=await fetch('/sim/insurance/preflight',{method:'POST',credentials:'same-origin',
   headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),cache:'no-store'});
  const answer=await r.json().catch(()=>({error:'File validation failed'}));
  if(!r.ok)throw Error(answer.error||'Preflight failed');
  const out=document.createElement('ul');for(const [key,match] of Object.entries(answer.checks)){
   const item=document.createElement('li');item.textContent=key.replaceAll('_',' ')+' — '+(match?'text found':'not matched');out.append(item)
  }
  const summary=document.createElement('p');summary.textContent='Matched '+answer.matched_fields+'/'+answer.required_fields+
    ' fields. Status: NEEDS REVIEW. File NOT stored.';
  q('#results').replaceChildren(summary,out);status.textContent='PDF check completed. No insurance status changed.';
 }catch(error){status.textContent=error.message}
});
