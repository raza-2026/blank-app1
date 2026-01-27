import streamlit as st

from menu import render_menu
from osdu_app.config import load_config
from osdu_app.auth import get_access_token
from get_acl_streamlit import render_entitlements_module


def _cleanup_group(value) -> str:
    """
    Normalize ACL group selection into a clean group string.

    Handles:
      - list: ["group@..."] -> "group@..."
      - list-like string: "['group@...']" -> "group@..."
      - plain string: "group@..." -> "group@..."
      - empty/None -> ""
    """
    if value is None:
        return ""

    # If the picker stored a real Python list
    if isinstance(value, list):
        if not value:
            return ""
        value = value[0]

    s = str(value).strip()

    # If it's a list-like string, remove wrappers
    # Examples:
    #   "['group@...']"
    #   '["group@..."]'
    if (s.startswith("[") and s.endswith("]")):
        s = s[1:-1].strip()

    # Remove surrounding quotes if present
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1].strip()

    # Also handle the case: "['group@...']" after bracket strip -> "'group@...'"
    s = s.strip().strip("'").strip('"').strip()

    return s


def main():
    st.set_page_config(page_title="Entitlements • ACL Picker", layout="wide")
    render_menu()  # sidebar + navigation

    st.title("🔐 Entitlements • ACL Viewer & ACL Picker")

    cfg = load_config()
    token = get_access_token(cfg)

    # Render your entitlements UI
    render_entitlements_module(
        base_url=cfg.base_url,
        data_partition=cfg.data_partition_id,
        access_token=token,
        title="🔐 Entitlements (ACL Picker)",
        filter_to_data_prefix=True,
    )

    st.divider()

    # Raw values created by your ACL picker
    raw_owner = st.session_state.get("owners_sel", "")
    raw_viewer = st.session_state.get("viewers_sel", "")

    # ✅ Clean them so we don't pass "['group@...']" to OSDU
    owner_value = _cleanup_group(raw_owner)
    viewer_value = _cleanup_group(raw_viewer)

    st.subheader("Selected ACL Values (cleaned)")
    st.code(f"Owners: {owner_value}\nViewers: {viewer_value}")

    # Optional: small warning if empty
    if not owner_value or not viewer_value:
        st.warning("Select both an ACL Owner and ACL Viewer above to enable Module 1 override.")

    st.divider()

    # Button to push selected ACLs to Module 1
    if st.button("✔️ Use These ACL Values in Module 1", disabled=(not owner_value or not viewer_value)):
        st.session_state["acl_owners"] = owner_value
        st.session_state["acl_viewers"] = viewer_value

        st.success("ACL values applied to Module 1. Redirecting...")
        st.switch_page("streamlit_app.py")


if __name__ == "__main__":
    main()
