#!/usr/bin/env bash
# Install cron entries for market open (9:30 ET) and EOD (16:05 ET).
# macOS cron runs in local TZ, so we schedule in America/New_York via the TZ env var.
# NOTE: DST-handled automatically by using TZ=America/New_York in the cron env.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SESSION_SCRIPT="$PROJECT_DIR/scripts/run_session.sh"
EOD_SCRIPT="$PROJECT_DIR/scripts/run_eod.sh"

chmod +x "$SESSION_SCRIPT" "$EOD_SCRIPT"

TMP="$(mktemp)"
# Preserve any existing crontab entries that aren't ours.
crontab -l 2>/dev/null | grep -v "# trading-bot:" > "$TMP" || true

cat >> "$TMP" <<EOF
# trading-bot: market-open session (9:30 ET Mon–Fri)
CRON_TZ=America/New_York
30 9 * * 1-5 $SESSION_SCRIPT >> $PROJECT_DIR/logs/cron_session.log 2>&1 # trading-bot:
# trading-bot: EOD report + git push (16:05 ET Mon–Fri)
5 16 * * 1-5 $EOD_SCRIPT >> $PROJECT_DIR/logs/cron_eod.log 2>&1 # trading-bot:
EOF

crontab "$TMP"
rm "$TMP"

echo "Installed cron jobs. View with: crontab -l"
echo ""
echo "IMPORTANT: On macOS, grant cron Full Disk Access:"
echo "  System Settings → Privacy & Security → Full Disk Access → add /usr/sbin/cron"
echo "Otherwise cron jobs may silently fail to read .env or write logs."
