#!/usr/bin/env python3
"""
Fetches yesterday's (Greek calendar day) FIFA World Cup results
from football-data.org and posts them to a Discord channel via webhook.

Designed to run at 06:00 UTC (= 09:00 Greek time, EEST UTC+3), which is
after all matches from the previous Greek calendar day have finished.

Runs daily via GitHub Actions (see .github/workflows/results.yml).
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
import requests

FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COMPETITION_CODE = "WC"  # FIFA World Cup, per football-data.org

# Optional: override the date for testing, e.g. "2026-06-15"
DEBUG_DATE = os.environ.get("DEBUG_DATE")


def get_target_date():
    """Returns the UTC date string for 'yesterday' relative to now.

    Since this script runs at 06:00 UTC (09:00 Greek time), the matches
    we want results for happened on the previous UTC calendar date.
    """
    if DEBUG_DATE:
        return DEBUG_DATE
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


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


def filter_finished(matches):
    """Keep only matches that actually finished."""
    return [m for m in matches if m.get("status") == "FINISHED"]


def build_result_embed(match):
    """Builds a Discord embed (poll-style card) showing a final result."""
    home = match["homeTeam"].get("name") or match["homeTeam"].get("shortName") or "TBD"
    away = match["awayTeam"].get("name") or match["awayTeam"].get("shortName") or "TBD"

    stage = match.get("stage", "").replace("_", " ").title()
    group = match.get("group")
    stage_label = stage + (f" – Group {group[-1]}" if group else "")

    score = match.get("score", {}).get("fullTime", {})
    home_goals = score.get("home")
    away_goals = score.get("away")

    title = f"{home}  vs  {away}"

    if home_goals is None or away_goals is None:
        # Shouldn't normally happen for a FINISHED match, but guard anyway
        home_goals, away_goals = "?", "?"
        home_mark, away_mark, draw_mark = "", "", ""
    elif home_goals > away_goals:
        home_mark, away_mark, draw_mark = "✅", "", "—"
    elif away_goals > home_goals:
        home_mark, away_mark, draw_mark = "", "✅", "—"
    else:
        home_mark, away_mark, draw_mark = "", "", "✅"

    fields = [
        {"name": f"1️⃣ {home} win", "value": f"**{home_goals}** {home_mark}", "inline": True},
        {"name": "🤝 Draw", "value": draw_mark, "inline": True},
        {"name": f"2️⃣ {away} win", "value": f"**{away_goals}** {away_mark}", "inline": True},
    ]

    return {
        "title": title,
        "color": 0x2ECC71,  # green for finished
        "fields": fields,
        "footer": {"text": f"Final  ·  {stage_label}"},
    }


def build_header(date_str, matches):
    pretty_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    header = f"📊 **FIFA World Cup — Results for {pretty_date}**"

    if not matches:
        return f"{header}\n\nNo World Cup matches were played that day. ⚽"

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

    date_str = get_target_date()
    matches, error = fetch_matches(date_str)

    if error == "no_access":
        print("World Cup competition not accessible right now (likely off-season). Skipping post.")
        return

    matches = filter_finished(matches)

    # Post the header first (date + count, or "no matches that day")
    header = build_header(date_str, matches)
    print(header)
    post_to_discord(header)

    # Then post each result as its own embed (poll-style card)
    for match in matches:
        embed = build_result_embed(match)
        print(embed["title"], "-", embed["footer"]["text"])
        post_embed_to_discord(embed)
        time.sleep(1)  # stay comfortably under Discord's webhook rate limit

    print(f"Posted header + {len(matches)} result(s) to Discord successfully.")


if __name__ == "__main__":
    main()
