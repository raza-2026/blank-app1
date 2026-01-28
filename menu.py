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
            _bytes = _load_logo_bytes(logo_src)
            import base64
            _b64 = base64.b64encode(_bytes).decode("ascii")
            st.markdown(
                f"<div style='display:block'>"
                f"<img src='data:image/png;base64,{_b64}' style='margin:0;padding:0;display:block;width:120px'/>"
                f"<h1 style='margin:18px 0 0 0;padding:0;line-height:1.1'>IngestWell</h1>"
                f"</div>",
                unsafe_allow_html=True,
            )
            # Divider below app name with comfortable spacing
            st.markdown(
                "<hr style='margin:12px 0; border: none; border-top: 1px solid #e6e6e6;'>",
                unsafe_allow_html=True,
            )
        except Exception:
            st.markdown("<h1 style='margin:0;padding:0;line-height:1.0'>IngestWell</h1>", unsafe_allow_html=True)
            st.markdown(
                "<hr style='margin:12px 0; border: none; border-top: 1px solid #e6e6e6;'>",
                unsafe_allow_html=True,
            )

        st.page_link("pages/03_Main_Menu.py", label="🧭 Home")
        st.page_link("pages/05_Entitlements.py", label="🔐 Entitlements")
        st.page_link("pages/04_Legal_Service.py", label="⚖️ Legal Service")
        # Internal page link (relative to entrypoint file)
        st.page_link("streamlit_app.py", label="📁 Wellbore Ingestion")
        st.page_link("pages/06_Wellbore_Search.py", label="🔎 Search Records")

        # Divider below services with comfortable spacing
        st.markdown(
            "<hr style='margin:12px 0; border: none; border-top: 1px solid #e6e6e6;'>",
            unsafe_allow_html=True,
        )
        # (removed tip caption per request)
        # Move OSDU token block to the very bottom; reset guard to avoid duplicate element keys
        st.session_state.pop("_auth_ui_rendered_sidebar", None)
        render_auth_status(location="sidebar", enable_live_timer=False)
