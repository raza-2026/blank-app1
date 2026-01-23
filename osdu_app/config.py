
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

    # Endpoint overrides (keep configurable)
    file_get_location_path: str
    file_create_metadata_path: str
    file_download_url_path_tmpl: str

    workflow_trigger_path_tmpl: str
    workflow_status_path_tmpl: str


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

        file_get_location_path=s.get("FILE_GET_LOCATION_PATH", "/api/file/v2/getLocation"),
        file_create_metadata_path=s.get("FILE_CREATE_METADATA_PATH", "/api/file/v2/files/metadata"),
        file_download_url_path_tmpl=s.get("FILE_DOWNLOAD_URL_PATH_TMPL", "/api/file/v2/files/{file_id}/downloadURL"),

        workflow_trigger_path_tmpl=s.get("WORKFLOW_TRIGGER_PATH_TMPL", "/api/workflow/v1/workflow/{workflow_name}/workflowRun"),
        workflow_status_path_tmpl=s.get("WORKFLOW_STATUS_PATH_TMPL", "/api/workflow/v1/workflowrun/{run_id}"),
    )
