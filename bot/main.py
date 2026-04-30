"""Main orchestrator. Entry points:

    python -m bot.main session   # run during market hours, scan + trade
    python -m bot.main eod       # run after close, write report + git push
    python -m bot.main status    # one-shot: print account status
    python -m bot.main flatten   # emergency: close everything

Intended to be driven by cron. See scripts/setup_cron.sh.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from .alpaca_client import AlpacaClient
from .config import load_config, load_credentials
from .executor import execute_signal, flatten_all
from .logger import get_logger
from .reporter import git_push_reports, write_eod_report
from .risk import (
    can_trade_today,
    get_starting_equity,
    size_position,
)
from .scanner import build_universe
from .strategy import scan_for_signals

ET = ZoneInfo("America/New_York")
log = get_logger("main")


def _client() -> AlpacaClient:
    return AlpacaClient(load_credentials())


def run_session():
    cfg = load_config()
    client = _client()

    if not client.is_market_open():
        log.info("Market closed. Exiting session loop.")
        return

    starting_equity = get_starting_equity(client)
    log.info(f"Session start. Starting equity: ${starting_equity:,.2f}")

    # Flatten any stale positions carried over from a previous session.
    # Without this, a position that didn't close (e.g. Mac slept past
    # force-flat time) eats today's buying power.
    stale = client.positions()
    if stale:
        log.warning(
            f"Carryover detected: {len(stale)} stale position(s). Flattening before session begins."
        )
        for p in stale:
            log.warning(f"  - {p.symbol} {p.side} {p.qty} @ {p.avg_entry_price} uPnL {p.unrealized_pl}")
        flatten_all(client)
        time.sleep(5)  # let close orders settle

    universe = build_universe(client, cfg)

    force_flat = dtime.fromisoformat(cfg["strategy"]["force_flat_time"])
    entry_end = dtime.fromisoformat(cfg["strategy"]["entry_window_end"])
    scan_interval = cfg["execution"]["scan_interval_seconds"]
    already_taken: set[str] = set()

    while True:
        now = datetime.now(ET).time()

        if now >= force_flat:
            log.info("Force-flat time reached. Closing positions.")
            flatten_all(client)
            break

        if not client.is_market_open():
            log.info("Market closed mid-session. Exiting.")
            break

        ok, reason = can_trade_today(client, cfg["risk"], starting_equity)
        if not ok:
            log.info(f"Trading halted: {reason}")
            if "loss cap" in reason or "profit target" in reason:
                flatten_all(client)
                break
            # max trades or positions: stop scanning, just wait out the session
            time.sleep(scan_interval)
            continue

        if now <= entry_end:
            signals = scan_for_signals(client, universe, cfg)
            held = client.position_symbols()
            for sig in signals:
                if sig.symbol in held or sig.symbol in already_taken:
                    continue
                ok, reason = can_trade_today(client, cfg["risk"], starting_equity)
                if not ok:
                    log.info(f"Risk gate closed mid-loop: {reason}")
                    break

                # Fetch fresh equity + buying power for accurate sizing
                equity = client.equity()
                bp = client.buying_power()
                sizing = size_position(sig, equity, bp, cfg["risk"])
                if sizing is None:
                    log.info(f"Skipping {sig.symbol}: position size would be 0 (insufficient buying power or risk).")
                    continue

                # Pre-flight check: confirm the order will fit in buying power.
                # Avoids spamming Alpaca with rejected orders (saw 80+ in one session).
                cost_basis = sizing.qty * sig.entry_price
                if cost_basis > bp * 0.98:  # 2% safety margin for slippage
                    log.info(
                        f"Skipping {sig.symbol}: cost ${cost_basis:,.0f} exceeds available BP ${bp:,.0f}."
                    )
                    continue

                oid = execute_signal(client, sig, sizing)
                if oid:
                    already_taken.add(sig.symbol)

        time.sleep(scan_interval)

    log.info("Session loop ended.")


def run_eod():
    cfg = load_config()
    client = _client()
    starting_equity = get_starting_equity(client)
    write_eod_report(client, starting_equity)
    if cfg["reporting"]["git_push_on_eod"]:
        git_push_reports(cfg["reporting"]["git_branch"])


def print_status():
    client = _client()
    acct = client.account()
    print(f"Account:          {acct.account_number}")
    print(f"Status:           {acct.status}")
    print(f"Equity:           ${float(acct.equity):,.2f}")
    print(f"Cash:             ${float(acct.cash):,.2f}")
    print(f"Buying power:     ${float(acct.buying_power):,.2f}")
    print(f"Market open:      {client.is_market_open()}")
    positions = client.positions()
    print(f"Open positions:   {len(positions)}")
    for p in positions:
        print(f"  {p.symbol:6} {p.side:5} {p.qty:>6} @ {p.avg_entry_price}  uPnL {p.unrealized_pl}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "session":
        run_session()
    elif cmd == "eod":
        run_eod()
    elif cmd == "status":
        print_status()
    elif cmd == "flatten":
        flatten_all(_client())
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
