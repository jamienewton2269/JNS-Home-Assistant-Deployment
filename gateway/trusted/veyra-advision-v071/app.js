"use strict";
const $=id=>document.getElementById(id);
let state=null;
function notify(message,error=false){const el=$("notice");el.textContent=message;el.classList.toggle("error",error);}
async function api(path,data){
 const opts={headers:{}};
 if(data!==undefined){
  opts.method="POST";
  opts.headers["X-Veyra-Visual"]="labelled-by-operator";
  opts.headers["Content-Type"]="application/json";
  opts.body=JSON.stringify(data);
 }
 const res=await fetch(path,opts);
 const value=await res.json();
 if(!res.ok)throw Error(value.error||"Server error");
 return value;
}
function show(s){
 state=s;
 $("provider").value=s.provider;
 $("capture").textContent=s.fresh?"CAPTURE ACTIVE":"DISPLAY NOT READY";
 $("capture").style.color=s.fresh?"#6ef4d7":"#ffba98";
 $("activity").textContent=s.capture+" · "+s.frames+" observed frames";
 $("phase").textContent=s.phase==="programme"?"PROGRAMME":"AD BREAK OBSERVED";
 $("mode").textContent=s.mode==="armed"?"ARMED":"OBSERVATION ONLY";
 $("inCount").textContent=s.templates.in;
 $("outCount").textContent=s.templates.out;
 $("enterScore").textContent=Math.round(s.scores.entrance*100)+"%";
 $("exitScore").textContent=Math.round(s.scores.exit*100)+"%";
 // Only enable arming after both visual phases have multiple training examples.
 $("arm").disabled=!(s.fresh&&s.templates.in>=2&&s.templates.out>=2);
 const list=$("events");list.replaceChildren();
 for(const e of s.events){
  const p=document.createElement("p");p.textContent=e.time+" · "+e.text;list.append(p);
 }
}
async function poll(){
 try{show(await api("/api/state"));}catch(e){notify("Observer offline: "+e.message,true);}
}
async function gallery(){
 const box=$("frames");box.textContent="Getting recent virtual-display frames…";
 try{
  const data=await api("/api/frames");box.replaceChildren();
  if(!data.frames.length){box.textContent="Virtual display not yet capturing.";return;}
  for(const f of data.frames){
   const card=document.createElement("div");card.className="frame";
   const img=document.createElement("img");img.src=f.image;img.alt="Recent downscaled virtual-display frame";
   const time=document.createElement("small");time.textContent=f.time.split("T").at(-1);
   const controls=document.createElement("div");controls.className="labels";
   for(const [role,label,cls] of [["in","Ad starts",""],["out","Programme returns","out"]]){
    const b=document.createElement("button");b.className=cls;b.textContent=label;
    b.addEventListener("click",async()=>{
     if(!window.confirm("Confirm that this image is a genuine "+(role==="in"?"advert-entrance":"advert-exit")+" provider graphic, not programme footage?"))return;
     try{await api("/api/teach",{role:role,frame_id:f.id});notify("Saved visual fingerprint for "+label+".");await poll();}
     catch(e){notify(e.message,true);}
    });
    controls.append(b);
   }
   card.append(img,time,controls);box.append(card);
  }
 }catch(e){notify("Could not load recent frames: "+e.message,true);}
}
document.addEventListener("DOMContentLoaded",()=>{
 $("refresh").addEventListener("click",gallery);
 $("provider").addEventListener("change",async e=>{
  try{await api("/api/provider",{provider:e.target.value});await poll();notify("Selected "+e.target.value+"; observation only.");}
  catch(err){notify(err.message,true);}
 });
 $("observe").addEventListener("click",async()=>{
  try{await api("/api/mode",{mode:"observe"});await poll();notify("Observation-only mode. No automatic cover commands.");}
  catch(err){notify(err.message,true);}
 });
 $("arm").addEventListener("click",async()=>{
  if(!window.confirm("Arm automatic visual matching? Only do this after validating BOTH entrance and return images during real breaks. Incorrect recognition may cover the programme."))return;
  try{await api("/api/mode",{mode:"armed"});await poll();notify("Visual matching armed; controller responses appear in event log.");}
  catch(err){notify(err.message,true);}
 });
 $("reset").addEventListener("click",async()=>{
  try{await api("/api/reset-phase",{});await poll();notify("Observer reset to Programme. Cover unchanged.");}
  catch(err){notify(err.message,true);}
 });
 poll();gallery();setInterval(poll,1100);
});