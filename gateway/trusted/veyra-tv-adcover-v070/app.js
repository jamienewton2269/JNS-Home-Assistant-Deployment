"use strict";
const $ = (id)=>document.getElementById(id);
let busy=false, previous=null;
function message(text,err=false){const el=$("notice");el.textContent=text;el.classList.toggle("error",err);}
function draw(s){
  previous=s;
  $("playerstate").textContent=s.player?"PLAYING · SYSTEMD SESSION ACTIVE":"Not running";
  $("statuspill").textContent=s.active?"COVER ACTIVE":"COVER OFF";
  $("statuspill").classList.toggle("on",!!s.active);
  $("remaining").textContent=s.active?Math.ceil(s.remaining)+"s":"—";
  $("countlabel").textContent=s.active?"Estimated time remaining":"Display cover inactive";
  $("fill").style.width=s.active && s.total?Math.round(100*(1-s.remaining/s.total))+"%":"0%";
  $("mute").textContent="Audio: "+(s.mute||"not available")+(s.hdmi==="connected"?" · HDMI connected":" · HDMI "+s.hdmi);
  document.querySelectorAll("[data-seconds]").forEach(b=>{b.disabled=busy||!s.player});
  $("end").disabled=busy||!s.active;
  $("preview").disabled=busy||s.active;
}
async function request(path,data){
 const opts={method:"POST",headers:{"Content-Type":"application/json","X-Veyra-Control":"ad-cover-v070"},body:JSON.stringify(data||{})};
 const res=await fetch(path,opts);const body=await res.json();
 if(!res.ok)throw new Error(body.error||"Controller error "+res.status);
 return body;
}
async function control(path,body,success){
 if(busy)return;
 busy=true;
 if(previous)draw(previous);
 try{
  draw(await request(path,body));
  message(success);
 }catch(e){message(e.message,true);}
 finally{busy=false;if(previous)draw(previous);}
}
async function poll(){
 try{const r=await fetch("/api/status",{cache:"no-store"});if(r.ok)draw(await r.json());}
 catch(e){message("Veyra controller disconnected: "+e.message,true);}
}
document.addEventListener("DOMContentLoaded",()=>{
 document.querySelectorAll("[data-seconds]").forEach(b=>b.addEventListener("click",()=>control("/api/start",{seconds:Number(b.dataset.seconds)},"Cover started; ITVX continues underneath. End early if adverts finish.")));
 $("end").addEventListener("click",()=>control("/api/end",{},"Cover removed. Programme is visible again."));
 $("preview").addEventListener("click",()=>control("/api/preview",{},"8-second visual preview requested. No programme audio change."));
 poll();setInterval(poll,500);
});