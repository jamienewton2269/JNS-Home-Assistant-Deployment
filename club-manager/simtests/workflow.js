'use strict';
const q=s=>document.querySelector(s);
const status=q('#status');
let tariffSchedule=[];
let locationTariffs=[];
function localDateTime(date){const pad=n=>String(n).padStart(2,'0');return [date.getFullYear(),pad(date.getMonth()+1),pad(date.getDate())].join('-')+'T'+pad(date.getHours())+':'+pad(date.getMinutes())}
function updateDeparture(){
 const arrival=q('#arrival-time').value, weeks=q('input[name=stay_duration]:checked').value;
 if(!arrival)return;
 if(weeks!=='custom'){const d=new Date(arrival);d.setDate(d.getDate()+Number(weeks)*7);q('#departure-time').value=localDateTime(d)}
 updateQuote();
}
function updateQuote(){
 const start=q('#arrival-time').value, end=q('#departure-time').value, note=q('#booking-quote');
 if(!start||!end){note.textContent='Select arrival and departure';return}
 const a=new Date(start),b=new Date(end);
 const days=(b-a)/86400000;
 if(!Number.isFinite(days)||days<=0){note.textContent='Departure must be after arrival';return}
 // Compare local calendar-clock values, not absolute UTC seconds:
 // the daylight-saving transition must not create an extra charged week.
 const localA=Date.UTC(a.getFullYear(),a.getMonth(),a.getDate(),a.getHours(),a.getMinutes());
 const localB=Date.UTC(b.getFullYear(),b.getMonth(),b.getDate(),b.getHours(),b.getMinutes());
 const weeks=Math.ceil((localB-localA)/604800000);
 const iso=localDateTime(a).slice(0,10);
 const mooring=q('#location-choice').value;
 const price=locationTariffs.find(r=>r.location_id===mooring&&r.effective_from<=iso) || tariffSchedule.find(r=>r.effective_from<=iso);
 note.textContent=price?'Estimated: '+weeks+' charged week(s) × '+gbp(price.weekly_pence)+' = '+gbp(weeks*price.weekly_pence):'No applicable weekly tariff — ask Finance to set one.';
}
const arrival=q('#arrival-time'),departure=q('#departure-time');
arrival.value=localDateTime(new Date());updateDeparture();
arrival.addEventListener('change',updateDeparture);q('#location-choice').addEventListener('change',updateQuote);
document.querySelectorAll('input[name=stay_duration]').forEach(r=>r.addEventListener('change',updateDeparture));
departure.addEventListener('change',()=>{q('input[name=stay_duration][value=custom]').checked=true;updateQuote()});

function cell(text){const td=document.createElement('td');td.textContent=String(text??'');return td}
function table(headers,rows){const t=document.createElement('table');t.className='test-table';const h=document.createElement('tr');for(const label of headers){const th=document.createElement('th');th.textContent=label;h.append(th)}t.append(h);for(const cells of rows){const tr=document.createElement('tr');for(const v of cells)tr.append(typeof v==='string'?cell(v):v);t.append(tr)}return t}
async function api(path,method='GET',payload){const r=await fetch('/sim/api/'+path,{method,headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:payload?JSON.stringify(payload):undefined});if(!r.ok){if(r.status===401||r.status===403)throw Error('No permission or session expired ('+r.status+'). Return to simulation login.');const err=await r.json().catch(()=>({error:'Request rejected'}));throw Error(err.error||'Operation rejected ('+r.status+')')}return r.json()}
const gbp=p=>'£'+(Number(p)/100).toFixed(2);
function selectOptions(node,records,label){const selected=node.value;node.replaceChildren();for(const r of records){const o=document.createElement('option');o.value=r.id;o.textContent=r[label];node.append(o)}if([...node.options].some(o=>o.value===selected))node.value=selected}
async function load(){const d=await api('state');selectOptions(q('#member-choice'),d.members,'name');selectOptions(q('#location-choice'),d.locations,'designation');
locationTariffs=(d.location_rates||[]).slice().sort((a,b)=>b.effective_from.localeCompare(a.effective_from));
tariffSchedule=d.rates.slice().sort((a,b)=>b.effective_from.localeCompare(a.effective_from));
const today=localDateTime(new Date()).slice(0,10);const applicable=tariffSchedule.find(x=>x.effective_from<=today);
q('#current-rate').textContent=applicable?gbp(applicable.weekly_pence)+' per week':'Not configured';
q('#rate-summary').textContent='Tariff schedule (view-only): '+(tariffSchedule.map(x=>x.effective_from+' — '+gbp(x.weekly_pence)).join('; ')||'None');
updateQuote();
q('#members').replaceChildren(table(['Member','Email','Category'],d.members.map(m=>[m.name,m.email,m.category])));
const bookings=d.bookings.map(b=>{const action=document.createElement('span');if(b.status==='requested'){const button=document.createElement('button');button.textContent='Approve';button.onclick=()=>change('approve',{booking_id:b.id});action.append(button)}else action.textContent='—';return [b.member,b.location,new Date(b.starts).toLocaleString('en-GB'),new Date(b.ends).toLocaleString('en-GB'),gbp(b.total_pence),b.status,action]});
q('#bookings').replaceChildren(table(['Member','Mooring','Start','End','Total','Status','Action'],bookings));status.textContent='Ready · Synthetic PostgreSQL data · ITAdmin1 permissions checked'}
async function change(action,payload){status.textContent='Saving synthetic transaction…';try{await api(action,'POST',payload);await load();status.textContent='Saved in simulation database; refresh complete.'}catch(e){status.textContent=e.message}}
function attach(form,action,map){q(form).addEventListener('submit',e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));change(action,map?map(data):data)})}
attach('#member-form','member');
attach('#request-form','request',d=>({member_id:d.member_id,location_id:d.location_id,starts:new Date(d.starts).toISOString(),ends:new Date(d.ends).toISOString()}));

load().catch(e=>{status.textContent=e.message});
