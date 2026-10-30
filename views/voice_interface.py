"""Page 1: full-screen-style animated voice landing page."""
from __future__ import annotations

import json

import streamlit as st

import database as dbm
import ui_common as ui
import ui_themes
import voice_service


def current_stage_html(ctx, *, show_controls: bool = True, autospeak: bool = True) -> str:
    theme = dbm.get_setting("ui_theme")
    try:
        custom = json.loads(dbm.get_setting("ui_custom") or "{}")
    except ValueError:
        custom = {}
    return ui_themes.stage_html(
        theme, ai_name=ctx.ai_name, greeting=ctx.greeting(),
        subtitle=f"{ctx.company['name']}  |  interface: {ui_themes.THEMES.get(theme, ui_themes.THEMES['atlas_core'])['name']}",
        custom=custom, reduce_motion=dbm.get_bool("reduce_motion"), paused=dbm.get_bool("pause_animation"),
        show_controls=show_controls, show_mic=not dbm.get_bool("text_only"), autospeak=autospeak,
        prefs=voice_service.get_prefs())


def render(ctx) -> None:
    ui.render_component(current_stage_html(ctx), height=620)
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        if st.button("OPEN COMMAND CENTER", type="primary", key="open_cc"):
            ui.goto("Overview")
    ui.md_html('<div class="muted" style="text-align:center">'
               'The animation is decorative. The microphone chip only says LISTENING while your browser is really '
               'listening, and the voice chip only says SPEAKING while speech is really playing. '
               'Voice not working? Everything is also available as text - just open the Command Center.</div>')
    ui.mode_banner(ctx)
