#!/usr/bin/env bash
# Run one trading session. Invoked by cron at 9:30 ET on weekdays.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

python -m bot.main session
