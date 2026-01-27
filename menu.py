
import streamlit as st
from osdu_app.auth_ui import render_auth_status


def render_menu():
    """Shared navigation menu for all pages."""
    with st.sidebar:
        # ✅ IMPORTANT:
        # auth_ui.py uses a guard key to prevent DuplicateElementKey errors.
        # That guard persists in session_state across reruns, so we reset it here
        # on every rerun to ensure the OSDU Token block never "disappears".
        st.session_state.pop("_auth_ui_rendered_sidebar", None)

        # Universal timer + refresh button (sidebar)
        render_auth_status(location="sidebar", enable_live_timer=False)

        st.divider()
        st.title("OSDU Demo App")
        st.caption("Modules")

        # Internal page links (relative to entrypoint file)
        st.page_link(
            "streamlit_app.py",
            label="Module 1 — File Service",
            icon="📁",
        )
        st.page_link(
            "pages/02_Workflow_Service.py",
            label="Module 2 — Workflow Service",
            icon="🧩",
        )
        st.page_link(
            "pages/03_Main_Menu.py",
            label="Module 3 — Main Menu / About",
            icon="🧭",
        )
        st.page_link(
            "pages/04_Legal_Service.py",
            label="Module 4 — Legal Service",
            icon="⚖️",
        )

        st.divider()
        st.caption("Tip: Use the menu to switch modules.")
