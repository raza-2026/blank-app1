
import requests
from .config import OSDUConfig
from .auth import osdu_headers


def _http_error_details(resp: requests.Response) -> str:
    try:
        return str(resp.json())
    except Exception:
        return resp.text


class WorkflowService:
    def __init__(self, cfg: OSDUConfig, token: str):
        self.cfg = cfg
        self.h = osdu_headers(cfg, token)

    def trigger(self, workflow_name: str, body: dict) -> dict:
        # POST /v1/workflow/{workflow_name}/workflowRun
        path = self.cfg.workflow_trigger_path_tmpl.format(workflow_name=workflow_name)
        url = self.cfg.base_url + path
        r = requests.post(url, headers=self.h, json=body, timeout=60)
        if not r.ok:
            raise RuntimeError(f"trigger workflow failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def status(self, workflow_name: str, run_id: str) -> dict:
        # GET /v1/workflow/{workflow_name}/workflowRun/{runId}
        path = self.cfg.workflow_status_path_tmpl.format(workflow_name=workflow_name, run_id=run_id)
        url = self.cfg.base_url + path
        r = requests.get(url, headers=self.h, timeout=60)
        if not r.ok:
            raise RuntimeError(f"status failed: {r.status_code} {_http_error_details(r)}")
        return r.json()
