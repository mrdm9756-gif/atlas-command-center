"""Voice support.

Speech synthesis and recognition happen in the USER'S BROWSER (Web Speech API), not on the server.
The server only stores preferences (gender, language, speed, pitch, on/off flags) and renders small
HTML components that talk to the browser APIs.

Honesty rules baked in:
* The voice list is read from the device at run time - we never assume which voices exist.
* "Male"/"female" is a best-effort guess from the voice's NAME (browsers do not expose gender).
  Voices we cannot classify are shown as "gender not identified".
* If no voice matches the preference, the closest available voice is used and the UI says so.
* The microphone state is driven by real recognition events: it is never shown as "listening"
  unless the browser actually started listening.
* Premium cloud voices: see CloudVoiceProvider below (optional adapter, nothing hard-coded).
"""
from __future__ import annotations

import html
import json
from abc import ABC, abstractmethod

import database as dbm

LANGUAGES = {
    "en": "English", "fil": "Filipino / Tagalog", "es": "Spanish", "fr": "French", "de": "German",
    "pt": "Portuguese", "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "hi": "Hindi", "ar": "Arabic",
    "id": "Indonesian", "it": "Italian", "ru": "Russian",
}


def get_prefs() -> dict:
    """Voice preferences as saved in the database (safe to embed in HTML)."""
    return {
        "gender": dbm.get_setting("voice_gender"),
        "lang": dbm.get_setting("voice_lang"),
        "rate": dbm.get_float("voice_rate", 1.0),
        "pitch": dbm.get_float("voice_pitch", 1.0),
        "speakEnabled": dbm.get_bool("speak_enabled") and not dbm.get_bool("text_only"),
        "autoSpeak": dbm.get_bool("auto_speak") and not dbm.get_bool("text_only"),
        "textOnly": dbm.get_bool("text_only"),
    }


def js_json(obj) -> str:
    """JSON that is safe inside a <script> block."""
    return json.dumps(obj).replace("</", "<\\/").replace("<!--", "<\\!--")


# --------------------------------------------------------------------------- #
# Optional premium cloud voice adapter (not implemented on purpose)
# --------------------------------------------------------------------------- #
class CloudVoiceProvider(ABC):
    """Adapter interface for paid TTS (ElevenLabs, Azure, Google Cloud TTS, ...).

    Subclass it, read the API key via config.get_secret("YOUR_KEY") (never hard-code or display it),
    and return audio bytes from synthesize(). The MVP ships NO implementation, so cloud voices are
    reported as "not configured".
    """
    name = "cloud"

    @abstractmethod
    def synthesize(self, text: str, voice: str, language: str) -> bytes:
        """Return audio bytes (e.g. MP3)."""


def cloud_voice_status() -> dict:
    return {"configured": False, "message": "No premium cloud voice provider is configured. "
            "The free browser voices on this device are used instead (see README, 'Premium voices')."}


