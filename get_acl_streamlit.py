import base64
import hashlib
import json
import re
import urllib.parse
from typing import Any, Dict, List, Tuple

import requests
import streamlit as st

# ------------------------------------------------------------------
# Session State Defaults (kept from your friend's file)
# ------------------------------------------------------------------
ss = st.session_state
ss.setdefault("data_ready", False)
ss.setdefault("owners", [])
ss.setdefault("viewers", [])
ss.setdefault("rows", [])
ss.setdefault("payload", {})
ss.setdefault("used_endpoint", "")
ss.setdefault("claims", {})
ss.setdefault("resolved_member", "")
ss.setdefault("owners_sel", [])   # multiselect state for owners
ss.setdefault("viewers_sel", [])  # multiselect state for viewers
ss.setdefault("config_signature", "")

# ------------------------------------------------------------------
# Helpers (mostly unchanged from your friend's file)
# ------------------------------------------------------------------
def normalize_token(raw: str) -> str:
    """Make pasted token robust against quotes, 'Bearer ' prefix, and newlines."""
    if not raw:
        return ""
    t = raw.strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    QUOTES = ['"', "'", "“", "”", "‘", "’", "«", "»"]
    if len(t) >= 2 and t[0] in QUOTES and t[-1] in QUOTES:
        t = t[1:-1].strip()
    t = t.replace("\n", "").replace("\r", "").replace("\t", "")
    return t

def sanitize_for_decode(token: str) -> str:
    """Create a decoding-safe copy of the token WITHOUT altering original used for API."""
    if not token:
        return ""
    clean = "".join(ch for ch in token if ch.isprintable())
    parts = clean.split(".")
    if len(parts) != 3:
        return clean
    base64url_re = re.compile(r"[^A-Za-z0-9\-\_]")
    p0 = base64url_re.sub("", parts[0])
    p1 = base64url_re.sub("", parts[1])
    p2 = base64url_re.sub("", parts[2])
    return ".".join([p0, p1, p2])

def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"

def _headers(token: str, partition: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "data-partition-id": partition,
    }

def safe_json_text(resp: requests.Response) -> str:
    try:
        return json.dumps(resp.json(), indent=2)
    except Exception:
        return resp.text or ""

def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)

def decode_jwt_unverified_for_email(token: str) -> Dict[str, Any]:
    """Decode JWT payload WITHOUT signature verification (safe for UI display)."""
    if not token:
        return {}
    sanitized = sanitize_for_decode(token)
    parts = sanitized.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload_bytes = _b64url_decode(parts[1])
        try:
            return json.loads(payload_bytes.decode("utf-8"))
        except UnicodeDecodeError:
            text = payload_bytes.decode("utf-8", errors="replace")
            return json.loads(text)
    except Exception:
        return {}

def extract_email_like(payload: Dict[str, Any]) -> str:
    for k in ("preferred_username", "upn", "email", "unique_name"):
        v = payload.get(k)
        if isinstance(v, str) and "@" in v:
            return v
    emails = payload.get("emails")
    if isinstance(emails, list) and emails and isinstance(emails[0], str):
        return emails[0]
    return ""

def token_signature(token: str) -> str:
    """Short signature used for caching without storing token itself."""
    return hashlib.sha1(token.encode("utf-8")).hexdigest()[:16]

