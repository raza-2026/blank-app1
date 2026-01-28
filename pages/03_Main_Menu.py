
import streamlit as st
from menu import render_menu


from osdu_app.auth_ui import render_auth_status

#render_auth_status(location="sidebar", enable_live_timer=True)


def main():
    st.set_page_config(page_title="OSDU Demo • Main Menu", layout="wide")
    render_menu()

    st.title("Welcome Muhammad Raza!")
    

    
        

 

if __name__ == "__main__":
    main()
