import csv
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

CSV_PATH     = "Commute Tracker - Metrics.csv"
FRESH_FLAG   = ".fresh"
WINDOW_HOURS = 5
LOCAL_TZ     = ZoneInfo("Europe/Berlin")


def export_sheet() -> None:
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scopes     = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds      = Credentials.from_service_account_info(creds_json, scopes=scopes)
    gc         = gspread.authorize(creds)

    ws   = gc.open_by_key(os.environ["GOOGLE_SHEET_ID"]).worksheet("Metrics")
    rows = ws.get_all_values()

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    print(f"[fetch] Exported {len(rows) - 1} data rows from 'Metrics' tab")


def is_fresh() -> bool:
    df = pd.read_csv(CSV_PATH)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    latest = df.sort_values("Date").iloc[-1]
    now    = datetime.now(tz=LOCAL_TZ)

    # Must be today (in local time)
    if latest["Date"].date() != now.date():
        print(f"[fetch] Latest row is {latest['Date'].date()}, not today — skipping")
        return False

    # Arrival must be parseable — column is a bare time string e.g. "17:59:28"
    arrival_raw = latest.get("Arrival Time", None)
    if not arrival_raw or pd.isna(arrival_raw):
        print("[fetch] Arrival Time is missing — skipping")
        return False

    try:
        arrival_dt = datetime.combine(
            now.date(),
            datetime.strptime(str(arrival_raw).strip(), "%H:%M:%S").time(),
            tzinfo=LOCAL_TZ,
        )
    except ValueError:
        print(f"[fetch] Arrival Time '{arrival_raw}' could not be parsed — skipping")
        return False

    mins_since = (now - arrival_dt).total_seconds() / 60

    if not (0 <= mins_since <= WINDOW_HOURS * 60):
        print(f"[fetch] Arrival was {mins_since:.0f} min ago (window is 0–{WINDOW_HOURS * 60} min) — skipping")
        return False

    print(f"[fetch] Fresh data found — {latest['Period']} on {latest['Date'].date()}, arrived {mins_since:.0f} min ago")
    return True


if __name__ == "__main__":
    export_sheet()
    fresh = is_fresh()

    with open(FRESH_FLAG, "w") as f:
        f.write("true" if fresh else "false")

    # GitHub Actions Output So The Workflow Can Branch On It
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"fresh={str(fresh).lower()}\n")
