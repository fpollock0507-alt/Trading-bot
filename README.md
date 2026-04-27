# Trading Routine — Alpaca Paper Trading Bot

An automated day-trading bot that runs on your Mac during US market hours via cron.
Scans a watchlist + premarket movers, trades an **Opening Range Breakout (ORB)** strategy
with a daily-trend filter, uses **dynamic position sizing** (A+ setups risk more, B setups
risk less), and writes an end-of-day report that is committed and pushed to GitHub.

**Paper trading only** until you explicitly flip `ALPACA_PAPER=false` in `.env`.

---

## Important reality checks

- No strategy wins 90%+ of trades. This bot is built for **positive expectancy**:
  realistic win rate is 45–55%, but winners are ~2× losers.
- Realistic monthly account growth if the strategy works: **2–5%**. Not per day.
- The bot halts for the day on a **3% account drawdown** or a **5% profit target** —
  hardcoded guardrails that prevent revenge trading and overtrading.
- Paper-trade for **at least 4 weeks** before considering live money. Use the EOD
  reports to judge whether the strategy is actually working on current market
  conditions.

---

## What it does

1. **Session loop** (9:30–15:55 ET): scans universe every 30s for ORB setups.
2. **Entry**: breakout of the first 15-min range, only in the direction of the daily trend
   (price vs. 20-day SMA), confirmed by ≥1.5× average volume.
3. **Risk**: bracket orders with stop at the opposite side of the range, target at 2R.
4. **Sizing**:
   - **A+ setup** (clean range + strong volume + strong trend) → 2% account risk
   - **A setup** → 1.5%
   - **B setup** → 1%
5. **Kill switches**: max 3 trades/day, max 3 concurrent positions, –3% daily loss cap,
   +5% daily profit lock.
6. **Force flat** at 15:55 ET so nothing carries overnight.
7. **EOD report** at 16:05 ET: markdown summary of trades, P&L, equity curve —
   committed and pushed to GitHub.

---

## Setup

### 1. Install dependencies

```bash
cd "/Users/Finpollock/Trading routine"
./scripts/install.sh
```

This creates `.venv/`, installs requirements, and copies `.env.example` → `.env`.

### 2. Add your Alpaca paper keys

Get them from https://app.alpaca.markets/paper/dashboard/overview, then edit `.env`:

```
ALPACA_API_KEY=PK...
ALPACA_API_SECRET=...
ALPACA_PAPER=true
```

### 3. Smoke test

```bash
source .venv/bin/activate
python -m bot.main status
```

You should see your paper account number, equity, and buying power.

### 4. Create a GitHub repo and connect it

The bot pushes EOD reports to GitHub. Create an empty repo on GitHub, then:

```bash
cd "/Users/Finpollock/Trading routine"
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

Make sure git is authenticated (either via SSH key or `gh auth login`) so the cron
job can push without prompting.

### 5. Install cron jobs

```bash
./scripts/setup_cron.sh
```

This installs two entries:
- 9:30 ET Mon–Fri: starts the session loop
- 16:05 ET Mon–Fri: writes the EOD report and git-pushes

**macOS gotcha**: cron needs Full Disk Access to read `.env` and write logs.
System Settings → Privacy & Security → Full Disk Access → `+` → `/usr/sbin/cron`.

Verify installation:
```bash
crontab -l
```

---

## Manual commands

```bash
source .venv/bin/activate

# Check account status
python -m bot.main status

# Run the session loop immediately (only does anything during market hours)
python -m bot.main session

# Force-write an EOD report now
python -m bot.main eod

# EMERGENCY: close all positions + cancel all orders
python -m bot.main flatten
```

---

## Tuning the strategy

All tunable parameters live in `config.yaml`. Most useful knobs:

- `strategy.opening_range_minutes` — shorter = more signals, noisier; longer = fewer, cleaner
- `strategy.volume_confirm_multiplier` — raise to require stronger breakouts
- `strategy.target_r_multiple` — 2.0 means target is 2× the stop distance. Higher = fewer winners but bigger R
- `risk.base_risk_pct` / `risk.max_risk_pct` — the dynamic sizing band
- `risk.daily_loss_cap_pct` — hard stop for the day
- `universe.watchlist` — add/remove tickers you want to watch

---

## How to tell if it's working

After ~20 trading days of paper, look at:

1. **Win rate**: want 45%+.
2. **Average win / average loss ratio (R)**: want 1.5+ (bigger winners than losers).
3. **Expectancy**: `(win_rate × avg_win) − (loss_rate × avg_loss)`. Must be positive.
4. **Max drawdown**: how bad was the worst multi-day loss?

If expectancy is positive and drawdown is tolerable (<10% peak-to-trough), the strategy
is worth considering for real money — **in small size**. If not, tune params or
change strategy. Do not increase size to "make it back."

---

## Files

```
bot/
├── main.py          # Entry point (session / eod / status / flatten)
├── config.py        # Loads .env and config.yaml
├── alpaca_client.py # Alpaca SDK wrapper
├── scanner.py       # Builds the tradable universe
├── strategy.py      # ORB + trend filter + setup grading
├── risk.py          # Position sizing + kill switches
├── executor.py      # Bracket order placement
├── reporter.py      # EOD markdown report + git push
└── logger.py        # Logging setup

scripts/
├── install.sh       # One-shot setup
├── run_session.sh   # Cron entry: trading session
├── run_eod.sh       # Cron entry: EOD report
└── setup_cron.sh    # Installs the two cron jobs

config.yaml          # Strategy + risk + universe parameters
.env.example         # API key template (copy to .env)
state/               # Daily trade log, starting equity
logs/                # Log files
reports/             # EOD markdown reports (committed to git)
```

---

## Going live (later)

When your Alpaca individual account is verified:

1. Get **live** API keys (different from paper keys).
2. Update `.env`: replace keys, set `ALPACA_PAPER=false`.
3. **Start with small size.** Consider setting `risk.base_risk_pct: 0.25` and
   `risk.max_risk_pct: 0.5` for the first month of live trading. You can always
   scale up. You can't un-blow an account.

---

## Troubleshooting

- **Cron not firing**: check `/usr/sbin/cron` has Full Disk Access (see Setup §5).
- **`.env` not loading**: the bot looks for it next to `config.yaml`. Make sure
  the cron script `cd`s into the project dir (it does).
- **Git push fails from cron**: cron doesn't have your shell's SSH agent. Easiest
  fix: use HTTPS + a PAT in the remote URL, or use `gh auth login` with a token
  stored in the keychain.
- **Alpaca rate limits**: the bot caches data and scans at 30s intervals. If you
  tighten `scan_interval_seconds`, watch for 429s in the logs.
