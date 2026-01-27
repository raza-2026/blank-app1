import streamlit as st
from .config import load_config
from .auth import seconds_remaining, refresh_access_token, get_access_token

# Optional dependency (prevents crash if not installed)
try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except Exception:
    _HAS_AUTOREFRESH = False


def render_auth_status(location="sidebar", enable_live_timer=True):
    """
    Universal auth UI.
    - Countdown timer globally
    - Auto-refresh token near expiry
    - Manual refresh button
    - (Debug section cleaned up: removed token preview + copy bar)
    """

    # Choose where to render
    container = st.sidebar if location == "sidebar" else st

    # Guard to prevent duplicate rendering in same run
    guard_key = f"_auth_ui_rendered_{location}"
    if st.session_state.get(guard_key, False):
        return
    st.session_state[guard_key] = True

    cfg = load_config()

    # Refresh policy
    refresh_early_seconds = int(st.secrets.get("TOKEN_REFRESH_EARLY_SECONDS", 120))
    tick_ms = int(st.secrets.get("TOKEN_TIMER_TICK_MS", 1000))

    # Ensure token exists
    try:
        get_access_token(cfg)
    except Exception as e:
        container.error(f"Auth error: {e}")
        return

    # Live ticking countdown
    if enable_live_timer and _HAS_AUTOREFRESH:
        st_autorefresh(interval=tick_ms, key=f"osdu_token_timer_tick_{location}")
    elif enable_live_timer:
        container.caption(
            "ℹ️ Live countdown requires streamlit-autorefresh. Timer updates on clicks/navigation."
        )

    # Remaining time
    rem = seconds_remaining()
    mm = rem // 60
    ss = rem % 60

    # Auto-refresh near expiry
    current_token = st.session_state.get("osdu_token")
    refreshed_for_token = st.session_state.get("_auto_refreshed_for_token")

    if current_token and rem > 0 and rem <= refresh_early_seconds and refreshed_for_token != current_token:
        try:
            st.session_state["_auto_refreshed_for_token"] = current_token
            refresh_access_token(cfg)
            st.toast("🔄 Token auto-refreshed (near expiry).")
            st.rerun()
        except Exception as e:
            container.error(f"Auto-refresh failed: {e}")

    # Auto-refresh if expired
    if current_token and rem == 0 and refreshed_for_token != current_token:
        try:
            st.session_state["_auto_refreshed_for_token"] = current_token
            refresh_access_token(cfg)
            st.toast("🔄 Token auto-refreshed (expired).")
            st.rerun()
        except Exception as e:
            container.error(f"Auto-refresh failed: {e}")

    # ---- UI ----
    container.markdown("### 🔐 OSDU Token")

    if rem > 0:
        container.success(f"Valid — **{mm:02d}:{ss:02d}** remaining")
        container.caption(
            f"Auto-refresh triggers when ≤ {refresh_early_seconds}s remain (plus cache refresh ~55 min)."
        )
    else:
        container.error("Expired — refresh required")

    # Manual refresh
    if container.button("🔄 Refresh Token", use_container_width=True):
        try:
            refresh_access_token(cfg)
            container.success("Token refreshed!")
            st.rerun()
        except Exception as e:
            container.error(f"Refresh failed: {e}")

    # ---- Cleaned Debug Section (NO preview, NO code block) ----
    #with container.expander("🔎 JWT Debug (hidden)", expanded=False):
        #container.caption("Token contents are hidden for security.")