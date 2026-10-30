"""Page 9: Voice Settings."""
from __future__ import annotations

import streamlit as st

import database as dbm
import ui_common as ui
import voice_service

_GENDERS = {"any": "Automatic", "female": "Female", "male": "Male"}


def render(ctx) -> None:
    st.title("Voice Settings")
    st.caption("Voices come from YOUR browser/device, so the list differs between phones, laptops and browsers.")
    ui.mode_banner(ctx)

    langs = list(voice_service.LANGUAGES)
    cur_lang = dbm.get_setting("voice_lang")
    cur_gender = dbm.get_setting("voice_gender")
    with st.form("voice_form"):
        gender = st.radio("Preferred voice", list(_GENDERS), horizontal=True, format_func=_GENDERS.get,
                          index=list(_GENDERS).index(cur_gender) if cur_gender in _GENDERS else 0)
        lang = st.selectbox("Language", langs, format_func=voice_service.LANGUAGES.get,
                            index=langs.index(cur_lang) if cur_lang in langs else 0)
        c1, c2 = st.columns(2)
        rate = c1.slider("Speaking speed", 0.5, 2.0, float(dbm.get_float("voice_rate", 1.0)), 0.1)
        pitch = c2.slider("Speech pitch (not supported by every voice)", 0.0, 2.0, float(dbm.get_float("voice_pitch", 1.0)), 0.1)
        speak_on = st.checkbox("Enable spoken responses", value=dbm.get_bool("speak_enabled"))
        auto = st.checkbox("Speak new replies automatically (browsers may block this until you click once)", value=dbm.get_bool("auto_speak"))
        text_only = st.checkbox("Text-only fallback mode (turns every voice feature off)", value=dbm.get_bool("text_only"))
        submitted = st.form_submit_button("Save voice settings")
    if submitted:
        dbm.set_setting("voice_gender", gender)
        dbm.set_setting("voice_lang", lang)
        dbm.set_setting("voice_rate", f"{rate:.1f}")
        dbm.set_setting("voice_pitch", f"{pitch:.1f}")
        dbm.set_setting("speak_enabled", "1" if speak_on else "0")
        dbm.set_setting("auto_speak", "1" if auto else "0")
        dbm.set_setting("text_only", "1" if text_only else "0")
        dbm.log_audit(ctx.company_id, "owner", "voice_settings_saved", f"gender={gender} lang={lang}")
        st.success("Voice settings saved.")
        st.rerun()

    if dbm.get_bool("text_only"):
        st.warning("Text-only mode is ON. Spoken replies and dictation are disabled everywhere.")

    st.subheader("Detected voices, test and microphone")
    ui.render_component(voice_service.voice_settings_html(voice_service.get_prefs()), height=700)

    st.subheader("Premium cloud voices")
    status = voice_service.cloud_voice_status()
    ui.md_html(ui.badge("NOT CONFIGURED", "warn") + f'<span class="muted"> {ui.esc(status["message"])}</span>')
    st.caption("Male/female selection uses the device's voice names as a best guess; if no matching voice exists, "
               "the closest available voice is used and the Test panel says which one.")
