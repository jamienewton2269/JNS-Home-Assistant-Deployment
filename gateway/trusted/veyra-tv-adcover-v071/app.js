"use strict";
const $=id=>document.getElementById(id);
let busy=false;
async function api(url,data){
 const opts=data===undefined?{}:{method:"POST",headers:{"X-Veyra-Control":"ad-cover-v070","Content-Type":"application/json"},body:JSON.stringify(data)};
 const r=await fetch(url,opts);const j=await r.json();if(!r.ok)throw Error(j.error||r.status);return j;
}
function render(s){
 $("player").textContent=s.player?"Veyra playback running":"Not running";
 $("status").textContent=s.active?"COVER ACTIVE":"COVER OFF";
 $("state").textContent=s.active?(s.indeterminate?"Waiting for visual return to programme":"Display preview active"):"No cover: watching for provider transition";
 $("audio").textContent="Player audio: "+s.mute;
 $("end").disabled=!s.active||busy;
 $("preview").disabled=s.active||busy;
 document.querySelector(".bar").classList.toggle("active",!!s.active);
}
async function refresh(){try{render(await api("/api/status"));}catch(e){$("notice").textContent="Controller unavailable: "+e.message;}}
async function control(url,msg){
 if(busy)return;busy=true;
 try{render(await api(url,{}));$("notice").textContent=msg;}catch(e){$("notice").textContent=e.message;}finally{busy=false;refresh();}
}
document.addEventListener("DOMContentLoaded",()=>{
 $("preview").addEventListener("click",()=>control("/api/preview","8-second visual preview started."));
 $("end").addEventListener("click",()=>control("/api/end","Cover removed; programme visible."));
 refresh();setInterval(refresh,550);
});