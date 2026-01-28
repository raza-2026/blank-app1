
import streamlit as st
from menu import render_menu


from osdu_app.auth_ui import render_auth_status

#render_auth_status(location="sidebar", enable_live_timer=True)


def main():
    st.set_page_config(page_title="OSDU Demo • Main Menu", layout="wide")
    render_menu()

    st.title("OSDU Wellbore Ingestor")
    st.write("Team A")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📁 Module 1 — File Service")
        st.write("- Upload file (legacy + modern)\n- Create metadata\n- Download URL\n- Delete metadata")
        st.page_link("streamlit_app.py", label="Open Module 1", icon="📁")

    with col2:
        st.subheader("🧩 Module 2 — Workflow Service")
        st.write("- List workflows\n- Workflow details\n- Run history\n- Run status + polling")
        st.page_link("pages/02_Workflow_Service.py", label="Open Module 2", icon="🧩")

    st.subheader("🔐 Module 5 — Entitlements")
    st.write("- View your entitlements groups\n- Pick ACL owners/viewers for ingestion")
    st.page_link("pages/05_Entitlements.py", label="Open Module 5", icon="🔐")

    st.divider()
    st.subheader("Architecture (high-level)")
    st.markdown(
        """
**Module 1 (File Service)**  
1) uploadURL/getLocation → 2) SignedURL upload → 3) create metadata

**Module 2 (Workflow Service)**  
4) trigger workflowRun → 5) poll status → 6) list run history
"""
    )

if __name__ == "__main__":
    main()
