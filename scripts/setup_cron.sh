#!/usr/bin/env bash
# Install cron entries for market open (9:30 ET) and EOD (16:05 ET).
# macOS cron runs in local TZ, so we schedule in America/New_York via the TZ env var.
# NOTE: DST-handled automatically by using TZ=America/New_York in the cron env.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SESSION_SCRIPT="$PROJECT_DIR/scripts/run_session.sh"
EOD_SCRIPT="$PROJECT_DIR/scripts/run_eod.sh"

chmod +x "$SESSION_SCRIPT" "$EOD_SCRIPT"

# Escape spaces in paths so cron parses them as a single argument.
PROJECT_DIR_ESC="${PROJECT_DIR// /\\ }"
SESSION_SCRIPT_ESC="${SESSION_SCRIPT// /\\ }"
EOD_SCRIPT_ESC="${EOD_SCRIPT// /\\ }"

TMP="$(mktemp)"
# Preserve any existing crontab entries that aren't ours.
crontab -l 2>/dev/null | grep -v "# trading-bot:" > "$TMP" || true

cat >> "$TMP" <<EOF
# trading-bot: market-open session
# macOS BSD cron uses LOCAL time and ignores CRON_TZ.
# Schedule below is in Australia/Sydney AEST (UTC+10) for US EDT (UTC-4) market.
# US 9:30 ET = 23:30 AEST same day  → cron Mon-Fri at 23:30
# US 16:05 ET = 06:05 AEST next day → cron Tue-Sat at 06:05
# Update twice a year for DST: AU DST ~Oct 1st Sun, US DST ends ~Nov 1st Sun.
30 23 * * 1-5 $SESSION_SCRIPT_ESC >> $PROJECT_DIR_ESC/logs/cron_session.log 2>&1 # trading-bot:
5 6 * * 2-6 $EOD_SCRIPT_ESC >> $PROJECT_DIR_ESC/logs/cron_eod.log 2>&1 # trading-bot:
EOF

crontab "$TMP"
rm "$TMP"

echo "Installed cron jobs. View with: crontab -l"
echo ""
echo "IMPORTANT: On macOS, grant cron Full Disk Access:"
echo "  System Settings → Privacy & Security → Full Disk Access → add /usr/sbin/cron"
echo "Otherwise cron jobs may silently fail to read .env or write logs."
