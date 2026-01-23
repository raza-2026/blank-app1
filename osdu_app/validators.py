
import pandas as pd
from io import BytesIO


REQUIRED_WELLBORE_COLUMNS = {"UWI", "Name", "Latitude", "Longitude", "TD", "SpudDate", "WellType"}


def validate_wellbore_csv(file_bytes: bytes) -> tuple[bool, str, int]:
    try:
        df = pd.read_csv(BytesIO(file_bytes))
    except Exception as e:
        return False, f"CSV read failed: {e}", 0

    missing = REQUIRED_WELLBORE_COLUMNS - set(df.columns)
    if missing:
        return False, f"Missing columns: {sorted(list(missing))}", len(df)

    return True, "OK", len(df)
