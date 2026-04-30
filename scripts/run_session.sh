#!/usr/bin/env bash
# Run one trading session. Invoked by cron at 23:30 AEST on weekdays.
# Wrapped in `caffeinate -i` so the Mac can't idle-sleep the bot mid-session
# (we hit this — Mac slept at ~10:53 ET, force-flat at 15:55 ET never ran,
# carrying GOOGL position overnight).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# -i: prevent system idle sleep
# -m: prevent disk idle sleep
# -s: prevent system sleep when on AC power
exec caffeinate -ims python -m bot.main session
