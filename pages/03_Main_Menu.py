
import streamlit as st
from menu import render_menu


from osdu_app.auth_ui import render_auth_status

#render_auth_status(location="sidebar", enable_live_timer=True)


def main():
    st.set_page_config(page_title="OSDU Demo • Main Menu", layout="wide")
    render_menu()

    st.title("Welcome Muhammad Raza!")

    # Intro line under title (larger text, with more top/bottom spacing)
    st.markdown(
        "<div style='margin-top:12px;margin-bottom:12px;font-size:20px;font-weight:500'>"
        "IngestWell insert your wells into OSDU following these steps"
        "</div>",
        unsafe_allow_html=True,
    )

    # Add slight extra spacing before the home image
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Show home page image (placed in assets/home_page.png)
    img_path = "assets/home_page.png"
    try:
        st.image(img_path, use_container_width=True)
    except Exception:
        # silent fallback if image missing
        st.info("Home image not found at assets/home_page.png")

    # Add spacing below the image to push subsequent content down
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Right-aligned CTA button that switches page in the same tab
    cols = st.columns([3, 1])
    with cols[1]:
        if st.button("Let's get your wells Ingested"):
            try:
                # Preferred: switch to the Entitlements page within Streamlit
                st.switch_page("pages/05_Entitlements.py")
            except Exception:
                # Fallback: set query params and rerun
                st.experimental_set_query_params(page=["pages/05_Entitlements.py"])
                st.experimental_rerun()
        

 

if __name__ == "__main__":
    main()
