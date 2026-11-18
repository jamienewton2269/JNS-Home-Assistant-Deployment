'use strict';
const q=s=>document.querySelector(s),status=q('#status');
async function api(path,method='GET',body){
 const r=await fetch('/sim/ybm/'+path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
 const data=await r.json().catch(()=>({error:'Unavailable'}));if(!r.ok)throw Error(data.error||'Access denied');return data;
}
function table(headers,rows){
 const t=document.createElement('table');t.className='test-table';let row=t.insertRow();
 for(const h of headers){const th=document.createElement('th');th.textContent=h;row.append(th)}
 for(const cells of rows){row=t.insertRow();for(const value of cells){const td=row.insertCell();td.textContent=value??'—'}}return t;
}
function options(id,items){const node=q(id),previous=node.value;node.replaceChildren();
 for(const item of items){const option=document.createElement('option');option.value=item.registration;option.textContent=item.label+' — '+item.registration;node.append(option)}
 if([...node.options].some(x=>x.value===previous))node.value=previous;
}
async function history(){
 const reg=q('#trailer').value;if(!reg)return;
 const data=await api('history?registration='+encodeURIComponent(reg));
 q('#history').replaceChildren(table(['Date','Inspector','Result','Notes','Next due'],data.history.map(i=>[new Date(i.inspected_at).toLocaleString('en-GB'),i.inspector,i.outcome,i.notes,i.next_due])));
}
async function refresh(){
 const d=await api('assets');
 options('#registration',[...d.trailers,...d.registered_tenders]);options('#trailer',d.trailers);
 q('#assets').replaceChildren(table(['Registration','Asset','Owner','Last inspected','Result'],d.trailers.map(x=>[x.registration,x.label,x.owner,x.last_inspection?new Date(x.last_inspection).toLocaleString('en-GB'):'Never',x.last_result||'No inspection'])));
 await history();status.textContent='YBM asset register ready';
}
q('#trailer').addEventListener('change',()=>history().catch(e=>status.textContent=e.message));
q('#inspect-form').addEventListener('submit',async e=>{
 e.preventDefault();const d=Object.fromEntries(new FormData(e.target));d.next_due=d.next_due||null;
 try{await api('inspect','POST',d);await refresh();status.textContent='Inspection recorded; history retained.'}catch(err){status.textContent=err.message}
});
q('#label-form').addEventListener('submit',async e=>{
 e.preventDefault();try{
  const data=await api('issue','POST',Object.fromEntries(new FormData(e.target)));
  const container=q('#printed-label');container.replaceChildren();
  const image=document.createElement('img');image.width=220;image.height=220;image.alt='Dated QR for '+data.registration;
  image.src='/sim/ybm/qr.png?t='+encodeURIComponent(new URL(data.scan_url,location.origin).searchParams.get('t'));
  const caption=document.createElement('p');caption.textContent=data.registration+' — issued '+data.issued+' — expires '+data.expires;
  const link=document.createElement('a');link.textContent='Test authenticated QR lookup';link.href=data.scan_url;
  container.append(image,caption,link);status.textContent='Label issued. Save or print it now; any previous code is revoked.';
 }catch(err){status.textContent=err.message}
});
refresh().catch(e=>status.textContent=e.message);
