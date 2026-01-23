
import json
import time
import streamlit as st

from osdu_app.config import load_config
from osdu_app.auth import get_access_token
from osdu_app.file_service import FileService
from osdu_app.workflow_service import WorkflowService
from osdu_app.validators import validate_wellbore_csv


def _csv_to_list(text: str) -> list[str]:
    """Comma-separated string -> clean list."""
    items = [x.strip() for x in (text or "").split(",")]
    return [x for x in items if x]


def build_metadata(
    template: dict,
    file_name: str,
    file_source: str,
    target_kind: str,
    encoding_format_id: str,
    description: str,
    acl_owners: list[str],
    acl_viewers: list[str],
    legal_tags: list[str],
) -> dict:
    """Fill dynamic fields in File.Generic metadata template."""
    record = json.loads(json.dumps(template))  # deep copy

    # Required core fields
    record["data"]["Name"] = file_name
    record["data"]["DatasetProperties"]["FileSourceInfo"]["Name"] = file_name
    record["data"]["DatasetProperties"]["FileSourceInfo"]["FileSource"] = file_source
    record["data"]["EncodingFormatTypeID"] = encoding_format_id
    record["data"]["ExtensionProperties"]["FileContentsDetails"]["TargetKind"] = target_kind
    record["data"]["ExtensionProperties"]["Description"] = description

    # Required governance fields
    record.setdefault("acl", {})
    record["acl"]["owners"] = acl_owners
    record["acl"]["viewers"] = acl_viewers

    record.setdefault("legal", {})
    record["legal"]["legaltags"] = legal_tags
    record["legal"].setdefault("otherRelevantDataCountries", ["US"])
    record["legal"].setdefault("status", "compliant")

    return record


def extract_location_fields(loc: dict):
    """
    Robustly extract SAS URL, FileSource, and FileID from getLocation response.

    Expected shape in your tenant:
    {
      "FileID": "...",
      "Location": { "SignedURL": "...", "FileSource": "..." }
    }
    """
    location_obj = loc.get("Location") or loc.get("location") or {}

    sas_url = (
        location_obj.get("SignedURL")
        or location_obj.get("signedURL")
        or location_obj.get("signedUrl")
        or loc.get("SignedURL")
        or loc.get("signedURL")
        or loc.get("uri")
        or loc.get("url")
    )

    file_source_from_loc = (
        location_obj.get("FileSource")
        or location_obj.get("fileSource")
        or loc.get("FileSource")
        or loc.get("fileSource")
    )

    file_id_from_loc = loc.get("FileID") or loc.get("fileID") or loc.get("fileId")

    return sas_url, file_source_from_loc, file_id_from_loc


