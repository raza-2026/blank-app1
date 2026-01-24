
import json
import time
import uuid

import streamlit as st

from osdu_app.config import load_config
from osdu_app.auth import get_access_token
from osdu_app.file_service import FileService
from osdu_app.workflow_service import WorkflowService
from osdu_app.validators import validate_wellbore_csv


# -----------------------------
# Helpers
# -----------------------------
def _csv_to_list(text: str) -> list[str]:
    items = [x.strip() for x in (text or "").split(",")]
    return [x for x in items if x]


def redact_url(url: str) -> str:
    """Redact query string for demo safety."""
    if not url:
        return url
    return url.split("?", 1)[0] + "?<redacted>"


def extract_location_fields_legacy(loc: dict):
    """
    Legacy getLocation extraction.
    Handles common tenant variations:
      { "Location": { "SignedURL": "...", "FileSource": "..." }, "FileID": "..." }
    """
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
    """
    Modern /v2/files/uploadURL extraction.
    Tenants may return fields at root or nested.
    """
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
    """
    Builds a File.Generic metadata record, using FileSource to link the uploaded object.
    """
    record = json.loads(json.dumps(template))  # deep copy

    # core name fields
    record["data"]["Name"] = file_name
    record["data"].setdefault("DatasetProperties", {}).setdefault("FileSourceInfo", {})
    record["data"]["DatasetProperties"]["FileSourceInfo"]["Name"] = file_name
    record["data"]["DatasetProperties"]["FileSourceInfo"]["FileSource"] = file_source

    # format + target
    record["data"]["EncodingFormatTypeID"] = encoding_format_id
    record["data"].setdefault("ExtensionProperties", {}).setdefault("FileContentsDetails", {})
    record["data"]["ExtensionProperties"]["FileContentsDetails"]["TargetKind"] = target_kind

    # description
    record["data"].setdefault("ExtensionProperties", {})
    record["data"]["ExtensionProperties"]["Description"] = description

    # governance
    record.setdefault("acl", {})
    record["acl"]["owners"] = acl_owners
    record["acl"]["viewers"] = acl_viewers

    record.setdefault("legal", {})
    record["legal"]["legaltags"] = legal_tags
    record["legal"].setdefault("otherRelevantDataCountries", ["US"])
    record["legal"].setdefault("status", "compliant")

    return record


