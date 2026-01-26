
# osdu_app/legal_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass(frozen=True)
class LegalService:
    """
    Minimal OSDU Legal Service client.

    Endpoints:
      - GET  /legaltags
      - GET  /legaltags/{name}

    Notes:
      - No self-imports (prevents circular import errors).
      - Caller provides base_url, data_partition_id, and access_token.
    """

    base_url: str
    data_partition_id: str
    access_token: str
    timeout: int = 30

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "data-partition-id": self.data_partition_id,
            "Content-Type": "application/json",
        }

    def list_legal_tags(self) -> Dict[str, Any]:
        """
        List all legal tags.
        """
        url = f"{self.base_url.rstrip('/')}/legaltags"
        resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_legal_tag(self, legal_tag_name: str) -> Dict[str, Any]:
        """
        Get / validate a specific legal tag by name.
        """
        if not legal_tag_name or not legal_tag_name.strip():
            raise ValueError("legal_tag_name cannot be empty")

        url = f"{self.base_url.rstrip('/')}/legaltags/{legal_tag_name.strip()}"
        resp = requests.get(url, headers=self._headers(), timeout=self.timeout)

        # Friendly errors (matches typical behavior you had)
        if resp.status_code == 404:
            raise ValueError("Legal tag does not exist")
        if resp.status_code == 403:
            raise PermissionError("Not authorized to access this legal tag")

        resp.raise_for_status()
        return resp.json()