def main():
    st.set_page_config(page_title="Wellbore Ingestion - File Service", layout="wide")
    st.title("Wellbore Ingestion • File Service Module ")

    cfg = load_config()

    # Defaults from secrets (recommended)
    default_acl_owner = st.secrets.get("ACL_OWNER", "")
    default_acl_viewer = st.secrets.get("ACL_VIEWER", "")
    default_legal_tag = st.secrets.get("LEGAL_TAG", "")

    with st.sidebar:
        st.header("Inputs")

        workflow_name = st.text_input("Workflow name", value=cfg.workflow_name)
        run_id = st.text_input("runId", value="ignite2-msiddiqui11-wellbore-workflow")

        # Fallback; we prefer FileSource returned from getLocation
        fallback_file_source = st.text_input("FileSource (fallback)", value="streamlit-test-app")

        target_kind = st.text_input("TargetKind", value="mlc-training:ignite:wellbore:1.0.0")
        encoding_format_id = st.text_input(
            "EncodingFormatTypeID",
            value="mlc-training:reference-data--EncodingFormatType:text%2Fcsv:",
        )

        st.divider()
        st.subheader("ACL / Legal (Required)")

        acl_owners_text = st.text_input(
            "ACL Owners (comma-separated)",
            value=default_acl_owner,
            help="Must not be empty. Use the owners group from your training handout.",
        )
        acl_viewers_text = st.text_input(
            "ACL Viewers (comma-separated)",
            value=default_acl_viewer,
            help="Must not be empty. Use the viewers group from your training handout.",
        )
        legal_tags_text = st.text_input(
            "Legal Tags (comma-separated)",
            value=default_legal_tag,
            help="Often required. Use the legal tag from your training handout.",
        )

    uploaded = st.file_uploader("Upload wellbore CSV", type=["csv"])

    st.subheader("Metadata template (File.Generic)")
    description = st.text_input("Description", value="CSV containing wellbore records for ingestion.")
    validate = st.checkbox("Validate CSV headers", value=True)

    # Minimal default template – ACL/Legal will be injected by build_metadata()
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

    template_text = st.text_area(
        "Template JSON (optional to edit)",
        value=json.dumps(default_template, indent=2),
        height=260,
    )

    if st.button("Run: Upload → Create Metadata → Trigger Workflow", type="primary"):
        # -------------------------
        # Guard: file selected
        # -------------------------
        if not uploaded:
            st.error("Please upload a CSV.")
            st.stop()

        file_name = uploaded.name
        file_bytes = uploaded.getvalue()

        # -------------------------
        # Validate CSV (optional)
        # -------------------------
        if validate:
            ok, msg, rows = validate_wellbore_csv(file_bytes)
            if not ok:
                st.error(msg)
                st.stop()
            st.success(f"CSV validation OK • Rows: {rows}")

        # -------------------------
        # Parse template JSON
        # -------------------------
        try:
            template = json.loads(template_text)
        except Exception as e:
            st.error(f"Invalid template JSON: {e}")
            st.stop()

        # -------------------------
        # ACL / Legal (required)
        # -------------------------
        acl_owners = _csv_to_list(acl_owners_text)
        acl_viewers = _csv_to_list(acl_viewers_text)
        legal_tags = _csv_to_list(legal_tags_text)

        if not acl_owners:
            st.error("ACL Owners cannot be empty. Add at least one owners group/email.")
            st.stop()
        if not acl_viewers:
            st.error("ACL Viewers cannot be empty. Add at least one viewers group/email.")
            st.stop()
        if not legal_tags:
            st.warning("Legal tags are empty. Many tenants require a legal tag; add LEGAL_TAG in secrets.toml.")

        # -------------------------
        # Auth
        # -------------------------
        try:
            token = get_access_token(cfg)
        except Exception as e:
            st.error(f"Auth failed: {e}")
            st.stop()

        file_api = FileService(cfg, token)
        wf_api = WorkflowService(cfg, token)

        # -------------------------
        # 1) Get landing zone location
        # -------------------------
        st.info("1) Getting landing zone location...")
        try:
            loc = file_api.get_upload_location(file_name)
        except Exception as e:
            st.error(f"getLocation failed: {e}")
            st.stop()

        st.json(loc)

        sas_url, file_source_from_loc, file_id_from_loc = extract_location_fields(loc)

        if not sas_url:
            st.error("Could not find SAS URL field in getLocation response.")
            st.stop()

        st.success("SAS URL extracted successfully.")
        st.write("FileID from getLocation:", file_id_from_loc)
        st.write("FileSource from getLocation:", file_source_from_loc)

        # Prefer FileSource returned by getLocation
        final_file_source = file_source_from_loc or fallback_file_source

        # -------------------------
        # 2) Upload to landing zone
        # -------------------------
        st.info("2) Uploading to landing zone (SAS PUT)...")
        try:
            file_api.upload_to_sas(sas_url, file_bytes, content_type="text/csv")
        except Exception as e:
            st.error(f"Upload failed: {e}")
            st.stop()
        st.success("Upload successful.")

        # -------------------------
        # 3) Create metadata record
        # -------------------------
        st.info("3) Creating metadata record...")
        record = build_metadata(
            template=template,
            file_name=file_name,
            file_source=final_file_source,
            target_kind=target_kind,
            encoding_format_id=encoding_format_id,
            description=description,
            acl_owners=acl_owners,
            acl_viewers=acl_viewers,
            legal_tags=legal_tags if legal_tags else template.get("legal", {}).get("legaltags", []),
        )

        try:
            meta = file_api.create_metadata(record)
        except Exception as e:
            st.error(f"Create metadata failed: {e}")
            st.stop()

        st.json(meta)

        file_id = meta.get("id") or meta.get("fileId") or meta.get("ID")
        if not file_id:
            st.warning("Metadata created, but file id not found in response.")
            st.stop()

        st.success(f"File Record ID: {file_id}")

        # -------------------------
        # 4) Trigger workflow (download step skipped)
        # -------------------------
        st.info("4) Triggering workflow...")
        payload = {
            "executionContext": {"id": file_id, "dataPartitionId": cfg.data_partition_id},
            "runId": run_id,
        }

        try:
            resp = wf_api.trigger(workflow_name, payload)
        except Exception as e:
            st.error(f"Trigger workflow failed: {e}")
            st.stop()

        st.json(resp)

        # -------------------------
        # Poll status
        # -------------------------
        st.info("Polling workflow status (every 5s)...")
        for _ in range(30):
            try:
                status = wf_api.status(workflow_name, run_id)
                st.write("Status:", status.get("status", status))
                if status.get("status") in ("finished", "completed", "success", "failed", "error"):
                    st.json(status)
                    break
            except Exception as e:
                st.warning(f"Status check failed: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
