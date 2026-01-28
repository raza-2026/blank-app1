
# osdu_app/validators.py (patched)
# Accept both the legacy V1 columns and the new Borehole schema columns.

import pandas as pd
from io import BytesIO

# Legacy schema (what your app originally validated)
REQUIRED_WELLBORE_COLUMNS_V1 = {"UWI", "Name", "Latitude", "Longitude", "TD", "SpudDate", "WellType"}

# New Borehole sample schema (from boreholes_sample01.csv)
# We'll validate case-insensitively and allow *at least* the core set below.
REQUIRED_BOREHOLE_MIN = {
    "wellname",            # maps to Name
    "uwi",                 # maps to UWI
    "latitudewgs84",       # maps to Latitude
    "longitudewgs84",      # maps to Longitude
    "startdate",           # maps to SpudDate
}

# Optional but nice-to-have fields in the new file (not strictly required to pass validation)
OPTIONAL_BOREHOLE = {
    "enddate", "outcomeid", "wellstatus", "wellboreorientation", "boreholetvd",
    "referencelevel", "referencelevelheight", "operatorid", "drillingrigid", "drillingcompany"
}


def _lower(s: str) -> str:
    return (s or "").strip().lower()


def validate_wellbore_csv(file_bytes: bytes) -> tuple[bool, str, int]:
    """
    Validate headers for either:
      - V1 legacy CSV: {UWI, Name, Latitude, Longitude, TD, SpudDate, WellType}
      - New Borehole CSV: at least the minimal core columns defined in REQUIRED_BOREHOLE_MIN

    Returns: (ok, message, row_count)
    """
    try:
        df = pd.read_csv(BytesIO(file_bytes))
    except Exception as e:
        return False, f"CSV read failed: {e}", 0

    row_count = len(df)

    # Exact V1 check (case-sensitive, as before) for backward compatibility
    cols_v1 = set(df.columns)
    if REQUIRED_WELLBORE_COLUMNS_V1.issubset(cols_v1):
        return True, "OK (legacy V1)", row_count

    # Case-insensitive check for Borehole schema
    cols_lower = {_lower(c) for c in df.columns}
    if REQUIRED_BOREHOLE_MIN.issubset(cols_lower):
        missing_opt = sorted(list(OPTIONAL_BOREHOLE - cols_lower))
        note = "; missing optional: " + ", ".join(missing_opt) if missing_opt else ""
        return True, "OK (borehole schema)" + note, row_count

    # Build a helpful message
    missing_v1 = sorted(list(REQUIRED_WELLBORE_COLUMNS_V1 - cols_v1))
    missing_bh = sorted(list(REQUIRED_BOREHOLE_MIN - cols_lower))
    msg = (
        "Unrecognized header set. "
        f"Missing for V1: {missing_v1}; "
        f"Missing for Borehole: {missing_bh}."
    )
    return False, msg, row_count
