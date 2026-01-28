import json
import time
import uuid
import streamlit as st
import requests

from menu import render_menu
from osdu_app.config import load_config
from osdu_app.auth import get_access_token
from osdu_app.auth_ui import render_auth_status

from osdu_app.file_service import FileService
from osdu_app.workflow_service import WorkflowService
from osdu_app.legal_service import LegalService
from osdu_app.validators import validate_wellbore_csv


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def _csv_to_list(text: str) -> list[str]:
    items = [x.strip() for x in (text or "").split(",")]
    return [x for x in items if x]


def redact_url(url: str) -> str:
    if not url:
        return url
    return url.split("?", 1)[0] + "?<redacted>"


def extract_location_fields_legacy(loc: dict):
    location_obj = loc.get("Location") or loc.get("location") or {}
    signed_url = (
        location_obj.get("SignedURL")
        or location_obj.get("signedURL")
        or location_obj.get("signedUrl")
        or loc.get("SignedURL")
        or loc.get("signedURL")
        or loc.get("uri")
        or loc.get("url")
    )
    file_source = (
        location_obj.get("FileSource")
        or location_obj.get("fileSource")
        or loc.get("FileSource")
        or loc.get("fileSource")
    )
    file_id = loc.get("FileID") or loc.get("fileID") or loc.get("fileId")
    return signed_url, file_source, file_id


def extract_location_fields_modern(upload_url_resp: dict):
    location_obj = upload_url_resp.get("Location") or upload_url_resp.get("location") or upload_url_resp
    signed_url = (
        location_obj.get("SignedURL")
        or location_obj.get("signedURL")
        or location_obj.get("signedUrl")
        or location_obj.get("SignedUrl")
        or location_obj.get("uri")
        or location_obj.get("url")
    )
    file_source = location_obj.get("FileSource") or location_obj.get("fileSource")
    return signed_url, file_source


def build_file_generic_metadata(
    template: dict,
    *,
    file_name: str,
    file_source: str,
    target_kind: str,
    encoding_format_id: str,
    description: str,
    acl_owners: list[str],
    acl_viewers: list[str],
    legal_tags: list[str],
):
    record = json.loads(json.dumps(template))  # deep copy

    record["data"]["Name"] = file_name
    record["data"].setdefault("DatasetProperties", {}).setdefault("FileSourceInfo", {})
    record["data"]["DatasetProperties"]["FileSourceInfo"]["Name"] = file_name
    record["data"]["DatasetProperties"]["FileSourceInfo"]["FileSource"] = file_source

    record["data"]["EncodingFormatTypeID"] = encoding_format_id
    record["data"].setdefault("ExtensionProperties", {}).setdefault("FileContentsDetails", {})
    record["data"]["ExtensionProperties"]["FileContentsDetails"]["TargetKind"] = target_kind

    record["data"].setdefault("ExtensionProperties", {})
    record["data"]["ExtensionProperties"]["Description"] = description

    record.setdefault("acl", {})
    record["acl"]["owners"] = acl_owners
    record["acl"]["viewers"] = acl_viewers

    record.setdefault("legal", {})
    record["legal"]["legaltags"] = legal_tags
    record["legal"].setdefault("otherRelevantDataCountries", ["US"])
    record["legal"].setdefault("status", "compliant")

    return record


