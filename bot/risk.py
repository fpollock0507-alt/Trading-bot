from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .alpaca_client import AlpacaClient
from .logger import get_logger
from .strategy import Signal

log = get_logger(__name__)
ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)


@dataclass
class Sizing:
    qty: int
    risk_dollars: float
    risk_pct: float


def grade_to_risk_pct(grade: str, r: dict) -> float:
    if grade == "A+":
        return r["max_risk_pct"]
    if grade == "A":
        return (r["max_risk_pct"] + r["base_risk_pct"]) / 2
    return r["base_risk_pct"]


def size_position(signal: Signal, account_equity: float, r: dict) -> Sizing | None:
    risk_pct = grade_to_risk_pct(signal.grade, r)
    risk_dollars = account_equity * (risk_pct / 100)
    per_share_risk = signal.risk_per_share
    if per_share_risk <= 0:
        return None
    qty = int(risk_dollars // per_share_risk)
    if qty <= 0:
        return None
    return Sizing(qty=qty, risk_dollars=qty * per_share_risk, risk_pct=risk_pct)


def can_trade_today(client: AlpacaClient, r: dict, starting_equity: float) -> tuple[bool, str]:
    """Check kill-switches: daily loss cap, profit target, max trades."""
    current_equity = client.equity()
    pnl_pct = (current_equity - starting_equity) / starting_equity * 100

    if pnl_pct <= -r["daily_loss_cap_pct"]:
        return False, f"Daily loss cap hit ({pnl_pct:.2f}%). Trading halted."
    if pnl_pct >= r["daily_profit_target_pct"]:
        return False, f"Daily profit target hit ({pnl_pct:.2f}%). Locking in gains."

    trades_today = _count_trades_today()
    if trades_today >= r["max_trades_per_day"]:
        return False, f"Max trades/day reached ({trades_today}/{r['max_trades_per_day']})."

    open_positions = len(client.positions())
    if open_positions >= r["max_concurrent_positions"]:
        return False, f"Max concurrent positions ({open_positions}) reached."

    return True, f"OK ({trades_today} trades taken, PnL {pnl_pct:+.2f}%)"


def record_trade(signal: Signal, sizing: Sizing, order_id: str):
    path = STATE_DIR / f"trades_{date.today().isoformat()}.csv"
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow([
                "timestamp", "symbol", "side", "grade", "qty",
                "entry", "stop", "target", "risk_pct", "risk_dollars",
                "reason", "order_id",
            ])
        w.writerow([
            datetime.now().isoformat(), signal.symbol, signal.side, signal.grade,
            sizing.qty, signal.entry_price, signal.stop_price, signal.target_price,
            f"{sizing.risk_pct:.2f}", f"{sizing.risk_dollars:.2f}",
            signal.reason, order_id,
        ])


def _count_trades_today() -> int:
    path = STATE_DIR / f"trades_{date.today().isoformat()}.csv"
    if not path.exists():
        return 0
    with path.open() as f:
        return max(0, sum(1 for _ in f) - 1)


def get_starting_equity(client: AlpacaClient) -> float:
    """Cache the day's starting equity so drawdown is measured from open."""
    path = STATE_DIR / f"equity_{date.today().isoformat()}.txt"
    if path.exists():
        return float(path.read_text().strip())
    eq = client.equity()
    path.write_text(str(eq))
    return eq
