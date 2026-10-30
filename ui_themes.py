"""Animated voice interfaces ("themes") rendered as self-contained HTML/canvas components.

Truthfulness rules:
* The microphone chip says LISTENING only after the browser's recognition really started.
* The voice chip says SPEAKING only while a real speech-synthesis utterance is playing.
* Waveforms/rings are DECORATIVE and labelled "not live audio".
* Reduced motion (setting or OS preference) and a Pause button stop all animation.
"""
from __future__ import annotations

import json

import voice_service

THEMES: dict[str, dict] = {
    "atlas_core": {"name": "ATLAS CORE", "desc": "Glowing orb, circular energy rings and a waveform on a dark premium background."},
    "neural_wave": {"name": "NEURAL WAVE", "desc": "Large circular waveform with pulsing rings that swell while speaking."},
    "holographic": {"name": "HOLOGRAPHIC CEO", "desc": "Holographic grid, rotating identity rings and floating interface chips."},
    "minimal": {"name": "MINIMAL VOICE", "desc": "A clean central orb with a simple waveform and nothing else."},
    "avatar": {"name": "DIGITAL AVATAR", "desc": "A stylised, non-photorealistic AI avatar with a speaking indicator."},
    "custom": {"name": "CUSTOM STUDIO", "desc": "Pick your own colour, animation intensity and layout."},
}
LAYOUTS = {"orb": "Orb", "ring": "Rings", "bars": "Bars"}
DEFAULT_CUSTOM = {"color": "#22d3ee", "intensity": 60, "layout": "orb"}


def theme_keys() -> list[str]:
    return list(THEMES)