# ---------------------------------------------------------
# Main App
# ---------------------------------------------------------
def main():

    st.set_page_config(page_title="Wellbore Ingestion - OSDU", layout="wide")
    render_menu()  # Sidebar menu + token info

    st.title("Wellbore Ingestion")

    cfg = load_config()

    # ---------------------------------------------------------
    # Sidebar: Module Navigation
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Sidebar Inputs (Option B layout)
    # ---------------------------------------------------------
    with st.sidebar:
        st.header("Inputs")

        workflow_name = st.text_input("Workflow name", value=cfg.workflow_name)

        run_id_default = f"ignite2-{uuid.uuid4().hex[:8]}-wellbore"
        run_id = st.text_input("runId", value=run_id_default)

        # ❌ Removed visible input
        # fallback_file_source = st.text_input("FileSource (fallback)", value="streamlit-test-app")
        # ✅ Hidden default instead
        fallback_file_source = "streamlit-test-app"

        target_kind = st.text_input("TargetKind", value="mlc-training:ignite:wellbore:1.0.0")

        # ❌ Removed visible input
        # encoding_format_id = st.text_input(
        #     "EncodingFormatTypeID",
        #     value="mlc-training:reference-data--EncodingFormatType:text%2Fcsv:",
        # )
        # ✅ Hidden default instead (adjust to your registry if needed)
        encoding_format_id = "mlc-training:reference-data--EncodingFormatType:text%2Fcsv:"
        # ---------------------------------------------------------
        # ACL / Legal Block (Option B)
        # ---------------------------------------------------------
        st.divider()
        st.subheader("ACL / Legal (Required)")

        DEFAULT_ACL_OWNER = st.secrets.get("ACL_OWNER", "")
        DEFAULT_ACL_VIEWER = st.secrets.get("ACL_VIEWER", "")
        DEFAULT_LEGAL_TAG = st.secrets.get("LEGAL_TAG", "")

        owners_override = st.session_state.get("acl_owners", DEFAULT_ACL_OWNER)
        viewers_override = st.session_state.get("acl_viewers", DEFAULT_ACL_VIEWER)

        autofill_tag = (st.session_state.get("autofill_legal_tag", "") or "").strip()
        if autofill_tag and not st.session_state.get("legal_tags_sidebar"):
            st.session_state["legal_tags_sidebar"] = autofill_tag

        legal_tag_value = st.session_state.get("legal_tags_sidebar", DEFAULT_LEGAL_TAG)

        acl_owners_text = st.text_input(
            "ACL Owners (comma-separated)",
            value=owners_override,
            key="acl_owners_sidebar",
        )

        acl_viewers_text = st.text_input(
            "ACL Viewers (comma-separated)",
            value=viewers_override,
            key="acl_viewers_sidebar",
        )

        legal_tags_text = st.text_input(
            "Legal Tags (comma-separated)",
            value=legal_tag_value,
            key="legal_tags_sidebar",
            help="Select a tag in Module 4 (Legal Service) or override manually."
        )

        if legal_tags_text.strip():
            st.caption(f"✅ Using Legal Tag(s): `{legal_tags_text}`")
        else:
            st.warning("⚠️ Legal Tags are empty. Select from Module 4 or enter manually.")

        st.divider()

    # ---------------------------------------------------------
    # Main Page UI
    # ---------------------------------------------------------
    st.subheader("Upload wellbore CSV")

    
    
    # Description text placed directly under the big heading
    st.caption("CSV containing wellbore records for ingestion.")

    # File uploader WITHOUT the small label
    uploaded = st.file_uploader(
        label="", 
        type=["csv"], 
        key="wellbore_csv_main"
    )

    # Remove the description input completely — no label, no text box
    description = "CSV containing wellbore records for ingestion."


    validate_headers = st.checkbox("Validate CSV headers", value=True, key="validate_main")

    # ---------------------------------------------------------
    # Template JSON
    # ---------------------------------------------------------
    default_template = {
        "kind": "osdu:wks:dataset--File.Generic:1.0.0",
        "acl": {"owners": [], "viewers": []},
        "legal": {"legaltags": [], "otherRelevantDataCountries": ["US"], "status": "compliant"},
        "data": {
            "Name": "",
            "DatasetProperties": {"FileSourceInfo": {"FileSource": "", "Name": ""}},
            "EncodingFormatTypeID": encoding_format_id,
            "ExtensionProperties": {
                "Classification": "Raw File",
                "Description": description,
                "FileContentsDetails": {"FileType": "csv", "TargetKind": target_kind},
            },
        },
    }

    st.subheader("Metadata template (File.Generic)")
    template_text = st.text_area(
        "Template JSON",
        value=json.dumps(default_template, indent=2),
        height=260,
    )

    # ---------------------------------------------------------
    # Client Factories
    # ---------------------------------------------------------
    def get_file_api() -> FileService:
        token = get_access_token(cfg)
        return FileService(cfg, token)

    def get_wf_api() -> WorkflowService:
        token = get_access_token(cfg)
        return WorkflowService(cfg, token)

    # LEGAL SERVICE CLIENT
    def get_legal_api() -> LegalService:
        token = get_access_token(cfg)
        legal_base_url = st.secrets.get("LEGAL_SERVICE_BASE_URL", "").strip()
        if not legal_base_url:
            raise ValueError("Missing LEGAL_SERVICE_BASE_URL in secrets.toml")
        return LegalService(
            base_url=legal_base_url,
            data_partition_id=cfg.data_partition_id,
            access_token=token,
        )

    @st.cache_data(show_spinner=False)
    def cached_list_legal_tags(_legal_base_url: str, _partition: str, _token: str) -> dict:
        api = LegalService(_legal_base_url, _partition, _token)
        return api.list_legal_tags()

    def safe_clear_legal_cache():
        try:
            cached_list_legal_tags.clear()
        except Exception:
            pass

    # ---------------------------------------------------------
    # MAIN INGESTION FLOW
    # ---------------------------------------------------------
    if st.button("Submit", type="primary"):
        if not uploaded:
            st.error("Please upload a CSV.")
            st.stop()

        file_name = uploaded.name
        file_bytes = uploaded.getvalue()

        if validate_headers:
            ok, msg, rows = validate_wellbore_csv(file_bytes)
            if not ok:
                st.error(msg)
                st.stop()
            st.success(f"CSV validation OK • Rows: {rows}")

        try:
            template = json.loads(template_text)
        except Exception as e:
            st.error(f"Invalid template JSON: {e}")
            st.stop()

        acl_owners = _csv_to_list(acl_owners_text)
        acl_viewers = _csv_to_list(acl_viewers_text)
        legal_tags = _csv_to_list(legal_tags_text)

        if not acl_owners:
            st.error("ACL Owners cannot be empty.")
            st.stop()
        if not acl_viewers:
            st.error("ACL Viewers cannot be empty.")
            st.stop()

        file_api = get_file_api()
        wf_api = get_wf_api()

        # --- CHANGED BLOCK START: prefer modern uploadURL; fallback to legacy getLocation ---
        st.info("1) Getting landing zone (prefer modern uploadURL; fallback to legacy)")

        signed_url = None
        file_source_from_loc = None
        file_id_from_loc = None
        flow_used = None

        try:
            # Modern v2 path — returns SignedURL + FileSource
            loc = file_api.get_upload_url(expiry_time="1H")  # adjust expiry as needed
            st.json(loc)
            signed_url, file_source_from_loc = extract_location_fields_modern(loc)
            flow_used = "modern uploadURL"
            st.success("Landing zone acquired via modern uploadURL.")
        except Exception as e_modern:
            st.warning(f"Modern uploadURL failed ({e_modern}). Falling back to legacy getLocation…")
            # Legacy path — older tenants
            loc = file_api.get_upload_location_legacy(file_name)
            st.json(loc)
            signed_url, file_source_from_loc, file_id_from_loc = extract_location_fields_legacy(loc)
            flow_used = "legacy getLocation"
            st.success("Landing zone acquired via legacy getLocation.")

        if not signed_url:
            st.error("SignedURL missing from landing-zone response.")
            st.stop()

        final_file_source = file_source_from_loc or fallback_file_source
        st.caption(f"Flow used: {flow_used} • FileSource: {final_file_source}")
        # --- CHANGED BLOCK END ---

        st.info("2) Uploading via SignedURL…")
        file_api.upload_to_signed_url(signed_url, file_bytes, content_type="text/csv")
        st.success("Upload OK.")

        st.info("3) Creating metadata record…")
        record = build_file_generic_metadata(
            template,
            file_name=file_name,
            file_source=final_file_source,
            target_kind=target_kind,
            encoding_format_id=encoding_format_id,
            description=description,
            acl_owners=acl_owners,
            acl_viewers=acl_viewers,
            legal_tags=legal_tags,
        )

        meta = file_api.create_metadata(record)
        st.json(meta)

        file_record_id = meta.get("id") or meta.get("fileId") or meta.get("ID")

        if not file_record_id:
            st.error("Metadata created but file record ID missing.")
            st.stop()

        st.success(f"File Record ID: {file_record_id}")
        st.session_state["last_file_record_id"] = file_record_id

        st.info("4) Triggering workflow…")
        payload = {
            "executionContext": {"id": file_record_id, "dataPartitionId": cfg.data_partition_id},
            "runId": run_id,
        }
        resp = wf_api.trigger(workflow_name, payload)
        st.json(resp)

        st.info("5) Polling workflow status…")
        for _ in range(60):
            status = wf_api.status(workflow_name, run_id)
            st.write("Status:", status.get("status", status))
            if status.get("status") in ("finished", "completed", "success", "failed", "error"):
                st.json(status)
                break
            time.sleep(5)

    # ---------------------------------------------------------
    # FILE SERVICE TOOLS
    # ---------------------------------------------------------
    st.divider()
    st.header("File Service Tools (Phase 1)")
    st.divider()

    # (A) /info
    with st.expander("A) File Service Info (/info)", expanded=False):
        if st.button("Get /info", key="btn_info"):
            try:
                file_api = get_file_api()
                st.json(file_api.info())
            except Exception as e:
                st.error(str(e))

    # (B) uploadURL
    with st.expander("B) uploadURL (modern) + Upload via SignedURL", expanded=False):
        expiry = st.text_input("uploadURL expiryTime (e.g. 5M, 1H, 1D)", value="1H", key="upload_expiry")
        up_file = st.file_uploader("Pick a file", type=None, key="any_file_upload")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Generate uploadURL", key="btn_uploadurl"):
                try:
                    file_api = get_file_api()
                    loc = file_api.get_upload_url(expiry_time=expiry)
                    st.json(loc)

                    signed, file_source = extract_location_fields_modern(loc)
                    st.write("SignedURL (redacted):", redact_url(signed) if signed else None)
                    st.write("FileSource:", file_source)

                    st.session_state["last_upload_signed_url"] = signed
                    st.session_state["last_upload_file_source"] = file_source
                except Exception as e:
                    st.error(str(e))

        with col2:
            if st.button(
                "Upload to last SignedURL",
                disabled=("last_upload_signed_url" not in st.session_state),
                key="btn_put_signed",
            ):
                try:
                    if not up_file:
                        st.error("Pick a file first.")
                    else:
                        file_api = get_file_api()
                        file_api.upload_to_signed_url(
                            st.session_state["last_upload_signed_url"],
                            up_file.getvalue(),
                            content_type=up_file.type or "application/octet-stream",
                        )
                        st.success("Upload complete.")
                except Exception as e:
                    st.error(str(e))

        st.caption("After uploadURL upload, use (C) to create metadata.")

    # (C) Create metadata (modern)
    with st.expander("C) Create metadata from last FileSource (modern helper)", expanded=False):
        file_source = st.text_input(
            "FileSource (from uploadURL)",
            value=st.session_state.get("last_upload_file_source", ""),
            key="modern_filesource",
        )
        file_name_for_meta = st.text_input("File name for metadata", value="uploaded-file", key="modern_filename")

        if st.button("Create metadata (POST /files/metadata)", key="btn_create_meta_modern"):
            try:
                if not file_source:
                    st.error("FileSource empty.")
                    st.stop()

                try:
                    template = json.loads(template_text)
                except Exception as e:
                    st.error(f"Invalid template JSON: {e}")
                    st.stop()

                acl_owners = _csv_to_list(acl_owners_text)
                acl_viewers = _csv_to_list(acl_viewers_text)
                legal_tags = _csv_to_list(legal_tags_text)

                if not acl_owners or not acl_viewers:
                    st.error("ACL Owners/Viewers cannot be empty.")
                    st.stop()

                file_api = get_file_api()
                record = build_file_generic_metadata(
                    template,
                    file_name=file_name_for_meta,
                    file_source=file_source,
                    target_kind=target_kind,
                    encoding_format_id=encoding_format_id,
                    description=description,
                    acl_owners=acl_owners,
                    acl_viewers=acl_viewers,
                    legal_tags=legal_tags,
                )
                meta = file_api.create_metadata(record)
                st.json(meta)

                file_record_id = meta.get("id") or meta.get("fileId") or meta.get("ID")
                if file_record_id:
                    st.success(f"File Record ID: {file_record_id}")
                    st.session_state["last_file_record_id"] = file_record_id
                else:
                    st.warning("Metadata created, ID missing.")
            except Exception as e:
                st.error(str(e))

    # (D) Get metadata
    with st.expander("D) Get metadata by File Record ID", expanded=False):
        meta_id = st.text_input(
            "File metadata record id",
            value=st.session_state.get("last_file_record_id", ""),
            key="meta_get_id",
        )
        if st.button("Get metadata", key="btn_get_meta"):
            try:
                file_api = get_file_api()
                resp = file_api.get_metadata(meta_id)
                st.json(resp)
            except Exception as e:
                st.error(str(e))

    # (E) downloadURL
    with st.expander("E) Generate downloadURL", expanded=False):
        dl_id = st.text_input(
            "File metadata record id",
            value=st.session_state.get("last_file_record_id", ""),
            key="dl_id",
        )
        dl_expiry = st.text_input("downloadURL expiryTime", value="15M", key="dl_expiry")

        if st.button("Get downloadURL", key="btn_dl"):
            try:
                file_api = get_file_api()
                resp = file_api.get_download_url(dl_id, expiry_time=dl_expiry)
                st.json(resp)

                signed = resp.get("SignedUrl") or resp.get("SignedURL") or resp.get("url")
                st.write("Signed download URL (redacted):", redact_url(signed) if signed else None)
            except Exception as e:
                st.error(str(e))
                st.info("403 usually means ACL/entitlements mismatch.")

    # (F) Delete metadata
    with st.expander("F) Delete metadata", expanded=False):
        del_id = st.text_input(
            "File metadata record id",
            value=st.session_state.get("last_file_record_id", ""),
            key="del_id",
        )
        st.warning("Deletes metadata AND associated file. Use only for test objects.")
        if st.button("Delete metadata", key="btn_del"):
            try:
                file_api = get_file_api()
                file_api.delete_metadata(del_id)
                st.success("Deleted.")
            except Exception as e:
                st.error(str(e))


if __name__ == "__main__":
    main()