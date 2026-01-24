
# osdu_app/config.py
from dataclasses import dataclass
import streamlit as st

@dataclass
class OSDUConfig:
    base_url: str
    data_partition_id: str
    appkey: str
    token_url: str
    client_id: str
    client_secret: str
    scope: str
    workflow_name: str

    # File Service endpoints (existing + new)
    file_get_location_path: str
    file_upload_url_path: str
    file_create_metadata_path: str
    file_get_metadata_path_tmpl: str
    file_delete_metadata_path_tmpl: str
    file_download_url_path_tmpl: str
    file_revoke_url_path: str
    file_info_path: str

    # Workflow endpoints (existing)
    workflow_trigger_path_tmpl: str
    workflow_status_path_tmpl: str

    
    # Workflow endpoints (new)
    workflow_base_path: str
    workflow_info_path: str
    workflow_list_path: str
    workflow_get_path_tmpl: str
    workflow_runs_path_tmpl: str
    workflow_update_run_path_tmpl: str



def load_config() -> OSDUConfig:
    s = st.secrets
    return OSDUConfig(
        base_url=s["OSDU_BASE_URL"].rstrip("/"),
        data_partition_id=s["DATA_PARTITION_ID"],
        appkey=s["APPKEY"],
        token_url=s["TOKEN_URL"],
        client_id=s["CLIENT_ID"],
        client_secret=s["CLIENT_SECRET"],
        scope=s["SCOPE"],
        workflow_name=s.get("WORKFLOW_NAME", "csv_parser_wf"),

        # Legacy (kept)
        file_get_location_path=s.get("FILE_GET_LOCATION_PATH", "/api/file/v2/getLocation"),

        # Modern File Service v2 endpoints (recommended)
        file_upload_url_path=s.get("FILE_UPLOAD_URL_PATH", "/api/file/v2/files/uploadURL"),
        file_create_metadata_path=s.get("FILE_CREATE_METADATA_PATH", "/api/file/v2/files/metadata"),
        file_get_metadata_path_tmpl=s.get("FILE_GET_METADATA_PATH_TMPL", "/api/file/v2/files/{file_id}/metadata"),
        file_delete_metadata_path_tmpl=s.get("FILE_DELETE_METADATA_PATH_TMPL", "/api/file/v2/files/{file_id}/metadata"),
        file_download_url_path_tmpl=s.get("FILE_DOWNLOAD_URL_PATH_TMPL", "/api/file/v2/files/{file_id}/downloadURL"),
        file_revoke_url_path=s.get("FILE_REVOKE_URL_PATH", "/api/file/v2/files/revokeURL"),
        file_info_path=s.get("FILE_INFO_PATH", "/api/file/v2/info"),


        
        # Workflow base
        workflow_base_path=s.get("WORKFLOW_BASE_PATH", "/api/workflow/v1"),

        workflow_info_path=s.get("WORKFLOW_INFO_PATH", "/api/workflow/v1/info"),
        workflow_list_path=s.get("WORKFLOW_LIST_PATH", "/api/workflow/v1/workflow"),
        workflow_get_path_tmpl=s.get("WORKFLOW_GET_PATH_TMPL", "/api/workflow/v1/workflow/{workflow_name}"),
        workflow_runs_path_tmpl=s.get("WORKFLOW_RUNS_PATH_TMPL", "/api/workflow/v1/workflow/{workflow_name}/workflowRun"),
        workflow_update_run_path_tmpl=s.get(
            "WORKFLOW_UPDATE_RUN_PATH_TMPL",
            "/api/workflow/v1/workflow/{workflow_name}/workflowRun/{run_id}",
        ),


        # Workflow (unchanged)
        workflow_trigger_path_tmpl=s.get(
            "WORKFLOW_TRIGGER_PATH_TMPL",
            "/api/workflow/v1/workflow/{workflow_name}/workflowRun",
        ),
        workflow_status_path_tmpl=s.get(
            "WORKFLOW_STATUS_PATH_TMPL",
            "/api/workflow/v1/workflow/{workflow_name}/workflowRun/{run_id}",
        ),
    )
