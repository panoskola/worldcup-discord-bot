#!/usr/bin/env python3
"""
Fetches yesterday's (US Eastern calendar day) FIFA World Cup results
from football-data.org and posts them to a Discord channel via webhook.

Designed to run at 06:00 UTC (~09:00 Greek time), which is comfortably
after even the latest standard World Cup kickoff slot (9 PM Eastern) has
finished, so the full previous US Eastern match day's results are final.

Match-day anchoring matches post_matches.py (also US Eastern) for
consistency between the "upcoming" and "results" posts.

Runs daily via GitHub Actions (see .github/workflows/results.yml).
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests

FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COMPETITION_CODE = "WC"  # FIFA World Cup, per football-data.org
GREEK_TZ = ZoneInfo("Europe/Athens")   # used only to determine "has the run-time arrived yet"
US_TZ = ZoneInfo("America/New_York")   # used to anchor "match day", matching official schedules

# Optional: override the date for testing, e.g. "2026-06-15"
DEBUG_DATE = os.environ.get("DEBUG_DATE")


def get_target_date():
    """Returns yesterday's date string, using the US EASTERN calendar day.

    The script runs at 06:00 UTC (~09:00 Greek time). By that point, even
    the latest standard World Cup slot (9 PM Eastern) has finished — so we
    can safely report on the full previous US Eastern match day, matching
    the same day-anchoring used by post_matches.py for consistency.
    """
    if DEBUG_DATE:
        return DEBUG_DATE
    now_us = datetime.now(US_TZ)
    yesterday_us = now_us - timedelta(days=1)
    return yesterday_us.strftime("%Y-%m-%d")


def us_day_utc_range(us_date_str):
    """Given a US Eastern calendar date (YYYY-MM-DD), returns the UTC date
    range that fully covers that Eastern day, as (dateFrom_str, dateTo_str).

    A US Eastern day can span two UTC calendar dates, so we query a day on
    each side to be safe and filter precisely afterward.
    """
    us_date = datetime.strptime(us_date_str, "%Y-%m-%d").replace(tzinfo=US_TZ)
    date_from = (us_date - timedelta(days=1)).strftime("%Y-%m-%d")
    date_to = (us_date + timedelta(days=1)).strftime("%Y-%m-%d")
    return date_from, date_to


def filter_to_us_day(matches, us_date_str):
    """Keep only matches whose kickoff, converted to US Eastern time, falls
    on the given Eastern calendar date."""
    result = []
    for m in matches:
        try:
            dt_utc = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            dt_us = dt_utc.astimezone(US_TZ)
            if dt_us.strftime("%Y-%m-%d") == us_date_str:
                result.append(m)
        except Exception:
            continue
    return result


def fetch_matches(date_from, date_to):
    url = f"https://api.football-data.org/v4/competitions/{COMPETITION_CODE}/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    params = {"dateFrom": date_from, "dateTo": date_to}

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
    date_from, date_to = us_day_utc_range(date_str)
    matches, error = fetch_matches(date_from, date_to)

    if error == "no_access":
        print("World Cup competition not accessible right now (likely off-season). Skipping post.")
        return

    matches = filter_to_us_day(matches, date_str)
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