def _json_or_empty(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {}

# ------------------------------------------------------------------
# Cached HTTP calls (kept from your friend's file)
# NOTE: they use ss._real_token for actual HTTP, and cache by signature.
# ------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def probe_access_cached(base: str, partition: str, sig: str) -> Tuple[bool, str, int, str]:
    url = _url(base, "/api/entitlements/v2/groups")  # Entitlements API probe [1](https://slb001-my.sharepoint.com/personal/msiddiqui11_slb_com/Documents/Microsoft%20Copilot%20Chat%20Files/get_acl_streamlit.py)
    try:
        resp = requests.get(url, headers=_headers(ss._real_token, partition), timeout=30)
        status = resp.status_code
        if status == 200:
            return True, "Access OK: token can query Entitlements for this partition.", status, ""
        elif status == 401:
            return False, "Unauthorized (401): invalid/expired token or wrong audience.", status, safe_json_text(resp)
        elif status == 403:
            return False, "Forbidden (403): no permission for this partition.", status, safe_json_text(resp)
        elif status == 404:
            return False, "Not Found (404): check endpoint and /api/entitlements/v2/groups route.", status, safe_json_text(resp)
        elif status == 429:
            return False, "Too Many Requests (429): throttled by service.", status, safe_json_text(resp)
        else:
            return False, f"Unexpected status {status}.", status, safe_json_text(resp)
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {e}", -1, ""

@st.cache_data(show_spinner=False)
def get_groups_for_member_cached(base: str, partition: str, sig: str, member_email: str) -> Tuple[int, Dict[str, Any], str]:
    """
    Tries:
      1) /members/{email}/groups
      2) /groups?memberEmail={email}
      3) fallback /groups
    """
    headers = _headers(ss._real_token, partition)

    if member_email:
        path1 = f"/api/entitlements/v2/members/{urllib.parse.quote(member_email)}/groups"
        resp1 = requests.get(_url(base, path1), headers=headers, timeout=30)
        if resp1.status_code == 200:
            return 200, _json_or_empty(resp1), path1

    if member_email:
        path2 = f"/api/entitlements/v2/groups?memberEmail={urllib.parse.quote(member_email)}"
        resp2 = requests.get(_url(base, path2), headers=headers, timeout=30)
        if resp2.status_code == 200:
            return 200, _json_or_empty(resp2), path2

    path3 = "/api/entitlements/v2/groups"
    resp3 = requests.get(_url(base, path3), headers=headers, timeout=30)
    if resp3.status_code == 200:
        return 200, _json_or_empty(resp3), path3

    return resp3.status_code, _json_or_empty(resp3), path3

# ------------------------------------------------------------------
# Classification logic (kept from your friend's file)
# ------------------------------------------------------------------
OWNER_RE = re.compile(r"(^|[.\-_])owners?([.\-_@]|$)", re.IGNORECASE)
VIEWER_RE = re.compile(r"(^|[.\-_])viewers?([.\-_@]|$)", re.IGNORECASE)

def parse_owner_viewer_from_payload(payload: dict):
    """Return (owners, viewers, all_groups, rows_for_diagnostics) from diverse payload shapes."""
    owners, viewers, all_groups = [], [], []
    rows = []

    arrays: List[Tuple[str, List[Any]]] = []
    if isinstance(payload.get("groups"), list):
        arrays.append(("groups", payload["groups"]))
    if isinstance(payload.get("items"), list):
        arrays.append(("items", payload["items"]))
    if not arrays:
        for k, v in payload.items():
            if isinstance(v, list):
                arrays.append((k, v))

    def pick_email(d: dict) -> str:
        return d.get("email") or d.get("groupEmail") or d.get("name") or d.get("id") or ""

    def infer_role(name: str, explicit_role: str) -> str:
        if explicit_role:
            return explicit_role.upper()
        n = name.lower()
        if OWNER_RE.search(n):
            return "OWNER"
        if VIEWER_RE.search(n):
            return "VIEWER"
        return ""

    for src, arr in arrays:
        for entry in arr:
            if not isinstance(entry, dict):
                continue
            email = pick_email(entry)
            if not isinstance(email, str) or not email:
                continue
            role_u = infer_role(email, str(entry.get("role") or "").strip())
            all_groups.append(email)
            rows.append({"source": src, "group": email, "role_detected": role_u or "(none)"})
            if role_u == "OWNER":
                owners.append(email)
            elif role_u == "VIEWER":
                viewers.append(email)

    owners = sorted(set(owners))
    viewers = sorted(set(viewers))
    all_groups = sorted(set(all_groups))
    return owners, viewers, all_groups, rows

def filter_data_prefix(groups: List[str]) -> List[str]:
    return [g for g in groups if isinstance(g, str) and g.lower().startswith("data.")]

# ------------------------------------------------------------------
# Public entrypoint to render this module inside YOUR app
# ------------------------------------------------------------------
def render_entitlements_module(
    *,
    base_url: str,
    data_partition: str,
    access_token: str,
    title: str = "🔐 Entitlements (ACL Picker)",
    filter_to_data_prefix: bool = True,
    show_config: bool = True,
) -> None:
    """
    Render the Entitlements/ACL picker UI.

    Integration notes:
    - Token is supplied by your existing app auth (no need to paste).
    - Uses cached calls keyed by token_signature() (token itself not cached).
    """
    st.subheader(title)

    token = normalize_token(access_token)
    if not token:
        st.error("No access token available. Please load the app token first.")
        return

    # Store real token in session for the cached HTTP functions (never cached)
    ss._real_token = token
    sig = token_signature(token)

    # Decode email silently (same behavior as your friend's script) [1](https://slb001-my.sharepoint.com/personal/msiddiqui11_slb_com/Documents/Microsoft%20Copilot%20Chat%20Files/get_acl_streamlit.py)
    claims = decode_jwt_unverified_for_email(token)
    resolved_member = extract_email_like(claims)

    # Configuration summary (no sidebar; avoids clash with menu.py sidebar)
    if show_config:
        with st.expander("Configuration (read-only)", expanded=False):
            st.write("OSDU Endpoint:", base_url)
            st.write("Data Partition:", data_partition)
            st.write("Resolved member (from JWT):", resolved_member or "(not found)")
            st.caption("Token comes from the app (session_state / get_access_token).")

    # Probe entitlements access
    ok, reason, code, body = probe_access_cached(base_url, data_partition, sig)
    if not ok:
        st.error(f"{reason} (status={code})")
        if body:
            with st.expander("Probe response body", expanded=False):
                st.code(body)
        ss.data_ready = False
        return

    # Fetch groups
    status_code, payload, used = get_groups_for_member_cached(base_url, data_partition, sig, resolved_member)
    if status_code != 200:
        st.error("Could not fetch groups successfully. Check endpoint route and partition header.")
        with st.expander("Response payload", expanded=False):
            st.json(payload)
        ss.data_ready = False
        return

    owners, viewers, all_groups, rows = parse_owner_viewer_from_payload(payload)

    # Keep your friend's default behavior: filter to data.* groups [1](https://slb001-my.sharepoint.com/personal/msiddiqui11_slb_com/Documents/Microsoft%20Copilot%20Chat%20Files/get_acl_streamlit.py)
    if filter_to_data_prefix:
        owners = filter_data_prefix(owners)
        viewers = filter_data_prefix(viewers)

    # Persist results
    ss.owners = owners
    ss.viewers = viewers
    ss.rows = rows
    ss.payload = payload
    ss.used_endpoint = used
    ss.claims = claims
    ss.resolved_member = resolved_member
    ss.config_signature = f"{base_url}\n{data_partition}\n{sig}\n{resolved_member or ''}"
    ss.data_ready = True

    # Reset selections that no longer exist
    ss.owners_sel = [g for g in ss.owners_sel if g in owners]
    ss.viewers_sel = [g for g in ss.viewers_sel if g in viewers]

    # ---- Main ACL picker UI ----
    st.markdown("## Select ACL Groups")

    # Render Owner ACL groups first, then Viewer ACL groups beneath (stacked)
    st.markdown(
        "<div style='display:flex;justify-content:space-between;align-items:center'>"
        "<div><strong>1️⃣ Owner ACL groups</strong></div>"
        "<div title='Choose one or more OWNER groups; multiple selection is allowed' style='background:#e6f0ff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:12px;color:#0b63d6;'>i</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    ss.owners_sel = st.multiselect(
        "",
        options=ss.owners,
        default=ss.owners_sel,
        key="owners_multiselect",
    )

    st.markdown(
        "<div style='display:flex;justify-content:space-between;align-items:center'>"
        "<div><strong>2️⃣ Viewer ACL groups</strong></div>"
        "<div title='Choose one or more VIEWER groups; multiple selection is allowed' style='background:#e6f0ff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:12px;color:#0b63d6;'>i</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    ss.viewers_sel = st.multiselect(
        "",
        options=ss.viewers,
        default=ss.viewers_sel,
        key="viewers_multiselect",
    )

    # (ACL output and debug details removed per UI cleanup request)