"""Page 8: Interface Studio - preview, customise and save the animated voice interface."""
from __future__ import annotations

import json

import streamlit as st

import database as dbm
import ui_common as ui
import ui_themes
import voice_service


def _saved_custom() -> dict:
    try:
        return {**ui_themes.DEFAULT_CUSTOM, **json.loads(dbm.get_setting("ui_custom") or "{}")}
    except ValueError:
        return dict(ui_themes.DEFAULT_CUSTOM)


def render(ctx) -> None:
    st.title("Interface Studio")
    st.caption("Preview each animated interface before applying it. Your choice is saved and restored after a restart.")
    ui.mode_banner(ctx)

    keys = ui_themes.theme_keys()
    saved_theme = dbm.get_setting("ui_theme")
    if saved_theme not in keys:
        saved_theme = keys[0]
    st.info(f"Currently applied: **{ui_themes.THEMES[saved_theme]['name']}**")

    choice = st.radio("Interface", keys, index=keys.index(saved_theme), horizontal=True,
                      format_func=lambda k: ui_themes.THEMES[k]["name"], key="studio_choice")
    st.caption(ui_themes.THEMES[choice]["desc"])

    custom = _saved_custom()
    if choice == "custom":
        c1, c2, c3 = st.columns(3)
        custom["color"] = c1.color_picker("Accent colour", value=custom["color"])
        custom["intensity"] = c2.slider("Animation intensity", 10, 100, int(custom["intensity"]))
        layouts = list(ui_themes.LAYOUTS)
        custom["layout"] = c3.selectbox("Layout", layouts, index=layouts.index(custom["layout"]) if custom["layout"] in layouts else 0,
                                        format_func=lambda k: ui_themes.LAYOUTS[k])

    st.markdown("**Accessibility**")
    a1, a2 = st.columns(2)
    reduce_cur, pause_cur = dbm.get_bool("reduce_motion"), dbm.get_bool("pause_animation")
    reduce_new = a1.checkbox("Reduce motion (static visuals)", value=reduce_cur)
    pause_new = a2.checkbox("Pause animation", value=pause_cur)
    if reduce_new != reduce_cur or pause_new != pause_cur:
        dbm.set_setting("reduce_motion", "1" if reduce_new else "0")
        dbm.set_setting("pause_animation", "1" if pause_new else "0")
        st.rerun()
    st.caption("The operating system's own 'reduce motion' preference is also respected automatically.")

    ui.render_component(ui_themes.stage_html(
        choice, ai_name=ctx.ai_name, greeting=ctx.greeting(), subtitle="PREVIEW - not saved yet", custom=custom,
        reduce_motion=reduce_cur, paused=pause_cur, show_controls=True, show_mic=not dbm.get_bool("text_only"),
        autospeak=False, prefs=voice_service.get_prefs()), height=560)

    if st.button("Apply and save this interface", type="primary", key="studio_apply"):
        dbm.set_setting("ui_theme", choice)
        dbm.set_setting("ui_custom", json.dumps(custom))
        dbm.log_audit(ctx.company_id, "owner", "interface_changed", choice)
        st.success(f"Saved. The Voice Interface page now uses {ui_themes.THEMES[choice]['name']}.")
        st.rerun()

    if st.checkbox("Compare all interfaces side by side", key="studio_compare"):
        cols = st.columns(2)
        for i, k in enumerate(keys):
            with cols[i % 2]:
                st.caption(ui_themes.THEMES[k]["name"])
                ui.render_component(ui_themes.stage_html(
                    k, ai_name=ctx.ai_name, greeting=ui_themes.THEMES[k]["name"], custom=custom,
                    reduce_motion=reduce_cur, paused=pause_cur, show_controls=False, show_mic=False,
                    prefs=voice_service.get_prefs()), height=300)
