
import requests
from .config import OSDUConfig
from .auth import osdu_headers


def _http_error_details(resp: requests.Response) -> str:
    try:
        return str(resp.json())
    except Exception:
        return resp.text


class FileService:
    def __init__(self, cfg: OSDUConfig, token: str):
        self.cfg = cfg
        self.h = osdu_headers(cfg, token)

    def get_upload_location(self, file_name: str) -> dict:
        url = self.cfg.base_url + self.cfg.file_get_location_path
        payload = {"fileName": file_name}
        r = requests.post(url, headers=self.h, json=payload, timeout=60)
        if not r.ok:
            raise RuntimeError(f"getLocation failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def upload_to_sas(self, sas_url: str, file_bytes: bytes, content_type: str = "text/csv") -> None:
        headers = {
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": content_type,
        }
        r = requests.put(sas_url, headers=headers, data=file_bytes, timeout=120)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Azure PUT failed: {r.status_code} {r.text}")

    def create_metadata(self, record: dict) -> dict:
        url = self.cfg.base_url + self.cfg.file_create_metadata_path
        r = requests.post(url, headers=self.h, json=record, timeout=60)
        if not r.ok:
            raise RuntimeError(f"create metadata failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def get_download_url(self, file_id: str) -> dict:
        path = self.cfg.file_download_url_path_tmpl.format(file_id=file_id)
        url = self.cfg.base_url + path
        r = requests.get(url, headers=self.h, timeout=60)
        if not r.ok:
            raise RuntimeError(f"downloadURL failed: {r.status_code} {_http_error_details(r)}")
        return r.json()
