#!/usr/bin/env python3
"""
Checks Southeastern departures between two stations (via the Huxley2 proxy
for National Rail's Darwin API) and sends a push notification via ntfy.sh
if any train is delayed or cancelled.

Only sends notifications inside a configurable local time window — outside
that window it exits quietly. Configure via environment variables so the
same script can drive multiple routes/windows (e.g. morning commute in,
evening commute back) from different GitHub Actions workflows.
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# ---- Config (all overridable via env vars, so one script can serve
# multiple routes from different workflow files) ----
FROM_CRS = os.environ.get("FROM_CRS", "ORP")            # Orpington
TO_CRS = os.environ.get("TO_CRS", "LBG")                 # London Bridge
FROM_NAME = os.environ.get("FROM_NAME", "Orpington")
TO_NAME = os.environ.get("TO_NAME", "London Bridge")
NUM_ROWS = int(os.environ.get("NUM_ROWS", "10"))          # upcoming departures to check
START_TIME = os.environ.get("START_TIME", "05:00")         # local "HH:MM", ignore runs before this
CUTOFF_TIME = os.environ.get("CUTOFF_TIME", "10:00")        # local "HH:MM", stop notifying at/after this
STATE_FILE = os.environ.get("STATE_FILE", "state.json")     # separate file per route to keep dedup independent
HUXLEY_BASE = "https://huxley2.azurewebsites.net"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
if not NTFY_TOPIC:
    print("NTFY_TOPIC env var not set — cannot send notifications.", file=sys.stderr)
    sys.exit(1)


def get_local_time():
    return datetime.now(ZoneInfo("Europe/London"))


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_departures():
    url = f"{HUXLEY_BASE}/departures/{FROM_CRS}/to/{TO_CRS}/{NUM_ROWS}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


def send_notification(title, message, priority="default", tags=None):
    # Use ntfy's JSON publish endpoint rather than custom headers — headers
    # must be Latin-1, which breaks on emoji/unicode in the title. JSON body
    # handles UTF-8 fine.
    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": message,
        "priority": {"min": 1, "low": 2, "default": 3, "high": 4, "max": 5}.get(priority, 3),
    }
    if tags:
        payload["tags"] = [t.strip() for t in tags.split(",")]
    requests.post(
        "https://ntfy.sh/",
        json=payload,
        timeout=10,
    )


def main():
    now = get_local_time()
    today_key = now.strftime("%Y-%m-%d")

    if not (START_TIME <= now.strftime("%H:%M") < CUTOFF_TIME):
        print(f"Local time {now.strftime('%H:%M')} is outside the {START_TIME}-{CUTOFF_TIME} "
              f"window — skipping.")
        return

    try:
        data = fetch_departures()
    except requests.RequestException as e:
        print(f"Error fetching departures: {e}", file=sys.stderr)
        return

    services = data.get("trainServices") or []
    if not services:
        print("No upcoming services returned.")
        return

    state = load_state()
    # Reset state daily so yesterday's notified delays don't suppress today's
    if state.get("date") != today_key:
        state = {"date": today_key, "notified": {}}
    notified = state.setdefault("notified", {})

    problems = []
    for svc in services:
        std = svc.get("std")  # scheduled departure time, e.g. "07:42"
        etd = svc.get("etd")  # estimated: "On time", "Cancelled", or a time
        platform = svc.get("platform") or "TBC"
        service_id = svc.get("serviceIdGuid") or svc.get("serviceIdUrlSafe") or std

        if not std or not etd:
            continue

        is_on_time = etd.strip().lower() == "on time"
        if is_on_time:
            # Clear any prior notified state for this slot once it recovers
            notified.pop(service_id, None)
            continue

        # Delayed or cancelled — only notify if status changed since last check
        if notified.get(service_id) == etd:
            continue  # already notified about this exact status

        notified[service_id] = etd

        if etd.strip().lower() == "cancelled":
            reason = svc.get("cancelReason", "")
            problems.append(f"{std} to {TO_NAME} — CANCELLED" + (f" ({reason})" if reason else ""))
        else:
            problems.append(f"{std} to {TO_NAME} — now expected {etd} (platform {platform})")

    save_state(state)

    if problems:
        message = "\n".join(problems)
        print("Delays/cancellations found:\n" + message)
        send_notification(
            title=f"⚠️ Southeastern: {FROM_NAME} → {TO_NAME}",
            message=message,
            priority="high",
            tags="warning,train",
        )
    else:
        print("All checked services on time (or already notified).")


if __name__ == "__main__":
    main()
