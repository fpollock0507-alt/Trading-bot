#!/usr/bin/env bash
# Generate EOD report and push to GitHub. Invoked by cron at 16:05 ET weekdays.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

python -m bot.main eod
