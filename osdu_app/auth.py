
import requests
import streamlit as st
from datetime import datetime, timedelta, timezone

from .config import OSDUConfig
from .token_store import load_token_from_env, save_token_to_env


def _http_error_details(resp: requests.Response) -> str:
    try:
        return str(resp.json())
    except Exception:
        return resp.text


def _utcnow():
    return datetime.now(timezone.utc)


def _init_auth_state():
    if "osdu_token" not in st.session_state:
        st.session_state.osdu_token = None
    if "osdu_expires_at" not in st.session_state:
        st.session_state.osdu_expires_at = None
    if "osdu_loaded_env" not in st.session_state:
        st.session_state.osdu_loaded_env = False


def _load_env_once():
    _init_auth_state()
    if st.session_state.osdu_loaded_env:
        return
    st.session_state.osdu_loaded_env = True
    token, exp = load_token_from_env()
    if token and exp:
        st.session_state.osdu_token = token
        st.session_state.osdu_expires_at = exp


@st.cache_data(ttl=3300, show_spinner=False)
def _fetch_access_token_cached(cfg: OSDUConfig) -> dict:
    """
    Cached for 55 min (3300s). Returns full token response dict.
    We keep get_access_token() returning str for backward compatibility.
    """
    data = {
        "grant_type": "client_credentials",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "scope": cfg.scope,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(cfg.token_url, data=data, headers=headers, timeout=30)
    if not r.ok:
        raise RuntimeError(
            f"Token request failed: {r.status_code} {_http_error_details(r)}"
        )
    return r.json()


def refresh_access_token(cfg: OSDUConfig) -> str:
    """
    Manual refresh: clears cache and fetches a new token immediately.
    """
    _fetch_access_token_cached.clear()
    return get_access_token(cfg)


def get_access_token(cfg: OSDUConfig) -> str:
    """
    Existing function signature preserved.
    Side-effects:
      - stores token + expiry in st.session_state
      - saves token + expiry into .env

    IMPORTANT FIX:
      - Do not reset expiry timer on every rerun if token hasn't changed.
        This prevents the UI countdown from getting stuck at 59:59.
    """
    _load_env_once()

    token_payload = _fetch_access_token_cached(cfg)
    token = token_payload["access_token"]
    expires_in = int(token_payload.get("expires_in", 3600))

    # Compute expiry (use expires_in from response)
    expires_at = _utcnow() + timedelta(seconds=expires_in)

    # ✅ KEY FIX: Only update expiry if token is new OR expiry missing OR expiry already passed
    prev_token = st.session_state.get("osdu_token")
    prev_exp = st.session_state.get("osdu_expires_at")

    should_update = (prev_token != token) or (prev_exp is None) or (prev_exp <= _utcnow())

    if should_update:
        # Save in session (for universal timer)
        st.session_state.osdu_token = token
        st.session_state.osdu_expires_at = expires_at

        # Save in env (for your requirement)
        try:
            save_token_to_env(token, expires_at)
        except Exception:
            # On Streamlit Cloud, filesystem may be read-only/ephemeral; session still works.
            pass

    return token


def seconds_remaining() -> int:
    _init_auth_state()
    exp = st.session_state.get("osdu_expires_at")
    if not exp:
        return 0
    return max(0, int((exp - _utcnow()).total_seconds()))


def osdu_headers(cfg: OSDUConfig, token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "data-partition-id": cfg.data_partition_id,
        "appkey": cfg.appkey,
        "Content-Type": "application/json",
    }
