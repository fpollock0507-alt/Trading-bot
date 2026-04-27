import csv
import subprocess
from datetime import date, datetime
from pathlib import Path

from .alpaca_client import AlpacaClient
from .logger import get_logger

log = get_logger(__name__)
ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)


def write_eod_report(client: AlpacaClient, starting_equity: float) -> Path:
    today = date.today().isoformat()
    trades_file = STATE_DIR / f"trades_{today}.csv"
    trades = []
    if trades_file.exists():
        with trades_file.open() as f:
            trades = list(csv.DictReader(f))

    account = client.account()
    equity = float(account.equity)
    cash = float(account.cash)
    pnl = equity - starting_equity
    pnl_pct = (pnl / starting_equity * 100) if starting_equity else 0.0

    # Closed-trade P&L from Alpaca's portfolio history
    try:
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        hist = client.trading.get_portfolio_history(
            GetPortfolioHistoryRequest(period="1D", timeframe="1H")
        )
        realized_curve = list(zip(hist.timestamp or [], hist.equity or []))
    except Exception:
        realized_curve = []

    lines = []
    lines.append(f"# End-of-Day Report — {today}")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Account")
    lines.append(f"- Starting equity: **${starting_equity:,.2f}**")
    lines.append(f"- Ending equity:   **${equity:,.2f}**")
    lines.append(f"- Day P&L:         **${pnl:+,.2f} ({pnl_pct:+.2f}%)**")
    lines.append(f"- Cash:            ${cash:,.2f}")
    lines.append("")
    lines.append(f"## Trades taken: {len(trades)}")
    if trades:
        lines.append("")
        lines.append("| Time | Symbol | Side | Grade | Qty | Entry | Stop | Target | Risk $ | Reason |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for t in trades:
            ts = t["timestamp"].split("T")[1][:8] if "T" in t["timestamp"] else t["timestamp"]
            lines.append(
                f"| {ts} | {t['symbol']} | {t['side']} | {t['grade']} | {t['qty']} | "
                f"{t['entry']} | {t['stop']} | {t['target']} | {t['risk_dollars']} | {t['reason']} |"
            )
    else:
        lines.append("No trades today — setup filters did not trigger.")

    lines.append("")
    lines.append("## Open positions at close")
    positions = client.positions()
    if positions:
        lines.append("")
        lines.append("| Symbol | Side | Qty | Avg Entry | Current | Unrealized P&L |")
        lines.append("|---|---|---|---|---|---|")
        for p in positions:
            lines.append(
                f"| {p.symbol} | {p.side} | {p.qty} | {p.avg_entry_price} | "
                f"{p.current_price} | {p.unrealized_pl} |"
            )
    else:
        lines.append("Flat at close.")

    if realized_curve:
        lines.append("")
        lines.append(f"## Equity curve (1H): {len(realized_curve)} points recorded")

    content = "\n".join(lines) + "\n"
    path = REPORT_DIR / f"{today}.md"
    path.write_text(content)
    log.info(f"Wrote EOD report: {path}")
    return path


def git_push_reports(branch: str = "main") -> bool:
    try:
        if not (ROOT / ".git").exists():
            log.warning("Not a git repo; run `git init` and add a remote first. See README.")
            return False

        subprocess.run(["git", "add", "reports/", "state/", "logs/"], cwd=ROOT, check=True)
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        )
        if not status.stdout.strip():
            log.info("No changes to commit.")
            return True
        msg = f"EOD report {date.today().isoformat()}"
        subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", branch], cwd=ROOT, check=True)
        log.info(f"Pushed EOD report to origin/{branch}.")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"Git push failed: {e}")
        return False