# --------------------------------------------------------------------------- #
# Browser-side helper library (shared by every component)
# --------------------------------------------------------------------------- #
VOICE_JS = r"""
window.AtlasVoice = (function () {
  const FEMALE = /\b(female|woman|zira|samantha|victoria|karen|moira|tessa|fiona|susan|hazel|aria|jenny|michelle|ava|allison|joanna|salli|kendra|kimberly|ivy|emma|amy|nicole|libby|sonia|natasha|serena|helena|laura|catherine|linda|heather|zoe|monica|paulina|luciana|melina|elsa|julia|sabina|ana|blessica|rosa|angelina|joana|raquel|marie|hortense|denise|katja|amala)\b/i;
  const MALE = /\b(male|man|david|mark|daniel|alex|fred|tom|george|james|guy|ryan|brian|matthew|justin|joey|russell|geraint|oliver|jorge|diego|thomas|rishi|aaron|arthur|bruce|lee|rocko|reed|eddy|ricardo|jorge|henri|claude|stefan|conrad|antonio|fabrizio|luca|mateo|jaime|enrique|albert|ralph|junior|nathan|alvaro)\b/i;
  function classify(v) {
    const n = v.name || "";
    if (FEMALE.test(n)) return "female";
    if (MALE.test(n)) return "male";
    return "unknown";
  }
  function supported() { return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window; }
  function load() {
    return new Promise((resolve) => {
      if (!supported()) return resolve([]);
      const s = window.speechSynthesis;
      const now = s.getVoices();
      if (now && now.length) return resolve(now);
      const t = setTimeout(() => resolve(s.getVoices() || []), 1500);
      s.addEventListener("voiceschanged", () => { clearTimeout(t); resolve(s.getVoices() || []); }, { once: true });
    });
  }
  function saved() { try { return localStorage.getItem("atlas_voice_name") || ""; } catch (e) { return ""; } }
  function save(name) { try { if (name) localStorage.setItem("atlas_voice_name", name); else localStorage.removeItem("atlas_voice_name"); } catch (e) {} }
  function pick(prefs, voices) {
    if (!voices.length) return { voice: null, note: "No speech voices were found on this device. Text-only mode is still available." };
    const want = prefs.gender || "any";
    const lang = (prefs.lang || "en").toLowerCase();
    const byLang = (v) => (v.lang || "").toLowerCase().startsWith(lang) || (lang === "fil" && /^(fil|tl)/i.test(v.lang || ""));
    const name = saved();
    if (name) {
      const v = voices.find((x) => x.name === name);
      if (v) return { voice: v, note: "Using the voice you chose on this device: " + v.name };
    }
    const g = (v) => classify(v);
    let c = voices.filter((v) => byLang(v) && (want === "any" || g(v) === want));
    if (c.length) return { voice: c[0], note: want === "any" ? "Using " + c[0].name : "Using " + c[0].name + " (" + want + " voice, guessed from its name)" };
    c = voices.filter((v) => want !== "any" && g(v) === want);
    if (c.length) return { voice: c[0], note: "No " + want + " voice for this language was found. Closest option: " + c[0].name + " (" + c[0].lang + ")" };
    c = voices.filter(byLang);
    if (c.length) return { voice: c[0], note: "No " + want + " voice was identified on this device. Closest option: " + c[0].name + " (gender not identified)" };
    const d = voices.find((v) => v.default) || voices[0];
    return { voice: d, note: "No voice matched your language/gender. Using the device default: " + d.name };
  }
  function chunks(text) {
    const parts = String(text).replace(/\s+/g, " ").match(/[^.!?。]+[.!?。]*/g) || [String(text)];
    const out = []; let cur = "";
    parts.forEach((p) => { if ((cur + p).length > 220) { if (cur) out.push(cur.trim()); cur = p; } else cur += p; });
    if (cur.trim()) out.push(cur.trim());
    return out;
  }
  function stop() { if (supported()) window.speechSynthesis.cancel(); }
  async function speak(text, prefs, hooks) {
    hooks = hooks || {};
    if (!supported()) { hooks.onerror && hooks.onerror("unsupported"); return; }
    const voices = await load();
    const pk = pick(prefs, voices);
    hooks.onpick && hooks.onpick(pk);
    stop();
    const parts = chunks(text); let started = false;
    parts.forEach((p, i) => {
      const u = new SpeechSynthesisUtterance(p);
      if (pk.voice) { u.voice = pk.voice; u.lang = pk.voice.lang; }
      u.rate = Math.max(0.5, Math.min(2, prefs.rate || 1));
      u.pitch = Math.max(0, Math.min(2, prefs.pitch || 1));
      u.onstart = () => { if (!started) { started = true; hooks.onstart && hooks.onstart(); } };
      u.onend = () => { if (i === parts.length - 1) hooks.onend && hooks.onend(); };
      u.onerror = (e) => { if (e.error !== "canceled" && e.error !== "interrupted") hooks.onerror && hooks.onerror(e.error || "error"); else if (i === parts.length - 1) hooks.onend && hooks.onend(); };
      window.speechSynthesis.speak(u);
    });
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  function micSupported() { return !!SR; }
  function listen(lang, hooks) {
    if (!SR) { hooks.onerror && hooks.onerror("unsupported"); return null; }
    rec = new SR();
    rec.lang = ({ fil: "fil-PH", en: "en-US", es: "es-ES", fr: "fr-FR", de: "de-DE", pt: "pt-PT", ja: "ja-JP", ko: "ko-KR", zh: "zh-CN", hi: "hi-IN", ar: "ar-SA", id: "id-ID", it: "it-IT", ru: "ru-RU" })[lang] || "en-US";
    rec.interimResults = false; rec.maxAlternatives = 1; rec.continuous = false;
    rec.onstart = () => hooks.onstart && hooks.onstart();
    rec.onspeechend = () => hooks.onprocessing && hooks.onprocessing();
    rec.onresult = (e) => { const t = e.results[0][0].transcript; hooks.onresult && hooks.onresult(t); };
    rec.onerror = (e) => hooks.onerror && hooks.onerror(e.error || "error");
    rec.onend = () => hooks.onend && hooks.onend();
    try { rec.start(); } catch (e) { hooks.onerror && hooks.onerror("could not start"); }
    return rec;
  }
  function stopListening() { try { rec && rec.stop(); } catch (e) {} }
  // Put dictated text into Streamlit's chat box (same-origin iframe). Returns true if it worked.
  function fillChatInput(text) {
    try {
      const ta = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]') ||
                 window.parent.document.querySelector("textarea");
      if (!ta) return false;
      const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, "value").set;
      setter.call(ta, text);
      ta.dispatchEvent(new Event("input", { bubbles: true }));
      ta.focus();
      return true;
    } catch (e) { return false; }
  }
  return { classify, supported, load, pick, speak, stop, saved, save, micSupported, listen, stopListening, fillChatInput };
})();
"""

