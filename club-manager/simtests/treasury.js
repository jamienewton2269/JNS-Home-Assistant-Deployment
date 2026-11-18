'use strict';
const q=s=>document.querySelector(s),note=q('#status');
const money=v=>{if(!/^\d+(\.\d{1,2})?$/.test(v))throw Error('Enter pounds and pence');return String(Math.round(Number(v)*100))};
const gbp=p=>'£'+(Number(p)/100).toFixed(2);
async function call(path,method='GET',data){const r=await fetch('/sim/treasury/'+path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const body=await r.json().catch(()=>({error:'No response'}));if(!r.ok)throw Error(body.error||'Rejected '+r.status);return body}
function choices(id,items){const el=q(id),prev=el.value;el.replaceChildren();for(const [value,label] of items){const o=document.createElement('option');o.value=value;o.textContent=label;el.append(o)}if([...el.options].some(x=>x.value===prev))el.value=prev}
function table(headers,rows){const t=document.createElement('table');t.className='test-table';const h=t.insertRow();for(const v of headers){const th=document.createElement('th');th.textContent=v;h.append(th)}for(const row of rows){const tr=t.insertRow();for(const v of row){const td=tr.insertCell();td.textContent=String(v??'')}}return t}
async function load(){const data=await call('state'),p=data.payment_state;
choices('#checkout-fees',p.fees.filter(x=>x.state==='issued'||x.state==='part_paid').map(x=>[x.id,x.member+' — '+x.description+' — '+gbp(x.amount_pence-x.reconciled_pence)]));
choices('#checkout-provider',p.providers.map(x=>[x.code,x.name]));
choices('#adjust-receipts',p.receipts.filter(x=>x.state==='reconciled').map(x=>[x.id,x.provider+' '+x.external_event_id+' '+gbp(x.gross_pence)]));
q('#summary').textContent='Unsettled events: '+data.unsettled+' | Mismatched payouts: '+data.exceptions+' | Recorded refunds: '+gbp(data.refunds_pence)+' | Dispute-open events: '+data.open_dispute_events;
const refs=new Map();for(const a of data.adjustments){if(a.type==='refund')refs.set(a.receipt_id,(refs.get(a.receipt_id)||0)+Number(a.amount_pence))}
const net=new Map();for(const r of p.receipts){if(r.state==='reconciled')net.set(r.fee_id,(net.get(r.fee_id)||0)+Number(r.gross_pence)-(refs.get(r.id)||0))}
q('#fees').replaceChildren(table(['Member','Description','Fee','Net paid after refunds','Outstanding','State'],p.fees.map(f=>[f.member,f.description,gbp(f.amount_pence),gbp(net.get(f.id)||0),gbp(f.amount_pence-(net.get(f.id)||0)),f.state])));
q('#adjustments').replaceChildren(table(['Receipt','Event','Reference','Amount'],data.adjustments.map(a=>[a.receipt_id.slice(0,8),a.type,a.event_id,gbp(a.amount_pence)])));
note.textContent='Synthetic ledger loaded. Provider events and mock links are test-only.'}
q('#checkout-form').addEventListener('submit',async e=>{e.preventDefault();try{const x=Object.fromEntries(new FormData(e.target));const v=await call('checkout','POST',x);const a=q('#checkout-link');a.href=v.url;a.textContent='Open test-only member checkout preview';await load();note.textContent='Mock checkout link issued; expires in 30 minutes.'}catch(err){note.textContent=err.message}});
q('#adjust-form').addEventListener('submit',async e=>{e.preventDefault();try{const x=Object.fromEntries(new FormData(e.target));await call('adjust','POST',{receipt_id:x.receipt_id,event_type:x.event_type,event_id:x.event_id,amount_pence:money(x.pounds)});await load();note.textContent='Simulated provider event recorded.'}catch(err){note.textContent=err.message}});
q('#import-form').addEventListener('submit',async e=>{e.preventDefault();try{const events=JSON.parse(q('#import-json').value);const result=await call('import','POST',{events});await load();note.textContent='Imported '+result.imported+' synthetic provider events.'}catch(err){note.textContent=err.message}});
q('#settlement-import-form').addEventListener('submit',async e=>{e.preventDefault();try{const events=JSON.parse(q('#settlement-import-json').value);const result=await call('import-settlements','POST',{events});await load();note.textContent='Processed '+result.processed+' synthetic payout lines; inspect exceptions below.'}catch(err){note.textContent=err.message}});
load().catch(e=>{note.textContent=e.message});
