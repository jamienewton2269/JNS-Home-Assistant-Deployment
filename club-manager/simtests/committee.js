'use strict';
const q=s=>document.querySelector(s),gbp=p=>'£'+(Number(p)/100).toFixed(2);
function table(headers,rows){const t=document.createElement('table');t.className='test-table';let r=t.insertRow();for(const h of headers){const x=document.createElement('th');x.textContent=h;r.append(x)}for(const cells of rows){r=t.insertRow();for(const v of cells){const x=r.insertCell();x.textContent=v??'—'}}return t}
(async()=>{
 try{
  const response=await fetch('/sim/committee/reports',{cache:'no-store',credentials:'same-origin'});
  if(!response.ok)throw Error('Authorised committee access required ('+response.status+')');
  const reports=await response.json();if(!reports.length){q('#status').textContent='No completed reporting periods';return}
  const report=reports[0],data=report.summary;
  q('#status').textContent='Latest '+report.type+' period '+report.period_start+' to '+report.period_end+' · Delivery: '+report.delivery_status.replaceAll('_',' ');
  q('#overview').replaceChildren(...[['New charges',gbp(data.new_charges_pence)],
   ['Reconciled receipts',gbp(data.reconciled_gross_pence)],
   ['Provider fees',gbp(data.provider_fees_pence)],
   ['Refunds',gbp(data.refunds_pence)],['Outstanding at generation',gbp(data.outstanding_pence)],
   ['Exceptions',data.reconciliation_exceptions],
   ['Unsettled receipts',data.unsettled_receipts],
   ['Insurance alerts',data.insurance_unresolved]].map(([label,value])=>{
     const section=document.createElement('section');const h=document.createElement('strong');h.textContent=label;
     const p=document.createElement('p');p.textContent=value;section.append(h,p);return section;
   }));
  q('#history').replaceChildren(table(['Period','From','To (exclusive)','New charges','Reconciled gross','Outstanding','Exceptions','Delivery'],reports.map(x=>[x.type,x.period_start,x.period_end,gbp(x.summary.new_charges_pence),gbp(x.summary.reconciled_gross_pence),gbp(x.summary.outstanding_pence),x.summary.reconciliation_exceptions,x.delivery_status])));
 }catch(e){q('#status').textContent=e.message}
})();
