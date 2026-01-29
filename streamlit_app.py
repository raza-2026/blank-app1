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
    render_menu()

    st.title("Wellbore Ingestion")

    cfg = load_config()

    # ---------------------------------------------------------
    # Upload Section
    # ---------------------------------------------------------
    st.subheader("Upload wellbore CSV")
    st.caption("CSV containing wellbore records for ingestion.")

    uploaded = st.file_uploader(
        label="",
        type=["csv"],
        key="wellbore_csv_main",
    )

    description = "CSV containing wellbore records for ingestion."

    validate_headers = st.checkbox("Validate CSV headers", value=True, key="validate_main")

    # ---------------------------------------------------------
    # Inputs
    # ---------------------------------------------------------
    st.divider()
    st.subheader("Inputs")

    workflow_name = st.text_input("Workflow name", value=cfg.workflow_name, key="wf_name_main")

    run_id_default = f"ignite2-{uuid.uuid4().hex[:8]}-wellbore"
    run_id = st.text_input("runId", value=run_id_default, key="run_id_main")

    fallback_file_source = "streamlit-test-app"
    encoding_format_id = "mlc-training:reference-data--EncodingFormatType:text%2Fcsv:"
    target_kind = st.text_input("TargetKind", value="mlc-training:ignite:wellbore:1.0.0", key="target_kind_main")

    # ---------------------------------------------------------
    # ACL / Legal
    # ---------------------------------------------------------
    st.divider()
    st.subheader("ACL / Legal (Required)")

    DEFAULT_ACL_OWNER = st.secrets.get("ACL_OWNER", "")
    DEFAULT_ACL_VIEWER = st.secrets.get("ACL_VIEWER", "")
    DEFAULT_LEGAL_TAG = st.secrets.get("LEGAL_TAG", "")

    owners_override = st.session_state.get("acl_owners", DEFAULT_ACL_OWNER)
    viewers_override = st.session_state.get("acl_viewers", DEFAULT_ACL_VIEWER)

    autofill_tag = (st.session_state.get("autofill_legal_tag", "") or "").strip()
    if autofill_tag and not st.session_state.get("legal_tags_main"):
        st.session_state["legal_tags_main"] = autofill_tag

    legal_tag_value = st.session_state.get("legal_tags_main", DEFAULT_LEGAL_TAG)

    acl_owners_text = st.text_input("ACL Owners", value=owners_override, key="acl_owners_main")
    acl_viewers_text = st.text_input("ACL Viewers", value=viewers_override, key="acl_viewers_main")
    legal_tags_text = st.text_input(
        "Legal Tags",
        value=legal_tag_value,
        key="legal_tags_main",
        help="Select from Module 4 (Legal Service) or override manually.",
    )

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

    if "template_text" not in st.session_state:
        st.session_state["template_text"] = json.dumps(default_template, indent=2)

    show_template_json = st.toggle("Show Template JSON {}", value=False, key="show_template_json")

    if show_template_json:
        template_text = st.text_area(
            "Template JSON",
            value=st.session_state["template_text"],
            height=260,
            key="template_main",
        )
        st.session_state["template_text"] = template_text
    else:
        template_text = st.session_state["template_text"]

    # ---------------------------------------------------------
    # API clients
    # ---------------------------------------------------------
    def get_file_api() -> FileService:
        token = get_access_token(cfg)
        return FileService(cfg, token)

    def get_wf_api() -> WorkflowService:
        token = get_access_token(cfg)
        return WorkflowService(cfg, token)

    # ---------------------------------------------------------
    # Main Submit Button
    # ---------------------------------------------------------
    if st.button("Submit", type="primary", key="submit_main"):
        if not uploaded:
            st.error("Please upload a CSV.")
            st.stop()

        file_name = uploaded.name
        file_bytes = uploaded.getvalue()

        # CSV validation or fallback row counting
        rows_count = None
        if validate_headers:
            ok, msg, rows = validate_wellbore_csv(file_bytes)
            if not ok:
                st.error(msg)
                st.stop()
            st.success(f"CSV validation OK • Rows: {rows}")
            rows_count = rows
        else:
            try:
                text = file_bytes.decode("utf-8", errors="ignore")
                lines = [ln for ln in text.splitlines() if ln.strip()]
                rows_count = max(len(lines) - 1, 0) if lines else 0
            except Exception:
                rows_count = None
        st.session_state["wb_rows_count"] = rows_count

        # Parse template JSON
        try:
            template = json.loads(template_text)
        except Exception as e:
            st.error(f"Invalid template JSON: {e}")
            st.stop()

        # ACL / Legal inputs
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

        # ---------------------------------------------------------
        # 1) Landing Zone
        # ---------------------------------------------------------
        st.info("1) Getting landing zone (prefer modern uploadURL; fallback to legacy)")

        signed_url = None
        file_source_from_loc = None
        file_id_from_loc = None
        flow_used = None

        try:
            loc = file_api.get_upload_url(expiry_time="1H")
            st.json(loc)
            signed_url, file_source_from_loc = extract_location_fields_modern(loc)
            flow_used = "modern uploadURL"
            st.success("Landing zone acquired via modern uploadURL.")
        except Exception as e_modern:
            st.warning(f"Modern uploadURL failed ({e_modern}). Falling back to legacy getLocation…")
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

        # ---------------------------------------------------------
        # 2) Upload
        # ---------------------------------------------------------
        st.info("2) Uploading via SignedURL…")
        file_api.upload_to_signed_url(signed_url, file_bytes, content_type="text/csv")
        st.success("Upload OK.")

        # ---------------------------------------------------------
        # 3) Metadata
        # ---------------------------------------------------------
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

        # ---------------------------------------------------------
        # 4) Triggering Workflow (EARLY SUCCESS REMOVED HERE)
        # ---------------------------------------------------------
        st.info("4) Triggering workflow…")

        payload = {
            "executionContext": {"id": file_record_id, "dataPartitionId": cfg.data_partition_id},
            "runId": run_id,
        }
        resp = wf_api.trigger(workflow_name, payload)
        st.json(resp)

        # *** Removed duplicate early success message ***
        # resp_status = (resp.get("status") or "").lower()
        # rows_count = st.session_state.get("wb_rows_count", None)
        # if resp_status == "submitted" and rows_count is not None:
        #     st.success(f"{rows_count} wellbore records were created successfully")

        # ---------------------------------------------------------
        # 5) Polling Workflow (final success is correct)
        # ---------------------------------------------------------
        st.info("5) Polling workflow status…")

        status_ph = st.empty()
        st.session_state["wf_last_status"] = None
        st.session_state["wf_polling_stop"] = False

        stop_polling = st.button("🛑 Stop Polling", key="btn_stop_polling")
        if stop_polling:
            st.session_state["wf_polling_stop"] = True

        max_wait_seconds = 300
        interval_seconds = 5
        iterations = max_wait_seconds // interval_seconds

        terminal_states = {"finished", "completed", "success", "failed", "error"}
        success_states = {"finished", "completed", "success"}

        with st.spinner("Waiting for workflow to finish…"):
            for _ in range(int(iterations)):
                if st.session_state.get("wf_polling_stop"):
                    status_ph.warning("Polling stopped by user.")
                    break

                status = wf_api.status(workflow_name, run_id)
                current = (status.get("status") or "").lower() or str(status)

                if current != st.session_state["wf_last_status"]:
                    st.session_state["wf_last_status"] = current
                    status_ph.write(f"Status: {current}")

                    if current in terminal_states:
                        if current in {"failed", "error"}:
                            status_ph.error(f"Status: {current}")
                        else:
                            status_ph.success(f"Status: {current}")

                            rows_count_final = st.session_state.get("wb_rows_count", None)
                            if rows_count_final is not None and current in success_states:
                                st.success(f"{rows_count_final} wellbore records were created successfully")

                        st.json(status)
                        st.toast("Workflow polling finished.", icon="✅")
                        break

                time.sleep(interval_seconds)
            else:
                status_ph.info("Polling timed out. Check workflow status later or increase timeout.")


if __name__ == "__main__":
    main()