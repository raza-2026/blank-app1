
import os
from datetime import datetime, timezone
from dotenv import load_dotenv, set_key

ENV_FILE = ".env"

def _utcnow():
    return datetime.now(timezone.utc)

def _format_expiry(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _parse_expiry(s: str):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None

def load_token_from_env():
    load_dotenv(ENV_FILE)
    token = os.getenv("OSDU_JWT", "") or None
    exp = _parse_expiry(os.getenv("OSDU_JWT_EXPIRES_AT", ""))
    if token and exp and exp > _utcnow():
        return token, exp
    return None, None

def save_token_to_env(token: str, expires_at: datetime):
    # Ensure file exists
    if not os.path.exists(ENV_FILE):
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("OSDU_JWT=\nOSDU_JWT_EXPIRES_AT=\n")
    set_key(ENV_FILE, "OSDU_JWT", token)
    set_key(ENV_FILE, "OSDU_JWT_EXPIRES_AT", _format_expiry(expires_at))
