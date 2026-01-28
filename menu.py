import streamlit as st
from pathlib import Path
from osdu_app.auth_ui import render_auth_status


@st.cache_resource
def _load_logo_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def render_menu():
    """Shared navigation menu for all pages."""
    with st.sidebar:
        # --- Branding (smaller logo, app name moved to top) ---
        # Configure via .streamlit/secrets.toml → APP_LOGO_PATH = "assets/logo.png"
        logo_src = st.secrets.get("APP_LOGO_PATH", "assets/logo.png")
        try:
            st.image(_load_logo_bytes(logo_src), width=80, use_container_width=False)
        except Exception:
            st.markdown("### IngestWell")

        # tighten spacing and show app name immediately below logo
        st.markdown("<div style='margin-top: 0.25rem'></div>", unsafe_allow_html=True)

        # Ensure auth UI renders reliably (guard reset)
        st.session_state.pop("_auth_ui_rendered_sidebar", None)
        render_auth_status(location="sidebar", enable_live_timer=False)

        st.divider()
        st.title("IngestWell")
        st.caption("Services")

        st.page_link("pages/03_Main_Menu.py", label="🧭 Home")
        st.page_link("pages/05_Entitlements.py", label="🔐 Entitlements")
        st.page_link("pages/04_Legal_Service.py", label="⚖️ Legal Service")
        # Internal page link (relative to entrypoint file)
        st.page_link("streamlit_app.py", label="📁 Wellbore Ingestion")
        st.page_link("pages/02_Workflow_Service.py", label="🧩 Workflow Service")
        st.page_link("pages/06_Wellbore_Search.py", label="🔎 Search Records")

        st.divider()
        st.caption("Tip: Use the menu to switch services.")
