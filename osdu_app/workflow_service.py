
# osdu_app/workflow_service.py
import json
import requests
from typing import Any, Tuple

from .config import OSDUConfig
from .auth import osdu_headers


def _http_error_details(resp: requests.Response) -> str:
    try:
        return str(resp.json())
    except Exception:
        return resp.text


class WorkflowService:
    def __init__(self, cfg: OSDUConfig, token: str):
        # Only store config + headers (DO NOT build URLs here)
        self.cfg = cfg
        self.h = osdu_headers(cfg, token)

    # -------------------------
    # Internal helpers (debug-friendly)
    # -------------------------
    @staticmethod
    def _normalize_list_response(data: Any) -> list:
        """Normalize tenant variations into a list."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "workflows", "results", "data"):
                v = data.get(key)
                if isinstance(v, list):
                    return v
        return []

    def _get_json_with_meta(self, url: str, params: dict | None = None, timeout: int = 60) -> Tuple[Any, dict]:
        """
        GET and return (json_body, meta)
        meta includes request url, status, and a short response preview.
        """
        r = requests.get(url, headers=self.h, params=params, timeout=timeout)

        meta = {
            "request_url": r.url,
            "status_code": r.status_code,
            "ok": r.ok,
            "content_type": r.headers.get("content-type"),
            "text_preview": (r.text[:1000] if r.text else ""),
        }

        if not r.ok:
            raise RuntimeError(f"GET failed: {r.status_code} {_http_error_details(r)}")

        try:
            return r.json(), meta
        except Exception:
            meta["json_parse_error"] = True
            return r.text, meta

    # -------------------------
    # Phase 1 (trigger + status)
    # -------------------------
    def trigger(self, workflow_name: str, body: dict) -> dict:
        path = self.cfg.workflow_trigger_path_tmpl.format(workflow_name=workflow_name)
        url = self.cfg.base_url + path
        r = requests.post(url, headers=self.h, json=body, timeout=60)
        if not r.ok:
            raise RuntimeError(f"trigger workflow failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def status(self, workflow_name: str, run_id: str) -> dict:
        path = self.cfg.workflow_status_path_tmpl.format(workflow_name=workflow_name, run_id=run_id)
        url = self.cfg.base_url + path
        r = requests.get(url, headers=self.h, timeout=60)
        if not r.ok:
            raise RuntimeError(f"status failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    # -------------------------
    # Phase 2 (info + list + details + runs)
    # -------------------------
    def info(self, return_meta: bool = False):
        url = self.cfg.base_url + self.cfg.workflow_info_path
        data, meta = self._get_json_with_meta(url, timeout=30)
        return (data, meta) if return_meta else data

    def list_workflows(self, prefix: str | None = None, return_meta: bool = False):
        url = self.cfg.base_url + self.cfg.workflow_list_path
        params = {"prefix": prefix} if prefix else None

        raw, meta = self._get_json_with_meta(url, params=params, timeout=60)
        items = self._normalize_list_response(raw)

        return (items, raw, meta) if return_meta else items

    def get_workflow(self, workflow_name: str, return_meta: bool = False):
        path = self.cfg.workflow_get_path_tmpl.format(workflow_name=workflow_name)
        url = self.cfg.base_url + path

        data, meta = self._get_json_with_meta(url, timeout=60)
        return (data, meta) if return_meta else data

    def list_runs(self, workflow_name: str, params_obj: dict | None = None, return_meta: bool = False):
        path = self.cfg.workflow_runs_path_tmpl.format(workflow_name=workflow_name)
        url = self.cfg.base_url + path

        params = None
        if params_obj is not None:
            params = {"params": json.dumps(params_obj)}

        raw, meta = self._get_json_with_meta(url, params=params, timeout=60)
        items = self._normalize_list_response(raw)

        return (items, raw, meta) if return_meta else items

    def update_run(self, workflow_name: str, run_id: str, status: str) -> dict:
        path = self.cfg.workflow_update_run_path_tmpl.format(workflow_name=workflow_name, run_id=run_id)
        url = self.cfg.base_url + path

        body = {"status": status}
        r = requests.put(url, headers=self.h, json=body, timeout=60)
        if not r.ok:
            raise RuntimeError(f"update run failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

