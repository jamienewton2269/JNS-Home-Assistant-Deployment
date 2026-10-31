/* JNS Temperature Timeline v0.1: native Lovelace custom-card.
 * Uses the signed-in HA frontend's callApi; no external services or tokens.
 * Read-only recorder history; dashed forecast is NOT historical observation.
 */
class JNSTemperatureTimelineCard extends HTMLElement {
  setConfig(config) {
    if (!config || !Array.isArray(config.series) || !config.series.length)
      throw new Error("JNS temperature timeline needs a non-empty series array");
    this.cfg = config;
    this.series = config.series.filter(x => typeof x.entity === "string" &&
       /^sensor\.[a-z0-9_]+$/.test(x.entity)).slice(0,16);
    if (!this.series.length) throw new Error("No valid temperature entities");
    this.hours = config.hours === 168 ? 168 : 24;
    this._lastFetch = 0;
    this._history = [];
    if (!this.shadowRoot) this.attachShadow({mode:"open"});
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot || !this.cfg) return;
    const now = Date.now();
    if (!this._lastRender || now - this._lastRender > 10000) {
      this._lastRender = now;
      this.render();
    }
    if (!this._busy && now - this._lastFetch > 60000) this.load();
  }
  getCardSize() {return 6;}
  async load() {
    if (!this._hass || this._busy) return;
    this._busy = true;
    this._lastFetch = Date.now();
    const start = new Date(Date.now()-this.hours*3600000).toISOString();
    const end = new Date().toISOString();
    const ids = this.series.map(x=>x.entity).join(",");
    try {
      const path = "history/period/" + encodeURIComponent(start) +
        "?end_time=" + encodeURIComponent(end) +
        "&filter_entity_id=" + encodeURIComponent(ids) +
        "&minimal_response&no_attributes";
      const data = await this._hass.callApi("GET",path);
      if (!Array.isArray(data)) throw new Error("History API format unavailable");
      const grouped = {};
      data.forEach((group,i) => {
        if (!Array.isArray(group) || !group.length) return;
        const key = group[0].entity_id || this.series[i]?.entity;
        if (key) grouped[key] = group;
      });
      this._history = this.series.map(s => {
        const rows = grouped[s.entity] || [];
        const points = [];
        rows.forEach(p=>{
          const t=Date.parse(p.last_changed || p.last_updated);
          const y=Number(p.state);
          if (Number.isFinite(t) && Number.isFinite(y) && y >= -30 && y <= 70)
            points.push({t,y});
        });
        return points;
      });
      this._error = "";
    } catch (e) {
      this._error = "History not available; current readings shown";
    } finally {
      this._busy=false;
      this.render();
    }
  }
  render() {
    if (!this._hass || !this.shadowRoot) return;
    const now=Date.now(), start=now-this.hours*3600000, finish=now+3600000;
    const w=940,h=260,left=50,right=15,top=16,bottom=36;
    const colors=["#38bdf8","#fb923c","#c084fc","#a3e635","#f472b6",
      "#facc15","#2dd4bf","#f87171","#818cf8","#d4d4d8","#86efac","#fda4af"];
    const rows = this.series.map((s,i)=>{
      const state=this._hass.states[s.entity];
      const live=state?Number(state.state):NaN;
      const data=(this._history[i]||[]).filter(p=>p.t>=start && p.t<=now);
      if (Number.isFinite(live) && live>=-30 && live<=70) data.push({t:now,y:live});
      return {s, data,live,color:colors[i%colors.length]};
    });
    const preds=[];
    rows.forEach((r,i)=>{
      const fc=r.s.forecast_entity?this._hass.states[r.s.forecast_entity]:null;
      const val=fc?Number(fc.state):NaN;
      const valid=fc && fc.attributes && fc.attributes.validated===true &&
         fc.attributes.source_epoch==="hallway-precision-v1";
      if (valid && Number.isFinite(val) && val>=-30 && val<=70 &&
          Number.isFinite(r.live))preds.push({i,from:r.live,to:val,color:r.color});
    });
    const all=rows.flatMap(r=>r.data.map(p=>p.y)).concat(preds.flatMap(p=>[p.from,p.to]));
    const ymin=all.length?Math.floor(Math.min(...all)-1):0;
    const ymax=all.length?Math.ceil(Math.max(...all)+1):30;
    const low=Math.max(-30,ymin),high=Math.min(70,Math.max(ymax,low+3));
    const x=t=>left+(t-start)/(finish-start)*(w-left-right);
    const y=v=>top+(high-v)/(high-low)*(h-top-bottom);
    const path=pts=>pts.map((p,i)=>(i?"L":"M")+x(p.t).toFixed(1)+","+
       y(p.y).toFixed(1)).join(" ");
    const escape=s=>String(s).replace(/[&<>"']/g,c=>({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    })[c]);
    let svg="";
    for(let step=0;step<=4;step++){
      const temp=low+(high-low)*step/4;
      const py=y(temp);
      svg+='<line x1="'+left+'" x2="'+(w-right)+'" y1="'+py+'" y2="'+py+
        '" stroke="currentColor" opacity=".12"/>'+
        '<text x="6" y="'+(py+4)+'" font-size="13" fill="currentColor">'+
        temp.toFixed(1)+'°</text>';
    }
    for(const hour of [this.hours, Math.round(this.hours*.75),
                       Math.round(this.hours*.5),Math.round(this.hours*.25),0]){
      const t=now-hour*3600000;
      svg+='<text x="'+x(t).toFixed(1)+'" y="'+(h-8)+
        '" font-size="12" text-anchor="middle" fill="currentColor">'+
        (hour?'-'+hour+'h':'NOW')+'</text>';
    }
    svg+='<line x1="'+x(now)+'" x2="'+x(now)+'" y1="'+top+
      '" y2="'+(h-bottom)+'" stroke="currentColor" stroke-dasharray="3 5" opacity=".6"/>';
    rows.forEach(r=>{
      if(r.data.length>1)
        svg+='<path d="'+path(r.data)+'" fill="none" stroke="'+r.color+
          '" stroke-width="2.5" vector-effect="non-scaling-stroke"/>';
    });
    preds.forEach(p=>{
      const f=[{t:now,y:p.from},{t:now+3600000,y:p.to}];
      svg+='<path d="'+path(f)+'" fill="none" stroke="'+p.color+
        '" stroke-width="2.5" stroke-dasharray="7 5"/>'+
        '<circle cx="'+x(now+3600000)+'" cy="'+y(p.to)+
        '" r="4" fill="'+p.color+'"/>';
    });
    const legend=rows.map(r=>{
      const current=Number.isFinite(r.live)?r.live.toFixed(1)+'°C':"Unavailable";
      const fc=r.s.forecast_entity;
      const eligible=preds.some(p=>rows[p.i]===r);
      return '<span class="legend"><b style="color:'+r.color+'">●</b> '+
        escape(r.s.name||r.s.entity)+': <strong>'+current+'</strong>'+
        (fc?(eligible?' · forecast shown':' · forecast unavailable'):'')+'</span>';
    }).join("");
    this.shadowRoot.innerHTML='<style>'+
      ':host{display:block}ha-card{padding:16px;color:var(--primary-text-color)}'+
      'h3{margin:0 0 8px;font-size:17px}svg{width:100%;height:auto;display:block}'+
      '.legendbox{display:flex;gap:8px 16px;flex-wrap:wrap;margin-top:8px}'+
      '.legend{font-size:12px;white-space:nowrap}footer{color:var(--secondary-text-color);'+
      'font-size:12px;margin-top:10px}</style>'+
      '<ha-card><h3>'+escape(this.cfg.title||"JNS Temperature Timeline")+'</h3>'+
      '<svg role="img" aria-label="Historical temperature lines, dashed future forecasts"'+
      ' viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="xMidYMid meet">'+svg+'</svg>'+
      '<div class="legendbox">'+legend+'</div><footer>'+
      'Solid = measured history. Dashed = validated prediction (next 60 min). '+
      escape(this._error||"")+'</footer></ha-card>';
  }
}
if(!customElements.get("jns-temperature-timeline-card"))
  customElements.define("jns-temperature-timeline-card",JNSTemperatureTimelineCard);
