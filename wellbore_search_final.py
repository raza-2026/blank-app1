# wellbore_search_final.py

import json
import math
from typing import Dict, Any, List, Tuple, Optional

import io
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import pydeck as pdk

# ---- Bring in your shared auth/config + status UI from osdu_app ----
try:
    from osdu_app.config import load_config
    from osdu_app.auth import get_access_token  # we only need to fetch the live token
    from osdu_app.auth_ui import render_auth_status  # to show the timer/auto-refresh UI
    _HAS_OSDU_AUTH = True
except Exception as _e:
    _HAS_OSDU_AUTH = False


def run_wellbore_search_app():
    st.title("Wellbore Search Dashboard")

    # ---- Session state ----
    ss = st.session_state
    ss.setdefault("results_df", pd.DataFrame())
    ss.setdefault("raw_hits", [])
    ss.setdefault("total_count", 0)
    ss.setdefault("clicked_name", None)

    DEFAULT_QUERY = "*"
    DEFAULT_RETURNED_FIELDS = ["*"]
    PAGE_LIMIT = 1000

    # -----------------------------
    # Resolve endpoint from secrets/config (no UI field)
    # -----------------------------
    cfg = load_config() if _HAS_OSDU_AUTH else None
    ENDPOINT = (
        st.secrets.get("SEARCH_SERVICE_BASE_URL", "").strip()
        or st.secrets.get("BASE_URL", "").strip()
        or (getattr(cfg, "base_url", "").strip() if cfg else "")
    )
    if not ENDPOINT:
        st.error("Missing SEARCH_SERVICE_BASE_URL (or base_url) in .streamlit/secrets.toml / config.")
        st.stop()

    # -----------------------------
    # Utility functions
    # -----------------------------
    def normalize_token(raw: str) -> str:
        if not raw:
            return ""
        t = raw.strip()
        if t.lower().startswith("bearer "):
            t = t[7:].strip()
        return t.replace("\n", "").replace("\r", "").replace("\t", "")

    def build_headers(token: str, partition: str) -> Dict[str, str]:
        return {
            "Authorization": "Bearer " + token,
            "data-partition-id": partition,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # -----------------------------
    # Geo helpers
    # -----------------------------
    def _is_num(x: Any) -> bool:
        try:
            return isinstance(x, (int, float)) or (isinstance(x, str) and x.strip() != "")
        except Exception:
            return False

    def _normalize_lon_lat(a: Any, b: Any) -> Optional[Tuple[float, float]]:
        """Return (lon, lat) if a/b can be interpreted as lon/lat or lat/lon."""
        if not (_is_num(a) and _is_num(b)):
            return None
        try:
            a, b = float(a), float(b)
        except Exception:
            return None

        # normal lon,lat
        if -180 <= a <= 180 and -90 <= b <= 90:
            return a, b
        # maybe reversed lat,lon
        if -90 <= a <= 90 and -180 <= b <= 180:
            return b, a
        return None

    def _find_first_coordinates(obj: Any) -> Optional[Tuple[float, float]]:
        """Search any nested structure for something that looks like coordinates."""
        if obj is None:
            return None

        if isinstance(obj, (list, tuple)) and len(obj) == 2:
            return _normalize_lon_lat(obj[0], obj[1])

        if isinstance(obj, dict):
            if "coordinates" in obj:
                coords = obj["coordinates"]
                if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                    norm = _normalize_lon_lat(coords[0], coords[1])
                    if norm:
                        return norm
            # DFS into dict
            for v in obj.values():
                got = _find_first_coordinates(v)
                if got:
                    return got

        if isinstance(obj, list):
            for it in obj:
                got = _find_first_coordinates(it)
                if got:
                    return got

        return None

    def extract_latlon_from_hit(hit: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        """Try multiple strategies to get (lat, lon) from an OSDU search hit."""
        data = hit.get("data") or {}

        # Explicit fields (WGS84)
        lat = data.get("latitudeWgs84")
        lon = data.get("longitudeWgs84")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except Exception:
                pass

        # Common generic keys (possibly reversed)
        for lat_key in ["Latitude", "latitude", "Lat", "lat"]:
            for lon_key in ["Longitude", "longitude", "Lon", "lon"]:
                lat = data.get(lat_key)
                lon = data.get(lon_key)
                if lat is not None and lon is not None:
                    norm = _normalize_lon_lat(lon, lat)  # normalize expects (a,b)
                    if norm:
                        # returned as (lon, lat) -> flip to (lat, lon)
                        return norm[1], norm[0]

        # Scan nested structures
        norm = _find_first_coordinates(data)
        if norm:
            return norm[1], norm[0]

        norm = _find_first_coordinates(hit)
        if norm:
            return norm[1], norm[0]

        return None, None

    # -----------------------------
    # API Search logic
    # -----------------------------
    def call_search_query(
        endpoint: str,
        partition: str,
        token: str,
        kind: str,
        query_str: str,
        returned_fields: List[str],
        limit: int,
        cursor: Optional[str] = None,
    ):
        url = endpoint.rstrip("/") + "/api/search/v2/query"

        body = {
            "kind": kind,
            "limit": min(max(limit, 1), 1000),
            "query": query_str,
        }
        if returned_fields:
            body["returnedFields"] = returned_fields
        if cursor:
            body["cursor"] = cursor

        headers = build_headers(token, partition)
        resp = requests.post(url, headers=headers, json=body, timeout=25)

        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}

        return resp.status_code, payload

    def fetch_all_pages(
        endpoint: str,
        partition: str,
        token: str,
        kind: str,
        query_str: str,
        returned_fields: List[str],
        limit: int,
    ):
        all_hits: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        total_count_seen: Optional[int] = None
        page = 1

        status_box = st.empty()

        while True:
            status, payload = call_search_query(
                endpoint, partition, token, kind, query_str, returned_fields, limit, cursor
            )

            if status != 200:
                st.error(f"Search failed. HTTP {status}")
                message = payload.get("message") if isinstance(payload, dict) else None
                if message:
                    st.error(str(message))
                break

            hits = payload.get("results") or []

            if total_count_seen is None:
                total_count_seen = payload.get("totalCount")

            all_hits.extend(hits)
            status_box.info(f"Fetching page {page}: {len(hits)} hits")

            cursor = payload.get("cursor")
            page += 1

            if not cursor or not hits:
                break

        status_box.empty()
        return all_hits, int(total_count_seen or len(all_hits))

    def flatten_hits(hits: List[Dict[str, Any]]) -> pd.DataFrame:
        rows = []
        for h in hits:
            data = h.get("data") or {}
            lat, lon = extract_latlon_from_hit(h)

            name = (
                data.get("wellName")
                or data.get("Name")
                or data.get("WellboreName")
                or ""
            )

            rows.append(
                {
                    "Name": name,
                    "UWI": data.get("uwi") or "",
                    "WellboreID": data.get("WellboreID") or "",
                    "WellID": data.get("WellID") or "",
                    "OperatingEnvironment": data.get("operatingEnvironment") or "",
                    "WellboreOrientation": data.get("wellboreOrientation") or "",
                    "StartDate": data.get("startDate") or data.get("SpudDate") or "",
                    "EndDate": data.get("endDate") or "",
                    "latitude": lat,
                    "longitude": lon,
                    "id": h.get("id") or "",
                }
            )
        return pd.DataFrame(rows)

    # -----------------------------
    # UI - MAIN PAGE (Configuration moved here, endpoint removed)
    # -----------------------------
    st.divider()
    st.subheader("Configuration")

    # Optional: show live token status/auto-refresh UI on the main page
    if _HAS_OSDU_AUTH:
        render_auth_status(location="main", enable_live_timer=True)
    else:
        st.warning("Shared auth module (osdu_app) not found. Using manual token path is disabled.")

    # Configuration inputs (no endpoint field)
    c1, c2 = st.columns([1, 2])
    with c1:
        partition = st.text_input(
            "Data Partition",
            value=(cfg.data_partition_id if cfg and getattr(cfg, "data_partition_id", None) else "mlc-training"),
            key="wb_search_partition_main",
        )
    with c2:
        kind = st.text_input(
            "Kind",
            value=st.session_state.get("wb_search_kind", "mlc-training:wks:master-data--Wellbore:*"),
            key="wb_search_kind_main",
            placeholder="partition:namespace:entity:version (or wildcard with *)",
        )

    st.caption("Tip: use wildcards, e.g., `*:wks:master-data--Wellbore:*`")

    st.divider()
    run_btn = st.button("Search", key="wb_search_run_main")

    # -----------------------------
    # Run search
    # -----------------------------
    def do_search_all(selected_partition: str, selected_kind: str):
        # Get token from your AUTH system
        if not _HAS_OSDU_AUTH:
            st.error("osdu_app auth/config modules are not available — cannot fetch access token.")
            return

        try:
            token = normalize_token(get_access_token(cfg))
        except Exception as e:
            st.error(f"Auth error: {e}")
            return

        if not selected_partition or not selected_kind:
            st.error("Please fill all required fields (Data Partition, Kind).")
            return

        with st.spinner("Searching..."):
            hits, total = fetch_all_pages(
                ENDPOINT, selected_partition, token, selected_kind,
                DEFAULT_QUERY, DEFAULT_RETURNED_FIELDS, PAGE_LIMIT
            )

            df = flatten_hits(hits)

            # --- Ensure UWI shows without commas (display-only formatting) ---
            if "UWI" in df.columns:
                df["UWI"] = df["UWI"].astype(str).str.replace(",", "", regex=False)

            # Ensure columns exist even if results are empty, to avoid KeyError
            for col in ["latitude", "longitude", "StartDate", "EndDate"]:
                if col not in df.columns:
                    df[col] = pd.Series(dtype="float64" if col in ["latitude", "longitude"] else "object")

            # Robust numeric conversion (coerce invalid values to NaN)
            if "latitude" in df.columns:
                df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce").round(8)
            if "longitude" in df.columns:
                df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce").round(8)

            # Normalize StartDate/EndDate to YYYY-MM-DD (drop time / TZ)
            for col in ["StartDate", "EndDate"]:
                if col in df.columns:
                    dt = pd.to_datetime(df[col], errors="coerce", utc=True)
                    df[col] = dt.dt.strftime("%Y-%m-%d").fillna("")

            # Save to session state
            ss.results_df = df
            ss.raw_hits = hits
            ss.total_count = total
            ss.clicked_name = None

            # Cache last selections
            st.session_state["wb_search_kind"] = selected_kind

    if run_btn:
        do_search_all(partition.strip(), kind.strip())

    # -----------------------------
    # Render results
    # -----------------------------
    df = ss.results_df

    if df.empty:
        st.info("Enter configuration and click Search.")
        return

    # Preferred column order
    preferred = [
        "Name",
        "UWI",
        "WellboreID",
        "WellID",
        "OperatingEnvironment",
        "WellboreOrientation",
        "StartDate",
        "EndDate",
        "latitude",
        "longitude",
        "id",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]

    # -----------------------------
    # Build Excel (or CSV fallback) buffer safely
    # -----------------------------
    def build_export_buffer(export_df: pd.DataFrame) -> Tuple[io.BytesIO, str, bool]:
        """
        Returns (buffer, mime_type, is_excel).
        Tries openpyxl, falls back to xlsxwriter; if neither available, falls back to CSV.
        """
        # Ensure numeric types are export-friendly
        for c in ["latitude", "longitude"]:
            if c in export_df.columns:
                export_df[c] = pd.to_numeric(export_df[c], errors="coerce")

        # Try engines in order: openpyxl -> xlsxwriter
        engine = None
        try:
            import openpyxl  # noqa: F401
            engine = "openpyxl"
        except Exception:
            try:
                import xlsxwriter  # noqa: F401
                engine = "xlsxwriter"
            except Exception:
                engine = None

        if engine:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine=engine) as writer:
                export_df.to_excel(writer, index=False, sheet_name="Results")

                # Width tuning
                if engine == "openpyxl":
                    ws = writer.sheets["Results"]
                    from openpyxl.utils import get_column_letter
                    for idx, col_name in enumerate(export_df.columns, start=1):
                        try:
                            max_len = max(
                                (export_df[col_name].astype(str).str.len().max() or 0),
                                len(str(col_name)),
                            )
                        except Exception:
                            max_len = len(str(col_name))
                        ws.column_dimensions[get_column_letter(idx)].width = min(40, max(12, max_len + 2))
                elif engine == "xlsxwriter":
                    ws = writer.sheets["Results"]
                    for idx, col_name in enumerate(export_df.columns):
                        try:
                            max_len = max(
                                (export_df[col_name].astype(str).str.len().max() or 0),
                                len(str(col_name)),
                            )
                        except Exception:
                            max_len = len(str(col_name))
                        ws.set_column(idx, idx, min(40, max(12, max_len + 2)))

            buffer.seek(0)
            return buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", True

        # Fallback to CSV if no engine is present
        csv_io = io.StringIO()
        export_df.to_csv(csv_io, index=False)
        buffer = io.BytesIO(csv_io.getvalue().encode("utf-8"))
        return buffer, "text/csv", False

    export_df = df[cols].copy()
    export_buffer, export_mime, is_excel = build_export_buffer(export_df)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---- Header row with right-aligned Export button (toolbar feel)
    hdr_c1, hdr_c2 = st.columns([6, 1])
    with hdr_c1:
        st.subheader("Search Results")
        st.caption(f"Total records: {ss.total_count}")
    with hdr_c2:
        st.download_button(
            label="📥 Excel" if is_excel else "📥 CSV",
            data=export_buffer,
            file_name=f"wellbore_search_results_{ts}.{'xlsx' if is_excel else 'csv'}",
            mime=export_mime,
            key="wb_search_export",
        )

    #if not is_excel:
        #st.info(
            #"XLSX export requires either `openpyxl` or `xlsxwriter`. "
            #"Install one of them and rerun: `pip install openpyxl` or `pip install xlsxwriter`.",
            #icon="ℹ️",
        #)

    # ---- Results table
    df_valid = df.dropna(subset=["latitude", "longitude"]).copy()
    st.dataframe(df[cols], height=380, use_container_width=True)

    if df_valid.empty:
        st.warning("No valid coordinates found in the results to plot on the map.")
        return

    names = ["(None)"] + df_valid["Name"].fillna("").tolist()
    selected_default = ss.clicked_name if ss.clicked_name else "(None)"
    try:
        selected_index = names.index(selected_default)
    except ValueError:
        selected_index = 0

    selected_name = st.selectbox(
        "Select Wellbore to Zoom",
        names,
        index=selected_index,
    )

    # -----------------------------
    # Map
    # -----------------------------
    st.markdown("### Map")

    mdf = df_valid.copy()

    # Compute view
    if selected_name != "(None)":
        row_match = mdf[mdf["Name"] == selected_name]
        if not row_match.empty:
            row = row_match.iloc[0]
            center_lat = float(row["latitude"])
            center_lon = float(row["longitude"])
            zoom = 13
            mdf["is_selected"] = mdf["Name"] == selected_name
        else:
            # Fallback to extent view if selected item vanished
            selected_name = "(None)"
            min_lat, max_lat = mdf["latitude"].min(), mdf["latitude"].max()
            min_lon, max_lon = mdf["longitude"].min(), mdf["longitude"].max()
            center_lat = float((min_lat + max_lat) / 2)
            center_lon = float((min_lon + max_lon) / 2)
            span = float(max(max_lat - min_lat, max_lon - min_lon))
            zoom = max(3, min(12, int(10 - span * 10)))
            mdf["is_selected"] = False
    if selected_name == "(None)":
        min_lat, max_lat = mdf["latitude"].min(), mdf["latitude"].max()
        min_lon, max_lon = mdf["longitude"].min(), mdf["longitude"].max()
        center_lat = float((min_lat + max_lat) / 2)
        center_lon = float((min_lon + max_lon) / 2)
        span = float(max(max_lat - min_lat, max_lon - min_lon))
        zoom = max(3, min(12, int(10 - span * 10)))
        mdf["is_selected"] = False

    view = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        pitch=0,
        bearing=0,
    )

    # Layers (non-selected in red; selected in gold)
    red_layer = pdk.Layer(
        "ScatterplotLayer",
        data=mdf.loc[~mdf["is_selected"]],
        get_position="[longitude, latitude]",
        get_radius=600,
        get_fill_color=[230, 57, 70, 220],  # red-ish
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 255, 0, 255],
    )

    highlight_layer = pdk.Layer(
        "ScatterplotLayer",
        data=mdf.loc[mdf["is_selected"]],
        get_position="[longitude, latitude]",
        get_radius=1300,
        get_fill_color=[255, 215, 0, 255],  # gold
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 255, 0, 255],
    )

    tooltip = {"html": "<b>{Name}</b><br/>({latitude}, {longitude})"}

    # Prefer external Positron GL style, but provide a fallback
    try:
        deck = pdk.Deck(
            layers=[red_layer, highlight_layer],
            initial_view_state=view,
            tooltip=tooltip,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        )
    except Exception:
        deck = pdk.Deck(
            layers=[red_layer, highlight_layer],
            initial_view_state=view,
            tooltip=tooltip,
            map_style="light",
        )

    st.pydeck_chart(deck)

    # --- Return to Start ---
    st.divider()
    st.markdown("### Ready to ingest another file?")

    # Use a native page link (works instantly, no rerun)
    st.page_link(
        "pages/05_Entitlements.py",    # <-- adjust if the filename differs
        label="📄 Ingest another file"
        
    )