STAGE_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>__CSS__
html,body{height:100%}
body{background:radial-gradient(ellipse at 50% 30%,#10203a 0%,#0a1020 55%,#060a14 100%);overflow:hidden}
#wrap{position:relative;height:100%;display:flex;flex-direction:column;align-items:center;padding:8px 10px}
#cv{width:100%;flex:1 1 auto;min-height:180px;display:block}
#title{position:absolute;top:10px;left:14px;font-size:12px;letter-spacing:.25em;color:#7dd3fc;opacity:.9}
#chips{position:absolute;top:8px;right:10px;text-align:right}
#greet{font-size:clamp(15px,2.6vw,22px);text-align:center;margin:4px 8px 2px;font-weight:600;line-height:1.35}
#sub{font-size:12px;color:#8da2c0;text-align:center;margin:0 8px 6px}
#ctl{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-bottom:4px}
.floaty{position:absolute;padding:5px 11px;border:1px solid rgba(34,211,238,.5);border-radius:6px;background:rgba(8,20,40,.55);font-size:11px;letter-spacing:.12em;color:#7dd3fc;animation:fl 6s ease-in-out infinite;backdrop-filter:blur(2px)}
.floaty:nth-of-type(2){animation-delay:-2s}.floaty:nth-of-type(3){animation-delay:-4s}
@keyframes fl{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.static *{animation:none!important}
@media (max-width:520px){#title{display:none}#chips{position:static;margin-top:28px}.floaty{display:none}}
</style></head><body>
<div id="wrap">
  <div id="title"></div>
  <div id="chips"><span id="cMic" class="chip">Mic: OFF</span><span id="cVoice" class="chip">Voice: IDLE</span><span id="cMode" class="chip warn">Waveform: decorative</span></div>
  <div id="floats"></div>
  <canvas id="cv" aria-label="Animated AI voice interface"></canvas>
  <div id="greet"></div><div id="sub"></div>
  <div id="ctl"><button id="bSpeak">🔊 Speak greeting</button><button id="bMic">🎤 Start listening</button><button id="bPause">⏸ Pause animation</button></div>
</div>
<script>__VOICE_JS__
(function(){
const CFG = __CFG__;
const $ = (id)=>document.getElementById(id);
const mq = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let paused = !!CFG.paused, reduced = !!CFG.reduceMotion || mq;
let micState = "off", voiceState = (CFG.textOnly || !CFG.speakEnabled) ? "disabled" : "idle";
const cv = $("cv"), ctx = cv.getContext("2d");
let W = 0, H = 0, raf = 0, t0 = performance.now() - 1500;   // start mid-cycle so the static frame is not mid-blink
$("title").textContent = (CFG.aiName || "ATLAS").toUpperCase();
$("greet").textContent = CFG.greeting; $("sub").textContent = CFG.subtitle || "";
if(!CFG.showMic) $("bMic").style.display = "none";
if(!CFG.showControls){ $("bSpeak").style.display="none"; $("bPause").style.display="none"; $("bMic").style.display="none"; }
if(CFG.theme === "holographic"){
  ["TASKS","REPORTS","AGENTS"].forEach((n,i)=>{ const d=document.createElement("div"); d.className="floaty"; d.textContent=n;
    d.style.top=(18+i*22)+"%"; d.style[i===1?"right":"left"]=(5+i*3)+"%"; $("floats").appendChild(d); });
}
function hex(c,a){ c=c.replace("#",""); if(c.length===3) c=c.split("").map(x=>x+x).join("");
  const n=parseInt(c,16); return "rgba("+(n>>16&255)+","+(n>>8&255)+","+(n&255)+","+a+")"; }
const PAL = { atlas_core:"#38bdf8", neural_wave:"#22d3ee", holographic:"#34d399", minimal:"#93c5fd", avatar:"#60a5fa" };
const COLOR = CFG.theme==="custom" ? (CFG.color||"#22d3ee") : (PAL[CFG.theme]||"#38bdf8");
function setChip(el,text,cls){ el.textContent=text; el.className="chip "+(cls||""); }
function refreshChips(){
  setChip($("cMic"), micState==="listening"?"Mic: LISTENING":micState==="processing"?"Mic: PROCESSING":"Mic: OFF", micState==="listening"?"on":micState==="processing"?"warn":"");
  setChip($("cVoice"), voiceState==="speaking"?"Voice: SPEAKING":voiceState==="disabled"?"Voice: OFF (text-only)":"Voice: IDLE", voiceState==="speaking"?"ok":"");
  $("bPause").textContent = paused ? "▶ Resume animation" : "⏸ Pause animation";
}
function resize(){ const r=cv.getBoundingClientRect(); const d=Math.min(window.devicePixelRatio||1,2); W=r.width; H=r.height; cv.width=W*d; cv.height=H*d; ctx.setTransform(d,0,0,d,0,0); }
function energy(){ // purely visual: how lively the decoration looks
  const k=(CFG.intensity==null?60:CFG.intensity)/100*1.5;
  const s = voiceState==="speaking"?0.55 : micState==="listening"?0.35 : 0.0;
  return Math.min(1,(0.2+s)*k+0.04);
}
function glow(x,y,r,c0,c1){ const g=ctx.createRadialGradient(x,y,0,x,y,r); g.addColorStop(0,c0); g.addColorStop(1,c1); ctx.fillStyle=g; ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.fill(); }
function bars(t,e,y,wFrac,n,hMax){ const w=W*wFrac, x0=(W-w)/2, bw=w/n;
  for(let i=0;i<n;i++){ const a=(Math.sin(t*3+i*.55)+Math.sin(t*1.7+i*.9)+2)/4; const h=3+a*e*hMax;
    ctx.fillStyle=hex(COLOR,.35+.5*a); ctx.fillRect(x0+i*bw+1,y-h/2,Math.max(1,bw-2),h); } }
function orb(t,e,cx,cy,R){ const R2=R*(1+.05*Math.sin(t*2.2)*(e*3));
  glow(cx,cy,R2*2.4,hex(COLOR,.28),hex(COLOR,0)); glow(cx,cy,R2,"rgba(235,250,255,.95)",hex(COLOR,.9)); }
function rings(t,e,cx,cy,R,n){ ctx.lineWidth=2; for(let i=0;i<n;i++){ const rad=R*(1.45+i*.38); ctx.strokeStyle=hex(COLOR,.55-i*.12);
  for(let s=0;s<4;s++){ const a=t*(.4+.2*i)*(i%2?-1:1)+s*Math.PI/2; ctx.beginPath(); ctx.arc(cx,cy,rad,a,a+1.1); ctx.stroke(); } } }
function dCore(t,e){ const cx=W/2, cy=H*.45, R=Math.min(W,H)*.16; orb(t,e,cx,cy,R); rings(t,e,cx,cy,R,3); bars(t,e,H*.9,.7,48,H*.1); }
function dNeural(t,e){ const cx=W/2, cy=H*.5, R0=Math.min(W,H)*.22; const N=200;
  for(let k=0;k<3;k++){ const ph=(t*.5+k/3)%1; ctx.strokeStyle=hex(COLOR,(1-ph)*.4); ctx.lineWidth=2; ctx.beginPath(); ctx.arc(cx,cy,R0*(1.2+ph*.9),0,Math.PI*2); ctx.stroke(); }
  for(let l=0;l<2;l++){ ctx.beginPath(); for(let i=0;i<=N;i++){ const a=i/N*Math.PI*2; const m=Math.sin(a*6+t*3+l)*.5+Math.sin(a*11-t*2)*.3+Math.sin(a*3+t)*.2;
    const r=R0*(1+.02*l)+e*R0*.38*m; const x=cx+Math.cos(a)*r, y=cy+Math.sin(a)*r; i?ctx.lineTo(x,y):ctx.moveTo(x,y); }
    ctx.closePath(); ctx.strokeStyle=hex(l?"#34d399":COLOR,l?.55:.95); ctx.lineWidth=l?1.5:2.5; ctx.stroke(); }
  glow(cx,cy,R0*.55,hex(COLOR,.25),hex(COLOR,0)); }
function dHolo(t,e){ const cx=W/2, cy=H*.42, hz=H*.66;
  ctx.lineWidth=1; for(let i=0;i<9;i++){ const p=Math.pow((i+((t*.3)%1))/9,2); const y=hz+(H-hz)*p; ctx.strokeStyle=hex(COLOR,.1+.3*p); ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }
  for(let i=-10;i<=10;i++){ ctx.strokeStyle=hex(COLOR,.18); ctx.beginPath(); ctx.moveTo(cx+i*8,hz); ctx.lineTo(cx+i*W*.09,H); ctx.stroke(); }
  const R=Math.min(W,H)*.2; ctx.lineWidth=2;
  for(let k=0;k<3;k++){ ctx.strokeStyle=hex(COLOR,.7-k*.15); ctx.beginPath(); ctx.ellipse(cx,cy,R*(1+k*.18),Math.max(2,R*(1+k*.18)*Math.abs(Math.cos(t*.6+k*1.1))),k*.6+t*.2,0,Math.PI*2); ctx.stroke(); }
  glow(cx,cy,R*.9,hex(COLOR,.22+e*.2),hex(COLOR,0));
  ctx.fillStyle=hex("#e0fff4",.95); ctx.font="600 "+Math.round(R*.32)+"px ui-monospace,monospace"; ctx.textAlign="center"; ctx.textBaseline="middle";
  ctx.fillText((CFG.aiName||"ATLAS").toUpperCase().slice(0,10),cx,cy);
  ctx.fillStyle=hex(COLOR,.06); for(let y=0;y<H;y+=4) ctx.fillRect(0,y,W,1); }
function dMinimal(t,e){ const cx=W/2, cy=H*.45; orb(t,e*.7,cx,cy,Math.min(W,H)*.13);
  ctx.strokeStyle=hex(COLOR,.7); ctx.lineWidth=2; ctx.beginPath(); const y0=H*.82;
  for(let x=0;x<=W;x+=4){ const env=Math.sin(x/W*Math.PI); const y=y0+Math.sin(x*.03+t*4)*e*H*.06*env; x?ctx.lineTo(x,y):ctx.moveTo(x,y); } ctx.stroke(); }
function dAvatar(t,e){ const cx=W/2, cy=H*.46, R=Math.min(W,H)*.2; const sp=voiceState==="speaking";
  glow(cx,cy,R*1.9,hex(COLOR,.18),hex(COLOR,0));
  const g=ctx.createLinearGradient(cx,cy-R,cx,cy+R); g.addColorStop(0,"#16305a"); g.addColorStop(1,"#0c1a33");
  ctx.fillStyle=g; ctx.strokeStyle=hex(COLOR,.9); ctx.lineWidth=3; ctx.beginPath(); ctx.arc(cx,cy,R,0,Math.PI*2); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.arc(cx,cy,R*1.12,Math.PI*1.05,Math.PI*1.95); ctx.stroke();                                   // headset
  const blink=(t%4)<.12?.12:1; ctx.fillStyle=hex("#bff3ff",.95);
  [-1,1].forEach(s=>{ ctx.beginPath(); ctx.ellipse(cx+s*R*.36,cy-R*.12,R*.12,R*.12*blink,0,0,Math.PI*2); ctx.fill(); });
  const open=sp?R*.05+R*.14*Math.abs(Math.sin(t*12))*(.5+e):R*.025; ctx.fillStyle=hex(COLOR,.95);
  ctx.beginPath(); ctx.ellipse(cx,cy+R*.42,R*.22,open,0,0,Math.PI*2); ctx.fill();
  const ax=cx, ay=cy-R*1.45; ctx.strokeStyle=hex(COLOR,.7); ctx.beginPath(); ctx.moveTo(cx,cy-R); ctx.lineTo(ax,ay); ctx.stroke();
  glow(ax,ay,R*.1+R*.04*Math.sin(t*4),sp?"#34d399":hex(COLOR,.9),hex(COLOR,0)); }
function dCustom(t,e){ const L=CFG.layout||"orb", cx=W/2, cy=H*.45, R=Math.min(W,H)*.15;
  if(L==="orb"){ orb(t,e,cx,cy,R); bars(t,e,H*.9,.5,32,H*.08); }
  else if(L==="ring"){ orb(t,e*.6,cx,cy,R*.7); rings(t,e,cx,cy,R*.9,4); }
  else { bars(t,e,H*.45,.85,64,H*.45); } }
const DRAW={atlas_core:dCore,neural_wave:dNeural,holographic:dHolo,minimal:dMinimal,avatar:dAvatar,custom:dCustom};
function frame(now){ const t=(now-t0)/1000; ctx.clearRect(0,0,W,H); (DRAW[CFG.theme]||dCore)(t,energy());
  if(!paused && !reduced) raf=requestAnimationFrame(frame); else raf=0; }
function kick(){ cancelAnimationFrame(raf); raf=requestAnimationFrame(frame); }
function applyStatic(){ document.body.classList.toggle("static", paused||reduced); }
window.addEventListener("resize",()=>{resize();kick();});
$("bPause").onclick=()=>{ paused=!paused; applyStatic(); refreshChips(); kick(); };
const PREFS = CFG.voice;
$("bSpeak").onclick=()=>{
  if(!PREFS.speakEnabled){ setChip($("cVoice"),"Voice: OFF (enable spoken responses in Voice Settings)","warn"); return; }
  AtlasVoice.speak(CFG.greeting, PREFS, {onstart:()=>{voiceState="speaking";refreshChips();kick();}, onend:()=>{voiceState="idle";refreshChips();kick();},
    onerror:(e)=>{voiceState="idle";refreshChips();setChip($("cVoice"),"Voice: "+(e==="not-allowed"?"blocked by browser - press Speak":"error "+e),"warn");}});
};
$("bMic").onclick=()=>{
  if(!AtlasVoice.micSupported()){ setChip($("cMic"),"Mic: not supported here","warn"); return; }
  AtlasVoice.listen(PREFS.lang,{onstart:()=>{micState="listening";refreshChips();kick();}, onprocessing:()=>{micState="processing";refreshChips();},
    onresult:(txt)=>{ $("sub").textContent='Heard: "'+txt+'"'; }, onerror:(e)=>{micState="off";refreshChips();setChip($("cMic"),"Mic: OFF ("+e+")","bad");},
    onend:()=>{micState="off";refreshChips();kick();}});
};
if(!AtlasVoice.supported()){ $("bSpeak").disabled=true; voiceState="disabled"; }
if(!AtlasVoice.micSupported()){ $("bMic").title="Speech recognition is not supported in this browser"; $("bMic").disabled=true; }
if(reduced){ $("sub").textContent=($("sub").textContent+" (reduced motion: animation is static)").trim(); }
resize(); applyStatic(); refreshChips(); kick();
window.__atlasReady = true;
if(CFG.autoSpeak && PREFS.speakEnabled && PREFS.autoSpeak){ setTimeout(()=>$("bSpeak").click(),600); }
})();
</script></body></html>"""


def stage_html(theme: str, *, ai_name: str, greeting: str, subtitle: str = "", custom: dict | None = None,
               reduce_motion: bool = False, paused: bool = False, show_controls: bool = True,
               show_mic: bool = True, autospeak: bool = False, prefs: dict | None = None) -> str:
    """Self-contained HTML for one animated voice interface."""
    if theme not in THEMES:
        theme = "atlas_core"
    custom = {**DEFAULT_CUSTOM, **(custom or {})}
    prefs = prefs or voice_service.get_prefs()
    cfg = {
        "theme": theme, "aiName": ai_name, "greeting": greeting, "subtitle": subtitle,
        "color": custom["color"], "intensity": int(custom["intensity"]), "layout": custom["layout"],
        "reduceMotion": reduce_motion, "paused": paused, "showControls": show_controls,
        "showMic": show_mic, "autoSpeak": autospeak, "textOnly": prefs.get("textOnly", False),
        "speakEnabled": prefs.get("speakEnabled", False), "voice": prefs,
    }
    return (STAGE_TEMPLATE.replace("__CSS__", voice_service._BASE_CSS)
            .replace("__VOICE_JS__", voice_service.VOICE_JS)
            .replace("__CFG__", voice_service.js_json(cfg)))