# -----------------------------
# Main App
# -----------------------------
def main():
    st.set_page_config(page_title="Wellbore Ingestion - OSDU", layout="wide")
    st.title("Wellbore Ingestion • File Service Module + Tools (Phase 1)")

    cfg = load_config()

    # Defaults from secrets (optional)
    default_acl_owner = st.secrets.get("ACL_OWNER", "")
    default_acl_viewer = st.secrets.get("ACL_VIEWER", "")
    default_legal_tag = st.secrets.get("LEGAL_TAG", "")

    # -----------------------------
    # Sidebar: configuration inputs
    # -----------------------------
    with st.sidebar:
        st.header("Inputs")

        workflow_name = st.text_input("Workflow name", value=cfg.workflow_name)

        # runId - stable but unique by default
        run_id_default = f"ignite2-{uuid.uuid4().hex[:8]}-wellbore"
        run_id = st.text_input("runId", value=run_id_default)

        fallback_file_source = st.text_input("FileSource (fallback)", value="streamlit-test-app")

        target_kind = st.text_input("TargetKind", value="mlc-training:ignite:wellbore:1.0.0")

        encoding_format_id = st.text_input(
            "EncodingFormatTypeID",
            value="mlc-training:reference-data--EncodingFormatType:text%2Fcsv:",
        )

        st.divider()
        st.subheader("ACL / Legal (Required)")

        acl_owners_text = st.text_input("ACL Owners (comma-separated)", value=default_acl_owner)
        acl_viewers_text = st.text_input("ACL Viewers (comma-separated)", value=default_acl_viewer)
        legal_tags_text = st.text_input("Legal Tags (comma-separated)", value=default_legal_tag)

    # -----------------------------
    # Main page: smooth ingestion flow inputs (UX fix)
    # -----------------------------
    st.subheader("Upload wellbore CSV")

    uploaded = st.file_uploader("Upload wellbore CSV", type=["csv"], key="wellbore_csv_main")

    description = st.text_input(
        "Description",
        value="CSV containing wellbore records for ingestion.",
        key="desc_main",
    )

    validate_headers = st.checkbox("Validate CSV headers", value=True, key="validate_main")

    # -----------------------------
    # Template JSON (built AFTER description exists ✅)
    # -----------------------------
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
        "Template JSON (optional to edit)",
        value=json.dumps(default_template, indent=2),
        height=260,
    )

    # -----------------------------
    # Client factories
    # -----------------------------
    def get_file_api() -> FileService:
        token = get_access_token(cfg)
        return FileService(cfg, token)

    def get_wf_api() -> WorkflowService:
        token = get_access_token(cfg)
        return WorkflowService(cfg, token)

    # -----------------------------
    # MAIN INGESTION FLOW (Legacy getLocation)
    # -----------------------------
    if st.button("Run: Upload → Create Metadata → Trigger Workflow (Legacy getLocation)", type="primary"):
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

        # parse template
        try:
            template = json.loads(template_text)
        except Exception as e:
            st.error(f"Invalid template JSON: {e}")
            st.stop()

        # governance
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

        st.info("1) Getting landing zone location (legacy getLocation)...")
        loc = file_api.get_upload_location_legacy(file_name)
        st.json(loc)

        signed_url, file_source_from_loc, file_id_from_loc = extract_location_fields_legacy(loc)
        if not signed_url:
            st.error("Could not find SAS/SignedURL in getLocation response.")
            st.stop()

        st.success("SignedURL extracted.")
        st.write("FileID from getLocation:", file_id_from_loc)
        st.write("FileSource from getLocation:", file_source_from_loc)

        final_file_source = file_source_from_loc or fallback_file_source

        st.info("2) Uploading to landing zone (SignedURL PUT)...")
        file_api.upload_to_signed_url(signed_url, file_bytes, content_type="text/csv")
        st.success("Upload successful.")

        st.info("3) Creating metadata record...")
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
            st.error("Metadata created but file record id not found in response.")
            st.stop()

        st.success(f"File Record ID: {file_record_id}")
        st.session_state["last_file_record_id"] = file_record_id

        st.info("4) Triggering workflow...")
        payload = {
            "executionContext": {"id": file_record_id, "dataPartitionId": cfg.data_partition_id},
            "runId": run_id,
        }
        resp = wf_api.trigger(workflow_name, payload)
        st.json(resp)

        st.info("5) Polling workflow status (every 5s)...")
        for _ in range(60):
            status = wf_api.status(workflow_name, run_id)
            st.write("Status:", status.get("status", status))
            if status.get("status") in ("finished", "completed", "success", "failed", "error"):
                st.json(status)
                break
            time.sleep(5)

    # -----------------------------
    # FILE SERVICE TOOLS (PHASE 1)
    # -----------------------------
    st.divider()
    st.header("File Service Tools (Phase 1)")

    with st.expander("A) File Service Info (/info)", expanded=False):
        if st.button("Get /info", key="btn_info"):
            try:
                file_api = get_file_api()
                st.json(file_api.info())
            except Exception as e:
                st.error(str(e))

    with st.expander("B) uploadURL (modern) + Upload via SignedURL", expanded=False):
        expiry = st.text_input("uploadURL expiryTime (e.g. 5M, 1H, 1D)", value="1H", key="upload_expiry")
        up_file = st.file_uploader("Pick a file to upload (any)", type=None, key="any_file_upload")

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
                        st.error("Please pick a file to upload.")
                    else:
                        file_api = get_file_api()
                        file_api.upload_to_signed_url(
                            st.session_state["last_upload_signed_url"],
                            up_file.getvalue(),
                            content_type=up_file.type or "application/octet-stream",
                        )
                        st.success("Upload completed via SignedURL.")
                except Exception as e:
                    st.error(str(e))

        st.caption("Tip: After uploadURL upload, use (C) to create metadata with the FileSource.")

    with st.expander("C) Create metadata from last FileSource (modern helper)", expanded=False):
        st.write("This helps test: POST /files/metadata using FileSource returned by uploadURL.")

        file_source = st.text_input(
            "FileSource (from uploadURL)",
            value=st.session_state.get("last_upload_file_source", ""),
            key="modern_filesource",
        )
        file_name_for_meta = st.text_input("File name for metadata", value="uploaded-file", key="modern_filename")

        if st.button("Create metadata (POST /files/metadata)", key="btn_create_meta_modern"):
            try:
                if not file_source:
                    st.error("FileSource is empty. Generate uploadURL first.")
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
                    st.warning("Metadata created, but could not find id in response.")
            except Exception as e:
                st.error(str(e))

    with st.expander("D) Get metadata by File Record ID (GET /files/{id}/metadata)", expanded=False):
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

    with st.expander("E) Generate downloadURL (GET /files/{id}/downloadURL)", expanded=False):
        dl_id = st.text_input(
            "File metadata record id",
            value=st.session_state.get("last_file_record_id", ""),
            key="dl_id",
        )
        dl_expiry = st.text_input("downloadURL expiryTime (e.g. 5M, 1H, 1D)", value="15M", key="dl_expiry")

        if st.button("Get downloadURL", key="btn_dl"):
            try:
                file_api = get_file_api()
                resp = file_api.get_download_url(dl_id, expiry_time=dl_expiry)
                st.json(resp)

                signed = resp.get("SignedUrl") or resp.get("SignedURL") or resp.get("url")
                st.write("Signed download URL (redacted):", redact_url(signed) if signed else None)
            except Exception as e:
                st.error(str(e))
                st.info("If you get 403, it's typically entitlements/ACL mismatch for the token identity.")

    with st.expander("F) Delete metadata (DELETE /files/{id}/metadata)", expanded=False):
        del_id = st.text_input(
            "File metadata record id",
            value=st.session_state.get("last_file_record_id", ""),
            key="del_id",
        )
        st.warning("This deletes metadata AND the associated file. Use only on test records.")
        if st.button("Delete metadata", key="btn_del"):
            try:
                file_api = get_file_api()
                file_api.delete_metadata(del_id)
                st.success("Deleted metadata (and associated file if supported).")
            except Exception as e:
                st.error(str(e))


if __name__ == "__main__":
    main()
