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
async function load(section){
 const status=$('#status');status.textContent='Reading authorised club data…';
 const output=$('#result');output.replaceChildren();
 try{
  const r=await fetch(routes[section],{credentials:'same-origin',cache:'no-store'});
  if(r.status===401){location.assign('/login');return;}
  if(r.status===403){status.textContent='Your account does not have this permission';return;}
  if(!r.ok)throw Error('Backend unavailable');
  const data=await r.json();const pre=document.createElement('pre');pre.textContent=JSON.stringify(data,null,2);output.appendChild(pre);
  status.textContent='Read only · Current permissions enforced · 15-minute maximum session';
 }catch(e){status.textContent='Data unavailable. No changes were made.';}
}
if($('#login'))$('#login').addEventListener('submit',login);
if($('#sections')){for(const b of document.querySelectorAll('[data-section]'))b.addEventListener('click',()=>load(b.dataset.section));load('dashboard');}
if($('#logout'))$('#logout').addEventListener('click',async()=>{try{await post('/auth/logout',{});}catch(e){}finally{location.assign('/login');}});
