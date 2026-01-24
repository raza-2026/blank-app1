
# osdu_app/file_service.py
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

    # -------------------------
    # Legacy (kept for compatibility)
    # -------------------------
    def get_upload_location_legacy(self, file_name: str) -> dict:
        """
        POST /v2/getLocation (legacy)
        """
        url = self.cfg.base_url + self.cfg.file_get_location_path
        payload = {"fileName": file_name}
        r = requests.post(url, headers=self.h, json=payload, timeout=60)
        if not r.ok:
            raise RuntimeError(f"getLocation failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    # -------------------------
    # Modern v2 endpoints
    # -------------------------
    def get_upload_url(self, expiry_time: str | None = None) -> dict:
        """
        GET /v2/files/uploadURL?expiryTime=5M|1H|7D
        Returns SignedURL + FileSource (tenant dependent fields).
        """
        url = self.cfg.base_url + self.cfg.file_upload_url_path
        params = {}
        if expiry_time:
            params["expiryTime"] = expiry_time
        r = requests.get(url, headers=self.h, params=params, timeout=60)
        if not r.ok:
            raise RuntimeError(f"uploadURL failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def upload_to_signed_url(self, signed_url: str, file_bytes: bytes, content_type: str = "text/csv") -> None:
        """
        Upload file bytes to SignedURL. (Azure needs x-ms-blob-type header; S3/GCS ignore it.)
        """
        headers = {
            "Content-Type": content_type,
            "x-ms-blob-type": "BlockBlob",  # safe for Azure; ignored by others
        }
        r = requests.put(signed_url, headers=headers, data=file_bytes, timeout=180)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"SignedURL PUT failed: {r.status_code} {r.text}")

    def create_metadata(self, record: dict) -> dict:
        """
        POST /v2/files/metadata
        """
        url = self.cfg.base_url + self.cfg.file_create_metadata_path
        r = requests.post(url, headers=self.h, json=record, timeout=60)
        if not r.ok:
            raise RuntimeError(f"create metadata failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def get_metadata(self, file_id: str) -> dict:
        """
        GET /v2/files/{id}/metadata
        """
        path = self.cfg.file_get_metadata_path_tmpl.format(file_id=file_id)
        url = self.cfg.base_url + path
        r = requests.get(url, headers=self.h, timeout=60)
        if not r.ok:
            raise RuntimeError(f"get metadata failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def delete_metadata(self, file_id: str) -> None:
        """
        DELETE /v2/files/{id}/metadata  (deletes metadata + associated file)
        """
        path = self.cfg.file_delete_metadata_path_tmpl.format(file_id=file_id)
        url = self.cfg.base_url + path
        r = requests.delete(url, headers=self.h, timeout=60)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"delete metadata failed: {r.status_code} {_http_error_details(r)}")

    def get_download_url(self, file_id: str, expiry_time: str | None = None) -> dict:
        """
        GET /v2/files/{id}/downloadURL?expiryTime=...
        """
        path = self.cfg.file_download_url_path_tmpl.format(file_id=file_id)
        url = self.cfg.base_url + path
        params = {}
        if expiry_time:
            params["expiryTime"] = expiry_time
        r = requests.get(url, headers=self.h, params=params, timeout=60)
        if not r.ok:
            raise RuntimeError(f"downloadURL failed: {r.status_code} {_http_error_details(r)}")
        return r.json()

    def revoke_url(self, payload: dict) -> None:
        """
        POST /v2/files/revokeURL (admin operation on many tenants)
        """
        url = self.cfg.base_url + self.cfg.file_revoke_url_path
        r = requests.post(url, headers=self.h, json=payload, timeout=60)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"revokeURL failed: {r.status_code} {_http_error_details(r)}")

    def info(self) -> dict:
        """
        GET /v2/info
        """
        url = self.cfg.base_url + self.cfg.file_info_path
        r = requests.get(url, headers=self.h, timeout=30)
        if not r.ok:
            raise RuntimeError(f"file info failed: {r.status_code} {_http_error_details(r)}")
        return r.json()
