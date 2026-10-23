"use strict";
(function(){
const $=id=>document.getElementById(id);
const providerNames={itvx:"ITVX",iplayer:"BBC iPlayer",channel4:"Channel 4",
 netflix:"Netflix",primevideo:"Prime Video",disney:"Disney+",other:"Other"};
let all=[],filter="all",editing=null,searchSeq=0,searchTimer;
function el(tag,cls,text){
 const n=document.createElement(tag);
 if(cls)n.className=cls;
 if(text!==undefined)n.textContent=String(text);
 return n;
}
function btn(label,action,id,cls){
 const b=el("button",cls,label);
 b.type="button";b.dataset.action=action;b.dataset.id=id;
 return b;
}
function msg(s,error){
 const n=$("notice");n.textContent=s||"";n.classList.toggle("error",!!error);
}
async function api(url,method,data){
 const opt={method:method||"GET",headers:{"Accept":"application/json"}};
 if(data!==undefined){opt.headers["Content-Type"]="application/json";opt.body=JSON.stringify(data);}
 const r=await fetch(url,opt);
 const result=await r.json().catch(()=>({error:"Invalid server response"}));
 if(!r.ok)throw Error(result.error||("HTTP "+r.status));
 return result;
}
async function refresh(){
 try{
  const data=await api("/api/items");
  all=data.items||[];
  $("total").textContent=all.length;
  $("active").textContent=all.filter(x=>x.status==="watching").length;
  $("complete").textContent=all.filter(x=>x.status==="watched").length;
  render();
 }catch(e){msg("Cannot load watchlist: "+e.message,true);}
}
function render(){
 const cont=$("cards");cont.replaceChildren();
 const q=$("filterText").value.toLocaleLowerCase();
 const items=all.filter(x=>(filter==="all"||x.status===filter) &&
    (x.title.toLocaleLowerCase().includes(q)||providerNames[x.provider].toLocaleLowerCase().includes(q)||
       (x.note||"").toLocaleLowerCase().includes(q)));
 if(!items.length){
  const e=el("div","empty");e.append(el("h3",null,all.length?"Nothing matches this view.":"Your next favourite starts here."));
  e.append(el("p",null,all.length?"Try another filter or add another episode.":"Choose Add programme to build a private watchlist."));
  cont.append(e);return;
 }
 for(const x of items){
  const box=el("article","tile");
  const top=el("div","eyeline");
  top.append(el("span","provider",providerNames[x.provider]||"Other"));
  top.append(el("span","state "+x.status,{planned:"UP NEXT",watching:"WATCHING",watched:"WATCHED"}[x.status]));
  box.append(top);
  box.append(el("h3",null,x.title));
  const parts=[x.media_type==="film"?"Film":"Series"];
  if(x.release_year)parts.push(String(x.release_year));
  if(x.media_type==="series"){
    if(x.season!==null)parts.push("Season "+x.season);
    if(x.episode!==null)parts.push("Episode "+x.episode);
  }
  box.append(el("div","subtitle",parts.join(" · ")));
  if(x.note)box.append(el("div","notes",x.note));
  const prog=el("div","meter");
  const fill=el("div","fill");fill.style.width=x.progress+"%";prog.append(fill);box.append(prog);
  const meta=el("div","meta");
  meta.append(el("span",null,x.progress+"% progress"));
  meta.append(el("span",null,x.status==="watched"?"Completed manually":("Updated "+x.updated_at.slice(0,10))));
  box.append(meta);
  const actions=el("div","actions");
  if(x.provider_url){actions.append(btn("Copy link","copy",x.id));}
  if(x.status!=="watched"){
   actions.append(btn("Edit / progress","edit",x.id));
   actions.append(btn("✓ Watched","complete",x.id,"complete"));
  }
  actions.append(btn("History","history",x.id,"dim"));
  actions.append(btn("Archive","archive",x.id,"dim"));
  box.append(actions);
  cont.append(box);
 }
}
function newEditor(x){
 editing=x?x.id:null;
 $("editorTitle").textContent=x?"Edit programme":"Add programme";
 $("form").reset();
 $("title").value=x?x.title:"";
 $("media_type").value=x?x.media_type:"series";
 $("provider").value=x?x.provider:"other";
 $("provider_url").value=x?x.provider_url:"";
 for(const field of ["release_year","season","episode"]){
  $(field).value=x&&x[field]!==null?x[field]:"";
 }
 $("progress").value=x?x.progress:0;
 $("progressLabel").textContent=$("progress").value+"%";
 $("note").value=x?x.note:"";
 $("catalogue_id").value=x?x.catalogue_id:"";
 $("saveBtn").textContent=x?"Save changes":"Add to watchlist";
 $("suggest").replaceChildren();
 toggleEpisode();
 $("editor").showModal();
 $("title").focus();
}
function toggleEpisode(){
 const film=$("media_type").value==="film";
 for(const f of ["season","episode"]){
  $(f).disabled=film;
  $(f).closest("label").style.opacity=film?".4":"1";
 }
}
function toNumber(id){
 const v=$(id).value.trim();return v===""?null:Number(v);
}
async function submit(e){
 e.preventDefault();
 const title=$("title").value.trim();
 if(!title){msg("Enter a programme title.",true);return;}
 const p={
  title:title,media_type:$("media_type").value,provider:$("provider").value,
  provider_url:$("provider_url").value.trim(),release_year:toNumber("release_year"),
  season:toNumber("season"),episode:toNumber("episode"),
  progress:Number($("progress").value),note:$("note").value.trim(),
  catalogue_id:$("catalogue_id").value
 };
 if(p.media_type==="film"){p.season=null;p.episode=null;}
 const save=$("saveBtn");save.disabled=true;
 try{
  if(editing)await api("/api/items/"+editing,"PATCH",p);
  else await api("/api/items","POST",p);
  $("editor").close();
  msg(editing?"Programme updated.":"Programme added to your local watchlist.");
  await refresh();
 }catch(err){msg("Could not save: "+err.message,true);}
 finally{save.disabled=false;}
}
async function action(button){
 const x=all.find(y=>y.id===button.dataset.id),kind=button.dataset.action;
 if(!x)return;
 if(kind==="edit"){newEditor(x);return;}
 if(kind==="copy"){
   if(!x.provider_url){msg("No direct provider link saved.",true);return;}
   try{await navigator.clipboard.writeText(x.provider_url);msg("Link copied. Paste into the virtual ITVX/provider Chrome session.");}
   catch(e){window.prompt("Copy this provider link for the virtual Chrome session:",x.provider_url);}
   return;
 }
 if(kind==="history"){
  try{
   const h=await api("/api/items/"+x.id+"/history");
   const lines=(h.events||[]).map(y=>y.occurred_at+"  "+y.event_type+" — "+y.detail);
   window.alert((x.title+" viewing history\n\n"+lines.join("\n")).slice(0,6000));
  }catch(e){msg("Cannot read history: "+e.message,true);}
  return;
 }
 if(kind==="complete"){
  if(!window.confirm("Have you actually finished watching "+x.title+"?\n\nThis manually marks it watched. It is not based on capture or buffered media."))return;
  try{await api("/api/items/"+x.id+"/complete","POST",{confirmed:true});msg("Marked watched (manual confirmation).");await refresh();}
  catch(e){msg("Unable to complete: "+e.message,true);}
  return;
 }
 if(kind==="archive"){
  if(!window.confirm("Archive "+x.title+"?\nIts history will be retained in Veyra's local database."))return;
  try{await api("/api/items/"+x.id+"/archive","POST",{confirmed:true});msg("Programme archived; history preserved.");await refresh();}
  catch(e){msg("Unable to archive: "+e.message,true);}
 }
}
async function suggest(){
 const out=$("suggest");out.replaceChildren();
 if(editing)return;
 const q=$("title").value.trim();
 if(q.length<2)return;
 const seq=++searchSeq;
 try{
  const r=await api("/api/search?q="+encodeURIComponent(q));
  if(seq!==searchSeq||$("title").value.trim()!==q)return;
  for(const item of r.suggestions||[]){
   const b=el("button",null,item.title+(item.year?" ("+item.year+")":""));
   b.type="button";b.setAttribute("role","option");
   b.addEventListener("click",()=>{
    $("title").value=item.title;
    $("catalogue_id").value=item.catalogue_id||"";
    if(item.year)$("release_year").value=item.year;
    out.replaceChildren();
    msg("Title suggestion selected. Confirm the provider and episode yourself; catalogue availability is not verified.");
   });
   out.append(b);
  }
 }catch(e){/* Manual entry remains available offline. */}
}
document.addEventListener("DOMContentLoaded",()=>{
 $("newBtn").addEventListener("click",()=>newEditor(null));
 $("close").addEventListener("click",()=>$("editor").close());
 $("cancel").addEventListener("click",()=>$("editor").close());
 $("form").addEventListener("submit",submit);
 $("media_type").addEventListener("change",toggleEpisode);
 $("progress").addEventListener("input",()=>$("progressLabel").textContent=$("progress").value+"%");
 $("filterText").addEventListener("input",render);
 for(const b of document.querySelectorAll("[data-filter]")){
  b.addEventListener("click",()=>{
   filter=b.dataset.filter;
   document.querySelectorAll("[data-filter]").forEach(x=>x.classList.toggle("selected",x===b));
   render();
  });
 }
 $("cards").addEventListener("click",e=>{
  const b=e.target.closest("button[data-action]");
  if(b)action(b);
 });
 $("title").addEventListener("input",()=>{
  $("catalogue_id").value="";
  clearTimeout(searchTimer);
  const seq=++searchSeq;
  if(!editing&&$("title").value.trim().length>=2){
   searchTimer=setTimeout(()=>{if(seq===searchSeq)suggest();},350);
  } else $("suggest").replaceChildren();
 });
 refresh();
});
})();
