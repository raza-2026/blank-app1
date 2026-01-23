
import requests
import streamlit as st
from .config import OSDUConfig


def _http_error_details(resp: requests.Response) -> str:
    try:
        return str(resp.json())
    except Exception:
        return resp.text


@st.cache_data(ttl=3300, show_spinner=False)
def get_access_token(cfg: OSDUConfig) -> str:
    data = {
        "grant_type": "client_credentials",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "scope": cfg.scope,
    }
    r = requests.post(cfg.token_url, data=data, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Token request failed: {r.status_code} {_http_error_details(r)}")
    return r.json()["access_token"]


def osdu_headers(cfg: OSDUConfig, token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "data-partition-id": cfg.data_partition_id,
        "appkey": cfg.appkey,
        "Content-Type": "application/json",
    }
