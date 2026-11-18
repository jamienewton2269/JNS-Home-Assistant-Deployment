'use strict';
const q=s=>document.querySelector(s),status=q('#status'),gbp=p=>'£'+(Number(p)/100).toFixed(2);
function table(h,rows){const t=document.createElement('table');t.className='test-table';const tr=t.insertRow();for(const x of h){const th=document.createElement('th');th.textContent=x;tr.append(th)}for(const row of rows){const tr=t.insertRow();for(const x of row){const td=tr.insertCell();td.textContent=x??''}}return t}
async function api(path,method='GET',body){const r=await fetch('/sim/tenders/'+path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const x=await r.json().catch(()=>({error:'Unavailable'}));if(!r.ok)throw Error(x.error||'Access denied');return x}
async function load(){const d=await api('state');const member=q('#member'),old=member.value;member.replaceChildren();for(const m of d.full_members){const o=document.createElement('option');o.value=m.id;o.textContent=m.name;member.append(o)}if([...member.options].some(o=>o.value===old))member.value=old;
q('#tenders').replaceChildren(table(['Member','Tender','State'],d.tenders.map(t=>[t.member,t.label,t.state])));
q('#rates').replaceChildren(table(['Year','Annual fee'],d.rates.map(r=>[r.year,gbp(r.amount_pence)])));
q('#charges').replaceChildren(table(['Tender','Year','Fee'],d.charges.map(c=>[c.tender_id.slice(0,8),c.year,gbp(c.amount_pence)])));
status.textContent='Simulation records loaded'}
async function submit(path,obj){try{const answer=await api(path,'POST',obj);await load();status.textContent='Saved: '+JSON.stringify(answer)}catch(e){status.textContent=e.message}}
q('#allocate').addEventListener('submit',e=>{e.preventDefault();submit('allocate',Object.fromEntries(new FormData(e.target)))});
q('#invoice').addEventListener('submit',e=>{e.preventDefault();submit('invoice',Object.fromEntries(new FormData(e.target)))});
const y=String(new Date().getFullYear());q('#invoice [name=year]').value=y;
load().catch(e=>status.textContent=e.message);
