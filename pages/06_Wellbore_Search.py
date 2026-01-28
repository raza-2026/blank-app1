# pages/06_Wellbore_Search.py

import streamlit as st
from menu import render_menu

# Import the search module (your friend's code)
# Make sure the file is in the root folder of your app
from wellbore_search_final import run_wellbore_search_app


def main():
    st.set_page_config(page_title="Wellbore Search", layout="wide")

    # Reuse your sidebar/menu
    render_menu()

    st.title("Search Records")

    # Hand off UI and logic to the module
    run_wellbore_search_app()


if __name__ == "__main__":
    main()