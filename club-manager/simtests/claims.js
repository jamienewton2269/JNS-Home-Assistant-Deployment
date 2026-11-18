'use strict';
const q=s=>document.querySelector(s),status=q('#status');
async function api(path,method='GET',payload){
 const response=await fetch('/sim/claims/'+path,{method,credentials:'same-origin',cache:'no-store',
 headers:{'Content-Type':'application/json'},body:payload?JSON.stringify(payload):undefined});
 const value=await response.json().catch(()=>({error:'Operation unavailable'}));
 if(!response.ok)throw Error(value.error||'Access denied');return value;
}
async function load(){
 const records=await api('state'),select=q('#request-id'),chosen=select.value;select.replaceChildren();
 const table=document.createElement('table');table.className='test-table';const head=table.insertRow();
 for(const h of ['Claim','Requested','Approvals','Status','Document retrieval']){const th=document.createElement('th');th.textContent=h;head.append(th)}
 for(const record of records){
  if(record.status==='requested'&&record.distinct_approvals<2){
   const o=document.createElement('option');o.value=record.request_id;o.textContent=record.reference;select.append(o)
  }
  const tr=table.insertRow();
  for(const value of [record.reference,new Date(record.requested_at).toLocaleString('en-GB'),
   record.distinct_approvals+' / 2',record.status,'Disabled']){
    const td=tr.insertCell();td.textContent=value
  }
 }
 if([...select.options].some(o=>o.value===chosen))select.value=chosen;
 q('#claims').replaceChildren(table);
 status.textContent='Claims registry loaded. No original policy documents are accessible.';
}
q('#request-form').addEventListener('submit',async e=>{
 e.preventDefault();try{const x=Object.fromEntries(new FormData(e.target));await api('request','POST',x);
 await load();status.textContent='Claim access requested; separate officer approvals required.'}
 catch(err){status.textContent=err.message}
});
q('#approve-form').addEventListener('submit',async e=>{
 e.preventDefault();try{const x=Object.fromEntries(new FormData(e.target));const r=await api('approve','POST',x);
 await load();status.textContent='Approvals: '+r.distinct_approvals+'/2. Document retrieval remains disabled.'}
 catch(err){status.textContent=err.message}
});
load().catch(e=>status.textContent=e.message);
