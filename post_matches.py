#!/usr/bin/env python3
"""
Fetches today's FIFA World Cup matches from football-data.org
and posts them to a Discord channel via webhook.

Runs daily via GitHub Actions (see .github/workflows/daily.yml).
"""

import os
import sys
from datetime import datetime, timezone
import requests

FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COMPETITION_CODE = "WC"  # FIFA World Cup, per football-data.org

# Optional: override the date for testing, e.g. "2026-06-15"
DEBUG_DATE = os.environ.get("DEBUG_DATE")

STATUS_EMOJI = {
    "SCHEDULED": "🕒",
    "TIMED": "🕒",
    "IN_PLAY": "🔴",
    "PAUSED": "⏸️",
    "FINISHED": "✅",
    "POSTPONED": "⚠️",
    "SUSPENDED": "⚠️",
    "CANCELLED": "❌",
}


def get_today():
    if DEBUG_DATE:
        return DEBUG_DATE
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_matches(date_str):
    url = f"https://api.football-data.org/v4/competitions/{COMPETITION_CODE}/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    params = {"dateFrom": date_str, "dateTo": date_str}

    resp = requests.get(url, headers=headers, params=params, timeout=20)

    if resp.status_code == 403:
        # Competition not currently active / not in free tier season window
        return None, "no_access"
    resp.raise_for_status()

    data = resp.json()
    return data.get("matches", []), None


def format_match(match):
    home = match["homeTeam"].get("name") or match["homeTeam"].get("shortName") or "TBD"
    away = match["awayTeam"].get("name") or match["awayTeam"].get("shortName") or "TBD"
    status = match.get("status", "SCHEDULED")
    emoji = STATUS_EMOJI.get(status, "🕒")

    utc_date = match.get("utcDate", "")
    try:
        dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
        time_str = dt.strftime("%H:%M UTC")
    except Exception:
        time_str = "TBD"

    stage = match.get("stage", "").replace("_", " ").title()
    group = match.get("group")
    stage_label = f"{stage}" + (f" – Group {group[-1]}" if group else "")

    score = match.get("score", {}).get("fullTime", {})
    home_goals = score.get("home")
    away_goals = score.get("away")

    if status in ("IN_PLAY", "PAUSED", "FINISHED") and home_goals is not None:
        result = f"**{home} {home_goals} - {away_goals} {away}**"
    else:
        result = f"**{home} vs {away}**"

    if status == "FINISHED":
        time_part = "Final"
    elif status in ("IN_PLAY", "PAUSED"):
        time_part = "Live now"
    else:
        time_part = time_str

    return f"{emoji} {result}  ·  {time_part}  ·  _{stage_label}_"


def build_message(date_str, matches):
    pretty_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    header = f"🏆 **FIFA World Cup — Matches for {pretty_date}**"

    if not matches:
        return f"{header}\n\nNo World Cup matches scheduled today. ⚽"

    lines = [format_match(m) for m in matches]
    return header + "\n\n" + "\n".join(lines)


def post_to_discord(content):
    resp = requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=20)
    resp.raise_for_status()


def main():
    if not FOOTBALL_DATA_TOKEN:
        print("ERROR: FOOTBALL_DATA_TOKEN is not set", file=sys.stderr)
        sys.exit(1)
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        sys.exit(1)

    date_str = get_today()
    matches, error = fetch_matches(date_str)

    if error == "no_access":
        print("World Cup competition not accessible right now (likely off-season). Skipping post.")
        return

    message = build_message(date_str, matches)
    print(message)  # also visible in GitHub Actions logs
    post_to_discord(message)
    print("Posted to Discord successfully.")


if __name__ == "__main__":
    main()
