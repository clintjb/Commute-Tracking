import hashlib
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import tweepy

# Variables
CSV_PATH      = "Commute Tracker - Metrics.csv"
MESSAGES_PATH = "messages.csv"
SENT_LOG      = "tweet_sent_log.json"

BASELINE_MINS = 60
WINDOW_HOURS  = 3
LOCAL_TZ      = ZoneInfo("Europe/Berlin")

X_API_KEY             = os.environ["X_API_KEY"]
X_API_SECRET          = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN        = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_TOKEN_SECRET = os.environ["X_ACCESS_TOKEN_SECRET"]

# Helper Functions
def _event_id(row) -> str:
    """SHA-1 fingerprint of date + period — stable across re-runs."""
    return hashlib.sha1(
        f"{row['Date'].date()}_{row['Period']}".encode()
    ).hexdigest()


def _load_sent_log() -> set:
    if os.path.exists(SENT_LOG):
        with open(SENT_LOG) as f:
            return set(json.load(f))
    return set()


def _save_sent_log(log: set) -> None:
    with open(SENT_LOG, "w") as f:
        json.dump(sorted(log), f, indent=2)


def _build_tweet(row) -> str:
    messages = pd.read_csv(MESSAGES_PATH)
    message  = messages["Message"].sample(1).iloc[0]
    delay    = int(row["Duration (mins)"]) - BASELINE_MINS
    return (
        f"@clintjb heute war ich {delay} Minuten zu spät - {message}\n"
        f"Mehr zu eurer Service-Performance:\n"
        f"https://clintbird.com/blog/commute-tracking-post\n"
        f"#dev #hamburg #verspätet"
    )


def _post_tweet(text: str) -> None:
    client = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
    )
    client.create_tweet(text=text)

# Tweet Functions
def maybe_tweet() -> None:
    df = pd.read_csv(CSV_PATH)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    latest = df.sort_values("Date").iloc[-1]

    event_id = _event_id(latest)
    sent_log = _load_sent_log()

    # DeDuplicate NTT (Never Tweet Twice)
    if event_id in sent_log:
        print(f"[tweet] Skipped — already sent for event {event_id[:8]}…")
        return

    # Today + Within Window
    now = datetime.now(tz=LOCAL_TZ)
    if latest["Date"].date() != now.date():
        print(f"[tweet] Skipped — event date {latest['Date'].date()} ≠ today")
        return

    if pd.isna(latest["Arrival Time"]):
        print("[tweet] Skipped — Arrival Time missing")
        return

    try:
        arrival_dt = datetime.combine(
            now.date(),
            datetime.strptime(str(latest["Arrival Time"]).strip(), "%H:%M:%S").time(),
            tzinfo=LOCAL_TZ,
        )
    except ValueError:
        print(f"[tweet] Skipped — Arrival Time '{latest['Arrival Time']}' could not be parsed")
        return

    mins_elapsed = (now - arrival_dt).total_seconds() / 60
    if not (0 <= mins_elapsed <= WINDOW_HOURS * 60):
        print(f"[tweet] Skipped — arrival was {mins_elapsed:.0f} min ago (window 0–{WINDOW_HOURS * 60} min)")
        return

    # Only Tweet On Red
    if latest["RAG"] != "Red":
        print(f"[tweet] Skipped — RAG is {latest['RAG']} (requires Red)")
        return

    # If Passed Bild And Send
    text = _build_tweet(latest)
    print(f"[tweet] Sending:\n  {text}")
    _post_tweet(text)

    sent_log.add(event_id)
    _save_sent_log(sent_log)
    print(f"[tweet] Done — event {event_id[:8]}… logged to {SENT_LOG}")


if __name__ == "__main__":
    maybe_tweet()
