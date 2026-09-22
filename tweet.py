import hashlib
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import tweepy
from atproto import Client as BskyClient

# Variables
CSV_PATH      = "Commute Tracker - Metrics.csv"
MESSAGES_PATH = "messages.csv"
SENT_LOG      = "tweet_sent_log.json"

BASELINE_MINS     = 60
WINDOW_HOURS      = 3
LOCAL_TZ          = ZoneInfo("Europe/Berlin")
MAX_DURATION_MINS = 150  # 2.5h — beyond this, treat as a bad/duplicate timestamp, not a real trip

X_API_KEY             = os.environ["X_API_KEY"]
X_API_SECRET          = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN        = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_TOKEN_SECRET = os.environ["X_ACCESS_TOKEN_SECRET"]
 
BSKY_HANDLE   = os.environ["BSKY_HANDLE"]
BSKY_PASSWORD = os.environ["BSKY_PASSWORD"]

# Helper Functions
def _event_id(row) -> str:
    """SHA-1 fingerprint of date + period — stable across re-runs."""
    return hashlib.sha1(
        f"{row['Date'].date()}_{row['Period']}".encode()
    ).hexdigest()
 
 
def _load_sent_log() -> dict:
    """
    Maps event_id -> {"x": bool, "bluesky": bool}, so a platform that
    already succeeded is never retried (and never double-posted) even if
    a *different* platform failed and the run crashed partway through.
    """
    if os.path.exists(SENT_LOG):
        with open(SENT_LOG) as f:
            raw = json.load(f)
        # Backwards-compat: migrate old flat list-of-event_id format.
        if isinstance(raw, list):
            return {event_id: {"x": True, "bluesky": True} for event_id in raw}
        return raw
    return {}
 
 
def _save_sent_log(log: dict) -> None:
    with open(SENT_LOG, "w") as f:
        json.dump(log, f, indent=2, sort_keys=True)
 
 
def _build_post(row) -> str:
    messages = pd.read_csv(MESSAGES_PATH)
    message  = messages["Message"].sample(1).iloc[0]
    delay    = int(row["Duration (mins)"]) - BASELINE_MINS
    return (
        f"Hey @hochbahn heute war ich {delay} Minuten zu spät - {message}.\n"
        f"Mehr zu eurer Service-Performance: https://clintbird.com/blog/commute-tracking-post\n"
        f"#hvv #hamburg #verspätet #bahn"
    )
 
 
def _post_tweet(text: str) -> None:
    client = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
    )
    client.create_tweet(text=text)
 
 
def _build_bsky_facets(text: str) -> list:
    """
    Build Bluesky facets for URLs and hashtags.
    Facets use UTF-8 byte offsets, not character offsets.
    """
    import re
    facets = []
    encoded = text.encode("utf-8")

    # URLs
    for m in re.finditer(r"https?://[^\s]+", text):
        url = m.group(0)
        byte_start = len(text[: m.start()].encode("utf-8"))
        byte_end   = byte_start + len(url.encode("utf-8"))
        facets.append({
            "$type": "app.bsky.richtext.facet",
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        })

    # Hashtags — Bluesky tag feature strips the leading #
    for m in re.finditer(r"#(\w+)", text):
        byte_start = len(text[: m.start()].encode("utf-8"))
        byte_end   = byte_start + len(m.group(0).encode("utf-8"))
        facets.append({
            "$type": "app.bsky.richtext.facet",
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}],
        })

    return facets


def _post_bluesky(text: str) -> None:
    # Bluesky has a 300-character limit
    if len(text) > 300:
        text = text[:297] + "…"
    facets = _build_bsky_facets(text)
    client = BskyClient()
    client.login(BSKY_HANDLE, BSKY_PASSWORD)
    client.send_post(text=text, facets=facets)
 
 
# Tweet Functions
def maybe_tweet() -> None:
    df = pd.read_csv(CSV_PATH)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
 
    # Drop rows with an implausible duration (double/missed timestamp in
    # the sheet) — never tweet about one of these.
    bad = df["Duration (mins)"] > MAX_DURATION_MINS
    if bad.any():
        print(f"[tweet] Ignoring {bad.sum()} row(s) with Duration > {MAX_DURATION_MINS} min (likely bad timestamp)")
        df = df[~bad]
 
    if df.empty:
        print("[tweet] Skipped — no valid rows after filtering")
        return
 
    latest = df.sort_values("Date").iloc[-1]
 
    event_id = _event_id(latest)
    sent_log = _load_sent_log()
    status   = sent_log.get(event_id, {"x": False, "bluesky": False})
 
    # DeDuplicate NTT (Never Tweet Twice) — only fully skip once BOTH
    # platforms have succeeded for this event. A partial prior failure
    # (e.g. X succeeded, Bluesky didn't) falls through so we can retry
    # just the platform that's still missing.
    if status["x"] and status["bluesky"]:
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
 
    # Build post text once, share across both platforms
    text = _build_post(latest)
    print(f"[tweet] Sending:\n  {text}")
 
    errors = []
 
    if status["x"]:
        print("[tweet] X/Twitter already posted for this event — skipping")
    else:
        try:
            _post_tweet(text)
            status["x"] = True
            sent_log[event_id] = status
            _save_sent_log(sent_log)  # persist immediately, before touching Bluesky
            print("[tweet] Posted to X/Twitter")
        except Exception as exc:
            errors.append(f"X/Twitter: {exc}")
            print(f"[tweet] FAILED to post to X/Twitter: {exc}")
 
    if status["bluesky"]:
        print("[bluesky] Bluesky already posted for this event — skipping")
    else:
        try:
            _post_bluesky(text)
            status["bluesky"] = True
            sent_log[event_id] = status
            _save_sent_log(sent_log)
            print("[bluesky] Posted to Bluesky")
        except Exception as exc:
            errors.append(f"Bluesky: {exc}")
            print(f"[bluesky] FAILED to post to Bluesky: {exc}")
 
    if errors:
        # Don't silently succeed — surface the failure (e.g. so CI marks
        # the job as failed) while leaving whichever platform DID
        # succeed correctly recorded in the sent log above.
        raise RuntimeError(
            f"[tweet] Completed with errors for event {event_id[:8]}…: "
            + "; ".join(errors)
        )
 
    print(f"[tweet] Done — event {event_id[:8]}… fully logged to {SENT_LOG}")
 
 
if __name__ == "__main__":
    maybe_tweet()
