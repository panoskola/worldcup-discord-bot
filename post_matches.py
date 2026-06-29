#!/usr/bin/env python3
"""
Fetches today's FIFA World Cup matches from football-data.org
and posts them to a Discord channel via webhook.

Runs daily via GitHub Actions (see .github/workflows/daily.yml).
"""

import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests

FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COMPETITION_CODE = "WC"  # FIFA World Cup, per football-data.org
GREEK_TZ = ZoneInfo("Europe/Athens")  # handles EET/EEST automatically

# Optional: override the date for testing, e.g. "2026-06-15"
DEBUG_DATE = os.environ.get("DEBUG_DATE")


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


def filter_upcoming(matches):
    """Keep only matches that haven't started yet."""
    upcoming_statuses = {"SCHEDULED", "TIMED"}
    return [m for m in matches if m.get("status") in upcoming_statuses]


def build_match_embed(match):
    """Builds a Discord embed (poll-style card) for an upcoming match."""
    home = match["homeTeam"].get("name") or match["homeTeam"].get("shortName") or "TBD"
    away = match["awayTeam"].get("name") or match["awayTeam"].get("shortName") or "TBD"

    utc_date = match.get("utcDate", "")
    try:
        dt_utc = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
        dt_greek = dt_utc.astimezone(GREEK_TZ)
        time_str = dt_greek.strftime("%H:%M") + " Greek time"
    except Exception:
        time_str = "TBD"

    stage = match.get("stage", "").replace("_", " ").title()
    group = match.get("group")
    stage_label = stage + (f" – Group {group[-1]}" if group else "")

    title = f"{home}  vs  {away}"

    fields = [
        {"name": f"1️⃣ {home} win", "value": "Kickoff " + time_str, "inline": True},
        {"name": "🤝 Draw", "value": "—", "inline": True},
        {"name": f"2️⃣ {away} win", "value": "Kickoff " + time_str, "inline": True},
    ]
    footer_text = f"Scheduled  ·  {stage_label}"
    color = 0x3498DB  # blue for scheduled

    return {
        "title": title,
        "color": color,
        "fields": fields,
        "footer": {"text": footer_text},
    }


def build_header(date_str, matches):
    pretty_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    header = f"🏆 **FIFA World Cup — Upcoming Matches for {pretty_date}**"

    if not matches:
        return f"{header}\n\nNo more upcoming World Cup matches today. ⚽"

    return header


def post_embed_to_discord(embed):
    resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=20)
    resp.raise_for_status()


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

    matches = filter_upcoming(matches)

    # Post the header first (date + count, or "no matches today")
    header = build_header(date_str, matches)
    print(header)
    post_to_discord(header)

    # Then post each match as its own embed (poll-style card)
    for match in matches:
        embed = build_match_embed(match)
        print(embed["title"], "-", embed["footer"]["text"])
        post_embed_to_discord(embed)
        time.sleep(1)  # stay comfortably under Discord's webhook rate limit

    print(f"Posted header + {len(matches)} match message(s) to Discord successfully.")


if __name__ == "__main__":
    main()