_BASE_CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0b1220;color:#e5edf7;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-size:14px}
button,select{font:inherit;color:#e5edf7;background:#16233a;border:1px solid #2b4268;border-radius:8px;padding:7px 12px;cursor:pointer}
button:hover:not(:disabled){border-color:#22d3ee}
button:disabled{opacity:.5;cursor:not-allowed}
.chip{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;border:1px solid #2b4268;background:#101b2f;margin:2px}
.on{border-color:#22d3ee;color:#22d3ee}.warn{border-color:#f59e0b;color:#fbbf24}.bad{border-color:#ef4444;color:#f87171}.ok{border-color:#34d399;color:#34d399}
.muted{color:#8da2c0;font-size:12px}
"""


# --------------------------------------------------------------------------- #
# Voice Settings component
# --------------------------------------------------------------------------- #
def voice_settings_html(prefs: dict | None = None) -> str:
    prefs = prefs or get_prefs()
    page = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>__CSS__ body{padding:6px} table{width:100%;border-collapse:collapse;font-size:13px} td,th{padding:4px 6px;border-bottom:1px solid #1f2f4d;text-align:left}
.box{border:1px solid #1f2f4d;border-radius:12px;padding:12px;margin-bottom:10px;background:#0f1a2e}</style></head><body>
<div class="box"><b>Voices detected on this device</b> <span id="count" class="chip">checking...</span>
 <div id="note" class="muted" style="margin:6px 0">Voices differ between devices and browsers. Gender is guessed from the voice name; some voices cannot be classified.</div>
 <select id="sel" style="width:100%;margin:6px 0"></select>
 <div><button id="use">Use this voice on this device</button> <button id="reset">Reset to automatic</button> <button id="test">🔊 Test voice</button> <button id="stop">Stop</button></div>
 <div id="pick" class="muted" style="margin-top:8px"></div></div>
<div class="box"><b>Microphone</b>
 <div id="micsupport" class="chip">checking...</div> <div id="micperm" class="chip">permission: unknown</div> <div id="micstate" class="chip">state: OFF</div>
 <div style="margin:6px 0"><button id="mictest">🎤 Test microphone (listens once)</button></div>
 <div id="heard" class="muted"></div></div>
<div class="box"><b>Text-only fallback</b><div class="muted">If this device has no voices or no speech recognition, the whole app still works by typing. Toggle "Text-only mode" in the controls above to turn speech off everywhere.</div></div>
<script>__VOICE_JS__
const PREFS = __PREFS__;
const $ = (id) => document.getElementById(id);
const SAMPLE = {en:"Hello, I am your AI chief executive. Your workforce is ready.",fil:"Kumusta po. Handa na ang inyong AI workforce.",es:"Hola, su equipo de inteligencia artificial está listo.",fr:"Bonjour, votre équipe d'intelligence artificielle est prête.",de:"Hallo, Ihr KI-Team ist bereit.",pt:"Olá, a sua equipa de inteligência artificial está pronta.",ja:"こんにちは。AIチームの準備ができました。",ko:"안녕하세요. AI 팀이 준비되었습니다.",zh:"你好，您的人工智能团队已准备就绪。",hi:"नमस्ते, आपकी एआई टीम तैयार है।",ar:"مرحبا، فريق الذكاء الاصطناعي جاهز.",id:"Halo, tim AI Anda siap.",it:"Ciao, il tuo team di intelligenza artificiale è pronto.",ru:"Здравствуйте, ваша команда ИИ готова."};
function chip(el, text, cls){ el.textContent = text; el.className = "chip " + (cls || ""); }
async function init(){
  if(!AtlasVoice.supported()){ chip($("count"),"speech synthesis not supported","bad"); $("test").disabled=true; $("use").disabled=true; $("sel").disabled=true; }
  else {
    const voices = await AtlasVoice.load();
    chip($("count"), voices.length + " voice(s)", voices.length ? "ok" : "warn");
    const sel = $("sel"); sel.innerHTML = "";
    voices.forEach((v,i)=>{ const o=document.createElement("option"); o.value=v.name; const g=AtlasVoice.classify(v);
      o.textContent = v.name + " - " + v.lang + " - " + (g==="unknown"?"gender not identified":g); sel.appendChild(o); });
    const s = AtlasVoice.saved(); if(s) sel.value = s;
    const pk = AtlasVoice.pick(PREFS, voices); $("pick").textContent = "Current choice: " + pk.note;
    if(!voices.length) $("note").textContent = "No voices found. Some browsers load voices only after the first click - try 'Test voice'. Otherwise use text-only mode.";
  }
  if(!AtlasVoice.micSupported()){ chip($("micsupport"),"speech recognition: not supported in this browser","warn"); $("mictest").disabled=true; }
  else chip($("micsupport"),"speech recognition: supported","ok");
  try{ if(navigator.permissions){ const p = await navigator.permissions.query({name:"microphone"}); const show=()=>chip($("micperm"),"permission: "+p.state, p.state==="granted"?"ok":p.state==="denied"?"bad":"warn"); show(); p.onchange=show; } else chip($("micperm"),"permission: cannot be checked here",""); }
  catch(e){ chip($("micperm"),"permission: cannot be checked here",""); }
}
$("use").onclick=()=>{ AtlasVoice.save($("sel").value); init(); };
$("reset").onclick=()=>{ AtlasVoice.save(""); init(); };
$("stop").onclick=()=>AtlasVoice.stop();
$("test").onclick=()=>{ if(PREFS.textOnly){ $("pick").textContent="Text-only mode is ON - voice output is disabled."; return; }
  AtlasVoice.speak(SAMPLE[PREFS.lang]||SAMPLE.en, PREFS, {onpick:(pk)=>{$("pick").textContent=pk.note;}, onerror:(e)=>{$("pick").textContent="Could not speak: "+e;}}); };
$("mictest").onclick=()=>{
  $("heard").textContent="";
  AtlasVoice.listen(PREFS.lang,{ onstart:()=>chip($("micstate"),"state: LISTENING","on"), onprocessing:()=>chip($("micstate"),"state: PROCESSING","warn"),
    onresult:(t)=>{$("heard").textContent='Heard: "'+t+'"';}, onerror:(e)=>{chip($("micstate"),"state: OFF (error: "+e+")","bad");},
    onend:()=>{ if(!$("micstate").className.includes("bad")) chip($("micstate"),"state: OFF",""); } });
};
init();
</script></body></html>"""
    return (page.replace("__CSS__", _BASE_CSS).replace("__VOICE_JS__", VOICE_JS)
            .replace("__PREFS__", js_json(prefs)))


# --------------------------------------------------------------------------- #
# Speak-a-reply component and dictation component (used in chats)
# --------------------------------------------------------------------------- #
def speak_html(text: str, prefs: dict | None = None, autoplay: bool = False) -> str:
    prefs = prefs or get_prefs()
    page = """<!doctype html><html><head><meta charset="utf-8"><style>__CSS__ body{padding:2px}</style></head><body>
<button id="b">🔊 Speak this reply</button> <button id="s">⏹</button> <span id="st" class="muted"></span>
<script>__VOICE_JS__
const TEXT=__TEXT__, PREFS=__PREFS__, AUTO=__AUTO__;
const $=(i)=>document.getElementById(i);
function go(){ AtlasVoice.speak(TEXT,PREFS,{onstart:()=>$("st").textContent="speaking...",onend:()=>$("st").textContent="",
  onerror:(e)=>$("st").textContent=(e==="not-allowed"?"Browser blocked automatic speech - press the button.":"Voice error: "+e)}); }
$("b").onclick=go; $("s").onclick=()=>{AtlasVoice.stop();$("st").textContent="";};
if(!AtlasVoice.supported()){ $("b").disabled=true; $("st").textContent="Speech not supported - text only."; }
else if(AUTO){ go(); }
</script></body></html>"""
    return (page.replace("__CSS__", _BASE_CSS).replace("__VOICE_JS__", VOICE_JS)
            .replace("__TEXT__", js_json(text[:4000])).replace("__PREFS__", js_json(prefs))
            .replace("__AUTO__", "true" if autoplay else "false"))


def dictation_html(prefs: dict | None = None) -> str:
    prefs = prefs or get_prefs()
    page = """<!doctype html><html><head><meta charset="utf-8"><style>__CSS__ body{padding:2px}</style></head><body>
<button id="m">🎤 Dictate</button> <span id="st" class="chip">Mic: OFF</span> <span id="h" class="muted"></span>
<script>__VOICE_JS__
const PREFS=__PREFS__; const $=(i)=>document.getElementById(i);
function chip(t,c){$("st").textContent=t;$("st").className="chip "+(c||"");}
if(!AtlasVoice.micSupported()){ $("m").disabled=true; chip("Mic: not supported in this browser - type instead","warn"); }
$("m").onclick=()=>{ $("h").textContent="";
  AtlasVoice.listen(PREFS.lang,{onstart:()=>chip("Mic: LISTENING","on"),onprocessing:()=>chip("Mic: PROCESSING","warn"),
   onresult:(t)=>{ const ok=AtlasVoice.fillChatInput(t); $("h").textContent=ok?'Heard: "'+t+'" - press Enter to send.':'Heard: "'+t+'" (copy it into the box).'; },
   onerror:(e)=>chip("Mic: OFF ("+e+")","bad"), onend:()=>{ if(!$("st").className.includes("bad")) chip("Mic: OFF",""); }}); };
</script></body></html>"""
    return (page.replace("__CSS__", _BASE_CSS).replace("__VOICE_JS__", VOICE_JS)
            .replace("__PREFS__", js_json(prefs)))
