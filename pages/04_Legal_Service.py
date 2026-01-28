import streamlit as st

from menu import render_menu
from osdu_app.config import load_config
from osdu_app.auth import get_access_token
from osdu_app.legal_service import LegalService

st.set_page_config(page_title="Legal Service - OSDU", layout="wide")


@st.cache_data(show_spinner=False)
def cached_list_legal_tags(base_url: str, partition: str, token: str) -> dict:
    api = LegalService(base_url=base_url, data_partition_id=partition, access_token=token)
    return api.list_legal_tags()


def main():
    render_menu()

    cfg = load_config()
    st.title("⚖️ Legal Service")
    st.caption("Browse, validate, and select legal tags for ingestion.")

    base_url = st.secrets.get("LEGAL_SERVICE_BASE_URL", "").strip()
    if not base_url:
        st.error("Missing LEGAL_SERVICE_BASE_URL in .streamlit/secrets.toml")
        st.stop()

    token = get_access_token(cfg)

    # Top bar (cleaned — removed show_raw toggle)
    c1, c2 = st.columns([1, 3])
    with c1:
        refresh = st.button("🔄 Refresh tags")
    with c2:
        selected = st.session_state.get("autofill_legal_tag", "—")
        st.info(f"Partition: `{cfg.data_partition_id}` • Selected for ingestion: `{selected}`")

    if refresh:
        cached_list_legal_tags.clear()

    # ------------------------------ BROWSE ------------------------------
    st.divider()
    st.subheader("1️⃣ Browse Legal Tags")

    try:
        resp = cached_list_legal_tags(base_url, cfg.data_partition_id, token)
        tags = resp.get("legalTags", []) or []

        # Show ALL tag names (no search, no raw JSON)
        names = [(t or {}).get("name") for t in tags]

        st.write(f"Showing **{len(names)}** legal tags")

        # Hide label of the selectbox
        chosen = st.selectbox(
            "Select a legal tag",             # label (collapsed)
            options=names,
            index=None,
            placeholder="Choose a legal tag...",
            key="legal_tag_selected",
            label_visibility="collapsed",
        )

        if chosen:
            st.session_state["selected_legal_tag"] = chosen
            st.success(f"Selected: `{chosen}`")

    except Exception as e:
        st.error(f"Failed to load legal tags: {e}")

    # ------------------------------ VALIDATE ------------------------------
    st.divider()
    st.subheader("2️⃣ Validate Legal Tag")

    # Use the selected tag directly (no visible input box)
    tag = st.session_state.get("selected_legal_tag", "")

    # Initialize session keys used for toggle-driven JSON display
    st.session_state.setdefault("last_validated_tag", "")
    st.session_state.setdefault("last_validated_payload", None)

    # Row: Validate button + JSON toggle (off by default)
    c_left, c_right = st.columns([1, 1])
    with c_left:
        do_validate = st.button("Validate tag ✅")
    with c_right:
        show_json = st.toggle("Show JSON {}", value=False, key="show_legal_json")

    if do_validate:
        try:
            if not tag or not tag.strip():
                st.warning("Please select a tag above before validating.")
                st.stop()

            api = LegalService(base_url, cfg.data_partition_id, token)
            validated = api.get_legal_tag(tag.strip())

            # Store for later toggling without re-calling API
            st.session_state["last_validated_tag"] = tag.strip()
            st.session_state["last_validated_payload"] = validated

            st.success(f"Legal tag `{tag}` validated successfully!")

        except Exception as e:
            st.error(f"Validation failed: {e}")

    # Conditionally render JSON only if toggle is ON and we have a payload
    if show_json:
        payload = st.session_state.get("last_validated_payload", None)
        if payload is not None:
            st.json(payload)
        else:
            st.info("No JSON to show yet. Validate a tag first.")

    # ------------------------------ USE FOR INGESTION ------------------------------
    st.divider()
    st.subheader("3️⃣ Use for Ingestion")

    candidate = (
        st.session_state.get("selected_legal_tag")
        or st.session_state.get("autofill_legal_tag", "")
    )

    st.code(candidate or "No tag selected", language="text")

    if st.button("Use this tag for ingestion 📌", disabled=not bool(candidate)):
        st.session_state["autofill_legal_tag"] = candidate
        st.success(f"Saved `{candidate}` for ingestion (Module 1).")

        # Redirect to Module 1 (File Service)
        st.switch_page("streamlit_app.py")


if __name__ == "__main__":
    main()