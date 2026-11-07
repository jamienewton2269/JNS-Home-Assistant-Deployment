'use strict';
const $=s=>document.querySelector(s);
function b64u(bytes){let t='';for(const b of new Uint8Array(bytes))t+=String.fromCharCode(b);return btoa(t).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');}
function from64(s){s=s.replace(/-/g,'+').replace(/_/g,'/');return Uint8Array.from(atob(s+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));}
async function post(path,body){let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:JSON.stringify(body)});if(!r.ok)throw Error('Authentication unavailable ('+r.status+')');return r.json();}
async function login(e){
 e.preventDefault();const status=$('#status');status.textContent='Touch your security key or approve your passkey…';
 try{
  if(!window.PublicKeyCredential||!navigator.credentials)throw Error('Secure HTTPS browser with passkey support required');
  const officer_id=$('#officer').value.trim();
  const begin=await post('/auth/webauthn/begin',{officer_id});
  const options=begin.options;
  let credential;
  if(PublicKeyCredential.parseRequestOptionsFromJSON)
   credential=await navigator.credentials.get({publicKey:PublicKeyCredential.parseRequestOptionsFromJSON(options)});
  else{
   options.challenge=from64(options.challenge);
   options.allowCredentials=(options.allowCredentials||[]).map(x=>({...x,id:from64(x.id)}));
   credential=await navigator.credentials.get({publicKey:options});
  }
  let response;
  if(typeof credential.toJSON==='function')response=credential.toJSON();
  else response={id:credential.id,rawId:b64u(credential.rawId),type:credential.type,
   response:{clientDataJSON:b64u(credential.response.clientDataJSON),authenticatorData:b64u(credential.response.authenticatorData),signature:b64u(credential.response.signature),
    userHandle:credential.response.userHandle?b64u(credential.response.userHandle):null}};
  await post('/auth/webauthn/complete',{officer_id,challenge_id:begin.challenge_id,response});
  location.assign('/beta');
 }catch(e){status.textContent='Sign-in failed. Check the enrolled security key and try again.';}
}
const routes={dashboard:'/api/v1/dashboard',members:'/api/v1/members',moorings:'/api/v1/moorings',clubhouse:'/api/v1/clubhouse',renewals:'/api/v1/renewals',committee:'/api/v1/committee',security:'/api/v1/security'};

const currency=pence=>'£'+(Number(pence||0)/100).toLocaleString('en-GB',{minimumFractionDigits:2,maximumFractionDigits:2});
function elem(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;}
function panel(parent,title){const n=elem('section',undefined,'data-panel');n.appendChild(elem('h2',title));parent.appendChild(n);return n;}
function metrics(parent,items){const row=elem('div',undefined,'data-metrics');for(const [label,value] of items){const n=elem('div',undefined,'data-metric');n.append(elem('small',label),elem('strong',value));row.appendChild(n);}parent.appendChild(row);}
function table(parent,heads,items){if(!items?.length){parent.appendChild(elem('p','No matching records in this synthetic beta.','empty'));return;}
 const wrap=elem('div',undefined,'table-scroll');const t=elem('table');const h=elem('thead');const hr=elem('tr');for(const k of heads)hr.appendChild(elem('th',k));h.appendChild(hr);t.appendChild(h);const body=elem('tbody');
 for(const values of items.slice(0,100)){const tr=elem('tr');for(const v of values)tr.appendChild(elem('td',v===null||v===undefined?'—':v));body.appendChild(tr);}t.appendChild(body);wrap.appendChild(t);parent.appendChild(wrap);}
