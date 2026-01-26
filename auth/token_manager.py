
# auth/token_manager.py
import os
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st
from dotenv import load_dotenv, set_key

ENV_FILE = ".env"


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_expiry(expiry_str: str):
    # expects ISO like: 2026-01-26T14:22:10Z
    if not expiry_str:
        return None
    try:
        if expiry_str.endswith("Z"):
            expiry_str = expiry_str.replace("Z", "+00:00")
        return datetime.fromisoformat(expiry_str)
    except Exception:
        return None


def _format_expiry(dt: datetime):
    # store as ISO Z
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def init_token_state():
    """
    Initialize session state and load any existing token from .env once.
    """
    if "osdu_jwt" not in st.session_state:
        st.session_state.osdu_jwt = None
    if "osdu_jwt_expires_at" not in st.session_state:
        st.session_state.osdu_jwt_expires_at = None

    # Load from .env only once per session
    if "env_loaded" not in st.session_state:
        st.session_state.env_loaded = True
        load_dotenv(ENV_FILE)

        jwt = os.getenv("OSDU_JWT", "") or None
        exp = _parse_expiry(os.getenv("OSDU_JWT_EXPIRES_AT", ""))

        if jwt and exp and exp > _utcnow():
            st.session_state.osdu_jwt = jwt
            st.session_state.osdu_jwt_expires_at = exp


def _save_to_env(jwt: str, expires_at: datetime):
    """
    Persist token to .env (works locally).
    On Streamlit Cloud, the filesystem may be ephemeral; session_state still works.
    """
    # Ensure env file exists
    if not os.path.exists(ENV_FILE):
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("OSDU_JWT=\nOSDU_JWT_EXPIRES_AT=\n")

    set_key(ENV_FILE, "OSDU_JWT", jwt)
    set_key(ENV_FILE, "OSDU_JWT_EXPIRES_AT", _format_expiry(expires_at))


def fetch_new_jwt():
    """
    Fetch a new JWT using client_credentials.
    This is your jwt_token_app.py logic, moved into a reusable function.
    """
    payload = {
        "grant_type": "client_credentials",
        "client_id": st.secrets["OSDU_CLIENT_ID"],
        "client_secret": st.secrets["OSDU_CLIENT_SECRET"],
        "scope": st.secrets["OSDU_SCOPE"],
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = requests.post(st.secrets["OSDU_TOKEN_ENDPOINT"], data=payload, headers=headers, timeout=30)
    data = resp.json()

    if "access_token" not in data:
        raise RuntimeError(f"Token fetch failed: {data}")

    expires_in = int(data.get("expires_in", 3600))
    expires_at = _utcnow() + timedelta(seconds=expires_in)

    # Store in session
    st.session_state.osdu_jwt = data["access_token"]
    st.session_state.osdu_jwt_expires_at = expires_at

    # Store in .env (local persistence)
    _save_to_env(st.session_state.osdu_jwt, expires_at)

    return st.session_state.osdu_jwt


def seconds_remaining():
    exp = st.session_state.get("osdu_jwt_expires_at")
    if not exp:
        return 0
    remaining = int((exp - _utcnow()).total_seconds())
    return max(0, remaining)


def ensure_valid_jwt(auto_refresh: bool = True):
    """
    Returns a valid JWT. If expired (or near expiry), refreshes automatically.
    """
    init_token_state()

    jwt = st.session_state.get("osdu_jwt")
    exp = st.session_state.get("osdu_jwt_expires_at")

    early_seconds = int(st.secrets.get("TOKEN_REFRESH_EARLY_SECONDS", 120))

    # No token or no expiry => refresh
    if not jwt or not exp:
        return fetch_new_jwt() if auto_refresh else None

    # If expired or near expiry => refresh
    if seconds_remaining() <= early_seconds:
        return fetch_new_jwt() if auto_refresh else jwt

    return jwt


def auth_header():
    """
    One-liner helper for your API calls.
    """
    jwt = ensure_valid_jwt(auto_refresh=True)
    return {"Authorization": f"Bearer {jwt}"}
