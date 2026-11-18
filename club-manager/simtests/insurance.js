'use strict';
const q=s=>document.querySelector(s);
function table(labels,rows){const t=document.createElement('table');t.className='test-table';const h=t.insertRow();for(const s of labels){const x=document.createElement('th');x.textContent=s;h.append(x)}for(const row of rows){const r=t.insertRow();for(const s of row){const x=r.insertCell();x.textContent=s===null?'—':String(s)}}return t}
(async()=>{
 try{
  const response=await fetch('/sim/insurance/reports',{cache:'no-store',credentials:'same-origin'});
  if(!response.ok)throw Error('Officer access or report unavailable ('+response.status+')');
  const rows=await response.json();
  if(rows.length===0){q('#status').textContent='No reports generated yet';return}
  const r=rows[0],data=r.summary;
  q('#status').textContent='Report '+r.report_date+' · Delivery: '+r.delivery_status.replaceAll('_',' ')+' · No live email sent';
  q('#totals').replaceChildren(...[['Vessels',data.total_vessels],['Missing',data.missing],['Unverified',data.unverified],['Expired',data.expired],['Renewal within month',data.renewal_due],['Current',data.current]].map(([label,n])=>{
   const section=document.createElement('section');const heading=document.createElement('strong');heading.textContent=label;
   const count=document.createElement('p');count.textContent=String(n);section.append(heading,count);return section;
  }));
  q('#alerts').replaceChildren(table(['Vessel','Member','Reason','Cover expires'],data.alerts.map(x=>[x.vessel,x.member,x.status,x.cover_until])));
  q('#history').replaceChildren(table(['Date','Vessels','Missing','Unverified','Expired','Due within month','Delivery'],rows.map(x=>[x.report_date,x.summary.total_vessels,x.summary.missing,x.summary.unverified,x.summary.expired,x.summary.renewal_due,x.delivery_status])));
 }catch(e){q('#status').textContent=e.message}
})();