function render(section,d){
 const out=$('#result');out.replaceChildren();out.appendChild(elem('h2',({
 dashboard:'Administration dashboard',members:'Membership register',moorings:'Moorings and yard',
 clubhouse:'Clubhouse booking diary',renewals:'Renewals and payments',committee:'Committee accounts',security:'Security and access'
 })[section]));
 if(section==='dashboard'){
  metrics(out,[['Yard assets',d.yard_assets],['Approved mooring bookings',d.approved_mooring_bookings],['Pending mooring requests',d.pending_mooring_requests],['Pending clubhouse requests',d.pending_facility_requests]]);
  const fees=panel(out,'Approved membership tariffs');
  table(fees,['Membership','Annual','Joining'],(d.member_tariffs||[]).map(x=>[x.category,currency(x.annual_pence),currency(x.joining_pence)]));
  const yard=panel(out,'Yard and trailer rates');
  table(yard,['Year','Asset','Basis','Rate'],(d.yard_tariffs||[]).map(x=>[x.year,x.asset_type,x.basis,currency(x.pence_per_unit)]));
 }else if(section==='members'){
  metrics(out,[['Returned membership records',d.length]]);
  const p=panel(out,'Permitted member records (up to 100)');
  table(p,['Member','Email','Category','Version'],d.map(x=>[x.display_name,x.email,x.category,x.version]));
 }else if(section==='moorings'){
  metrics(out,[['Boats and trailers',d.yard_assets],['Approved seasonal allocations',d.allocations]]);
  const a=panel(out,'Mooring locations');table(a,['Designation','Type','Active'],(d.locations||[]).map(x=>[x.designation,x.mooring_type,x.active?'Yes':'No']));
  const b=panel(out,'Bookings');table(b,['Mooring','Start','End','Status','Tariff'],(d.bookings||[]).map(x=>[x.designation,new Date(x.starts_at).toLocaleString('en-GB'),new Date(x.ends_at).toLocaleString('en-GB'),x.state,x.tariff_mode]));
 }else if(section==='clubhouse'){
  const a=panel(out,'Facilities');table(a,['Facility','Available'],(d.facilities||[]).map(x=>[x.name,x.active?'Yes':'No']));
  const b=panel(out,'Booking diary');table(b,['Facility','Event','Start','End','Status'],(d.bookings||[]).map(x=>[x.facility,x.event_title,new Date(x.starts_at).toLocaleString('en-GB'),new Date(x.ends_at).toLocaleString('en-GB'),x.state]));
 }else if(section==='renewals'){
  metrics(out,[['Invoiced',currency(d.invoiced_pence)],['Received',currency(d.paid_pence)]]);
  const a=panel(out,'Annual campaigns');table(a,['Year','Status'],(d.campaigns||[]).map(x=>[x.renewal_year,x.state]));
  const b=panel(out,'Invoice state counts');table(b,['Status','Invoices'],Object.entries(d.invoice_counts||{}));
 }else if(section==='committee'){
  const a=panel(out,'Committee accounts (read-only)');table(a,['Officer','State','Assigned roles'],(d.accounts||[]).map(x=>[x.display_name,x.account_state,(x.roles||[]).join(', ')||'None']));
 }else if(section==='security'){
  metrics(out,[['Preferred factor',d.preferred_factor==='webauthn'?'Passkeys':'Not configured'],['Fallback',String(d.fallback_factor||'—').toUpperCase()],['MFA minutes',d.privileged_session_minutes],['Independent approvers',d.minimum_independent_approvers]]);
  const a=panel(out,'Security operations');
  a.appendChild(elem('p','Pending security approvals: '+d.pending_approval_requests+'. These actions cannot be approved from this read-only beta.'));
 }
 out.appendChild(elem('p','All values come from the permission-checked CT101 read API. Changes, payments and exports are disabled.','data-footnote'));
}
async function load(section){
 const status=$('#status');status.textContent='Loading permission-checked records…';
 const output=$('#result');output.replaceChildren();
 try{
  const r=await fetch(routes[section],{credentials:'same-origin',cache:'no-store'});
  if(r.status===401){location.assign('/login');return;}
  if(r.status===403){status.textContent='You do not have permission to view this section';return;}
  if(!r.ok)throw Error('Unavailable');
  const data=await r.json();render(section,data);
  for(const b of document.querySelectorAll('[data-section]'))b.setAttribute('aria-pressed',String(b.dataset.section===section));
  status.textContent='Read-only · Current officer permissions enforced · 15-minute session';
 }catch(e){status.textContent='Data unavailable. Nothing has changed.';}
}
if($('#login'))$('#login').addEventListener('submit',login);
if($('#sections')){for(const b of document.querySelectorAll('[data-section]'))b.addEventListener('click',()=>load(b.dataset.section));load('dashboard');}
if($('#logout'))$('#logout').addEventListener('click',async()=>{try{await post('/auth/logout',{});location.assign('/login');}catch(e){$('#status').textContent='Sign-out could not be confirmed. Please close this browser and contact the administrator.';}});
