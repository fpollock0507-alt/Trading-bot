from __future__ import annotations

from alpaca.trading.enums import OrderSide

from .alpaca_client import AlpacaClient
from .logger import get_logger
from .risk import Sizing, record_trade
from .strategy import Signal

log = get_logger(__name__)


def execute_signal(client: AlpacaClient, signal: Signal, sizing: Sizing) -> str | None:
    side = OrderSide.BUY if signal.side == "long" else OrderSide.SELL
    try:
        order = client.submit_bracket_order(
            symbol=signal.symbol,
            qty=sizing.qty,
            side=side,
            stop_loss_price=signal.stop_price,
            take_profit_price=signal.target_price,
        )
        oid = str(order.id)
        log.info(
            f"SUBMITTED {signal.side.upper()} {sizing.qty} {signal.symbol} "
            f"@ ~{signal.entry_price:.2f} stop={signal.stop_price:.2f} "
            f"tgt={signal.target_price:.2f} grade={signal.grade} risk=${sizing.risk_dollars:.2f}"
        )
        record_trade(signal, sizing, oid)
        return oid
    except Exception as e:
        log.error(f"Order submission failed for {signal.symbol}: {e}")
        return None


def flatten_all(client: AlpacaClient):
    log.info("Flattening all positions and cancelling open orders.")
    try:
        client.cancel_all_orders()
        client.close_all_positions()
    except Exception as e:
        log.error(f"Flatten failed: {e}")
