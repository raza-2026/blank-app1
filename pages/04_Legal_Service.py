
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
    st.title("⚖️ Legal Service (Module 4)")
    st.caption("Browse, validate, and select legal tags for ingestion.")

    base_url = st.secrets.get("LEGAL_SERVICE_BASE_URL", "").strip()
    if not base_url:
        st.error("Missing LEGAL_SERVICE_BASE_URL in .streamlit/secrets.toml")
        st.stop()

    token = get_access_token(cfg)

    # Top bar
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        refresh = st.button("🔄 Refresh tags")
    with c2:
        show_raw = st.toggle("Show raw JSON", value=False)
    with c3:
        selected = st.session_state.get("autofill_legal_tag", "—")
        st.info(f"Partition: `{cfg.data_partition_id}` • Selected for ingestion: `{selected}`")

    if refresh:
        cached_list_legal_tags.clear()

    tab1, tab2, tab3 = st.tabs(["📋 Browse", "✅ Validate", "📌 Use for ingestion"])

    # ---- Browse
    with tab1:
        try:
            resp = cached_list_legal_tags(base_url, cfg.data_partition_id, token)
            tags = resp.get("legalTags", []) or []

            if show_raw:
                st.json(resp)

            query = st.text_input("Search legal tags", placeholder="Type to filter by name...")
            names = []
            for t in tags:
                name = (t or {}).get("name", "")
                if name and (not query or query.lower() in name.lower()):
                    names.append(name)

            st.write(f"Showing **{len(names)}** tags")

            chosen = st.selectbox(
                "Select a legal tag",
                options=names,
                index=None,
                placeholder="Choose a legal tag...",
                key="legal_tag_selected",
            )

            if chosen:
                st.session_state["selected_legal_tag"] = chosen
                st.success(f"Selected: `{chosen}`")

        except Exception as e:
            st.error(f"Failed to load legal tags: {e}")

    # ---- Validate
    with tab2:
        tag = st.text_input(
            "Legal tag to validate",
            value=st.session_state.get("selected_legal_tag", ""),
            placeholder="Select from Browse tab or type here...",
        )

        if st.button("Validate tag ✅"):
            try:
                if not tag.strip():
                    st.warning("Please provide a legal tag name.")
                    st.stop()

                api = LegalService(base_url, cfg.data_partition_id, token)
                validated = api.get_legal_tag(tag.strip())
                st.success("Legal tag validated successfully ✅")
                st.json(validated)

            except Exception as e:
                st.error(f"Validation failed: {e}")

    # ---- Use for ingestion
    with tab3:
        candidate = st.session_state.get("selected_legal_tag") or st.session_state.get("autofill_legal_tag", "")
        st.write("Save the selected tag so Module 1 can use it automatically.")
        st.code(candidate or "No tag selected", language="text")

        if st.button("Use this tag for ingestion 📌", disabled=not bool(candidate)):
            st.session_state["autofill_legal_tag"] = candidate
            st.success(f"Saved `{candidate}` for ingestion (Module 1).")


if __name__ == "__main__":
    main()
