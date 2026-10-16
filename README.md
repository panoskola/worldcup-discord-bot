# worldcup-discord-bot

A small for-fun bot that posted the FIFA World Cup 2026 schedule and results to a Discord
server every day. There is no server behind it: two Python scripts run on a schedule in
GitHub Actions and post through a Discord webhook.

## What it does

| Workflow | Script | When (UTC) | Posts |
|---|---|---|---|
| `daily.yml` | `post_matches.py` | 08:00 | Today's upcoming matches, one card per match, kickoff in Greek time |
| `results.yml` | `results.py` | 06:00 | Yesterday's final scores, winner marked ✅ |

Both workflows can also be started by hand from the **Actions** tab (`workflow_dispatch`).

## How it works

```
GitHub Actions (cron) ──► Python 3.12 ──► football-data.org API v4 ──► Discord webhook
```

1. Work out the target "match day" in US Eastern time.
2. Query the API for that day plus one day either side (a US day spans two UTC dates).
3. Keep only matches whose kickoff falls on the target Eastern day, then only upcoming
   (`SCHEDULED`/`TIMED`) or `FINISHED` ones.
4. Post a header message, then one embed per match, one second apart to stay under
   Discord's webhook rate limit.

If the competition is not available (HTTP 403, e.g. off-season), the run exits without
posting.

## Setup

1. Get a free API token at [football-data.org](https://www.football-data.org/).
2. In Discord: **Server Settings → Integrations → Webhooks → New Webhook**, copy the URL.
3. In this repository: **Settings → Secrets and variables → Actions → New repository secret**
   - `FOOTBALL_DATA_TOKEN`
   - `DISCORD_WEBHOOK_URL`
4. **Actions → Post Daily World Cup Matches → Run workflow** to test.

Run locally:

```bash
pip install -r requirements.txt
export FOOTBALL_DATA_TOKEN=...  DISCORD_WEBHOOK_URL=...
DEBUG_DATE=2026-06-15 python post_matches.py   # optional: pretend it is another day
```

## What I learned

- **Matches showed up on the wrong day.** I first split days at Greek midnight, which cut
  the tournament's evening match days in two. Official schedules list matches by US
  Eastern date, so the "match day" is now anchored to `America/New_York` and Greek time is
  used only to display kickoff times.
- **One day is not one date in UTC.** A US Eastern day covers parts of two UTC dates, so the
  scripts over-fetch by a day on each side and filter afterwards.
- **Secrets stay out of the code.** The token and webhook URL come from GitHub Actions
  secrets as environment variables, and the scripts stop with a clear error if either is
  missing.

## Status

Built for the 2026 World Cup (June–July 2026). The tournament is over, so the scheduled
workflows can be disabled from the Actions tab.

## Notes

Development was assisted by [Claude](https://claude.ai/), Anthropic's AI model. Design
decisions, testing in a live Discord server and releases are by the maintainer.
