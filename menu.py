import streamlit as st
from pathlib import Path
from osdu_app.auth_ui import render_auth_status


@st.cache_resource
def _load_logo_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def render_menu():
    """Shared navigation menu for all pages."""
    with st.sidebar:
        # --- Branding (universal logo) ---
        # Configure via .streamlit/secrets.toml → APP_LOGO_PATH = "assets/logo.png"
        logo_src = st.secrets.get("APP_LOGO_PATH", "assets/logo.png")
        try:
            st.image(_load_logo_bytes(logo_src), use_container_width=True)
        except Exception:
            # Silent fallback: if logo missing, show a compact text title instead
            st.markdown("### OSDU Wellbore Ingestor")

        # Optional: tighten spacing under the logo slightly
        st.markdown("<div style='margin-top: 0.25rem'></div>", unsafe_allow_html=True)

        # ✅ IMPORTANT:
        # auth_ui.py uses a guard key to prevent DuplicateElementKey errors.
        # That guard persists in session_state across reruns, so we reset it here
        # on every rerun to ensure the OSDU Token block never "disappears".
        st.session_state.pop("_auth_ui_rendered_sidebar", None)

        # Universal timer + refresh button (sidebar)
        render_auth_status(location="sidebar", enable_live_timer=False)

        st.divider()
        st.title("OSDU Wellbore Ingestor")
        st.caption("Services")

        st.page_link(
            "pages/03_Main_Menu.py",
            label="🧭 Home",
        )

        st.page_link(
            "pages/05_Entitlements.py",
            label="🔐 Entitlements",
        )

        st.page_link(
            "pages/04_Legal_Service.py",
            label="⚖️ Legal Service",
        )

        # Internal page links (relative to entrypoint file)
        st.page_link(
            "streamlit_app.py",
            label="📁 File Service",
        )
        st.page_link(
            "pages/02_Workflow_Service.py",
            label="🧩 Workflow Service",
        )
        

        

        st.page_link(
            "pages/06_Wellbore_Search.py",
            label="🔎 Wellbore Search",
        )

        st.divider()
        st.caption("Tip: Use the menu to switch services.")