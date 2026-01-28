# entitlements.py

import streamlit as st

from menu import render_menu
from osdu_app.config import load_config
from osdu_app.auth import get_access_token
from get_acl_streamlit import render_entitlements_module


def _cleanup_groups(value) -> list[str]:
    """
    Normalize ACL group selection into a clean list of group strings.

    Handles:
      - list: ["group@...", "group2@..."] -> ["group@...", "group2@..."]
      - list-like string: "['group@...','group2@...']" -> ["group@...","group2@..."]
      - plain string: "group@..." -> ["group@..."]
      - empty/None -> []
    """
    import ast

    if not value:
        return []

    # If already a list from multiselect
    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip().strip("'").strip('"').strip()
            if s:
                out.append(s)
        return out

    # If a string, try to parse list-like strings; else return as single-item list
    s = str(value).strip()
    try:
        if s.startswith("[") and s.endswith("]"):
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return [str(x).strip().strip("'").strip('"').strip() for x in parsed if str(x).strip()]
    except Exception:
        pass

    s = s.strip().strip("'").strip('"').strip()
    return [s] if s else []


def _ensure_session_keys():
    """
    Ensure session_state keys exist before they are used anywhere else.
    This prevents AttributeError on first page load.
    """
    defaults = {
        "owners_sel": [],       # selection coming from ACL picker (owners)
        "viewers_sel": [],      # selection coming from ACL picker (viewers)
        # These are the cleaned values we propagate to Module 1 (optional)
        "acl_owners": "",
        "acl_viewers": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def main():
    st.set_page_config(page_title="Entitlements • ACL Picker", layout="wide")
    render_menu()  # sidebar + navigation
    st.title("🔐 Entitlements")

    # ✅ Initialize session keys BEFORE calling any module that reads them
    _ensure_session_keys()

    # --- Load config & token (with a friendly error if anything fails) ---
    try:
        cfg = load_config()
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        st.stop()

    try:
        token = get_access_token(cfg)
    except Exception as e:
        st.error(f"Failed to get access token: {e}")
        st.stop()

    # --- Render your entitlements UI (this reads/writes owners_sel/viewers_sel) ---
    render_entitlements_module(
        base_url=cfg.base_url,
        data_partition=cfg.data_partition_id,
        access_token=token,
        title="Browse and select access control list groups for ingestion",
        filter_to_data_prefix=True,
        show_config=False,
    )

    st.divider()

    # Raw values created by your ACL picker
    raw_owner = st.session_state.get("owners_sel", [])
    raw_viewer = st.session_state.get("viewers_sel", [])

    # ✅ Clean into lists so we support multiple selections
    owner_values = _cleanup_groups(raw_owner)
    viewer_values = _cleanup_groups(raw_viewer)

    st.subheader("Selected ACL Groups")
    owners_display = "\n".join(owner_values) if owner_values else "(none)"
    viewers_display = "\n".join(viewer_values) if viewer_values else "(none)"
    st.code(f"Owners:\n{owners_display}\n\nViewers:\n{viewers_display}")

    # Optional: small warning if either list is empty
    if not owner_values or not viewer_values:
        st.warning("Select at least one Owner and one Viewer group above to enable Module 1 override.")

    st.divider()

    # Button to push selected ACLs to Module 1
    if st.button("✔️ Use These ACL Values in Module 1", disabled=(not owner_values or not viewer_values)):
        # Module 1 expects comma-separated text which it parses into lists
        st.session_state["acl_owners"] = ", ".join(owner_values)
        st.session_state["acl_viewers"] = ", ".join(viewer_values)

        st.success("ACL values applied to Module 1. Redirecting...")
        # NOTE: Update the target if your main page is under `pages/` or has a different filename.
        try:
            st.switch_page("streamlit_app.py")
        except Exception:
            # If Streamlit multipage routing is used with `pages/`, you may need something like:
            # st.switch_page("pages/01_Home.py")
            st.info("If redirect didn't work, please use the sidebar to navigate to Module 1.")


if __name__ == "__main__":
    main()