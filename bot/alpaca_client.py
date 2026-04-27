from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from .config import Credentials

ET = ZoneInfo("America/New_York")


class AlpacaClient:
    def __init__(self, creds: Credentials):
        self.trading = TradingClient(creds.api_key, creds.api_secret, paper=creds.paper)
        self.data = StockHistoricalDataClient(creds.api_key, creds.api_secret)

    def account(self):
        return self.trading.get_account()

    def equity(self) -> float:
        return float(self.account().equity)

    def buying_power(self) -> float:
        return float(self.account().buying_power)

    def positions(self):
        return self.trading.get_all_positions()

    def position_symbols(self) -> set[str]:
        return {p.symbol for p in self.positions()}

    def open_orders(self):
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        return self.trading.get_orders(
            filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)
        )

    def close_all_positions(self):
        return self.trading.close_all_positions(cancel_orders=True)

    def cancel_all_orders(self):
        return self.trading.cancel_orders()

    def is_market_open(self) -> bool:
        return self.trading.get_clock().is_open

    def market_clock(self):
        return self.trading.get_clock()

    def daily_bars(self, symbol: str, days: int = 30) -> pd.DataFrame:
        end = datetime.now(ET) - timedelta(minutes=15)
        start = end - timedelta(days=days * 2 + 10)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
        )
        bars = self.data.get_stock_bars(req).df
        if bars.empty:
            return bars
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level="symbol")
        return bars.tail(days)

    def minute_bars(self, symbol: str, lookback_minutes: int = 60) -> pd.DataFrame:
        end = datetime.now(ET) - timedelta(minutes=16)
        start = end - timedelta(minutes=lookback_minutes + 30)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            start=start,
            end=end,
        )
        bars = self.data.get_stock_bars(req).df
        if bars.empty:
            return bars
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level="symbol")
        return bars

    def latest_quote(self, symbol: str):
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        return self.data.get_stock_latest_quote(req)[symbol]

    def submit_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: OrderSide,
        stop_loss_price: float,
        take_profit_price: float,
    ):
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
            order_class="bracket",
            stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2)),
            take_profit=TakeProfitRequest(limit_price=round(take_profit_price, 2)),
        )
        return self.trading.submit_order(req)
