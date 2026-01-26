
import streamlit as st

def render_menu():
    """Shared navigation menu for all pages."""
    with st.sidebar:
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
