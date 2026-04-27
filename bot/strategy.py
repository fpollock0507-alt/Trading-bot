from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from .alpaca_client import AlpacaClient
from .logger import get_logger

ET = ZoneInfo("America/New_York")
log = get_logger(__name__)


@dataclass
class Signal:
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    stop_price: float
    target_price: float
    grade: str  # "A+", "A", "B"
    reason: str

    @property
    def risk_per_share(self) -> float:
        return abs(self.entry_price - self.stop_price)


def _opening_range(bars: pd.DataFrame, minutes: int, session_date) -> tuple[float, float, float] | None:
    """Return (high, low, volume) of the first `minutes` of the RTH session."""
    if bars.empty:
        return None
    bars = bars.copy()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_et = bars.tz_convert(ET)
    rth_open = datetime.combine(session_date, time(9, 30), tzinfo=ET)
    rth_end = datetime.combine(session_date, time(9, 30 + minutes), tzinfo=ET)
    window = bars_et[(bars_et.index >= rth_open) & (bars_et.index < rth_end)]
    if window.empty:
        return None
    return float(window["high"].max()), float(window["low"].min()), float(window["volume"].sum())


def _trend_direction(daily: pd.DataFrame, sma_days: int) -> str | None:
    if len(daily) < sma_days:
        return None
    sma = daily["close"].tail(sma_days).mean()
    last = float(daily["close"].iloc[-1])
    if last > sma * 1.005:
        return "long"
    if last < sma * 0.995:
        return "short"
    return None


def _grade_setup(range_pct: float, vol_ratio: float, trend_strength: float) -> str:
    """Dynamic grading for position sizing.

    A+ = clean range size, strong breakout volume, clear trend.
    A  = 2 of 3 strong.
    B  = baseline, meets filters but nothing exceptional.
    """
    score = 0
    if 0.5 <= range_pct <= 2.0:
        score += 1
    if vol_ratio >= 2.0:
        score += 1
    if trend_strength >= 0.02:  # >2% above/below SMA
        score += 1
    return {3: "A+", 2: "A", 1: "B", 0: "B"}[score]


def scan_for_signals(client: AlpacaClient, universe: list[str], cfg: dict) -> list[Signal]:
    s = cfg["strategy"]
    signals: list[Signal] = []
    now_et = datetime.now(ET)
    session_date = now_et.date()

    entry_start = time.fromisoformat(s["entry_window_start"])
    entry_end = time.fromisoformat(s["entry_window_end"])
    if not (entry_start <= now_et.time() <= entry_end):
        log.info(f"Outside entry window ({s['entry_window_start']}–{s['entry_window_end']}). Skipping scan.")
        return signals

    for sym in universe:
        try:
            sig = _evaluate(client, sym, session_date, s)
            if sig:
                signals.append(sig)
        except Exception as e:
            log.debug(f"Signal eval failed for {sym}: {e}")

    signals.sort(key=lambda x: {"A+": 0, "A": 1, "B": 2}[x.grade])
    return signals


def _evaluate(client: AlpacaClient, sym: str, session_date, s: dict) -> Signal | None:
    daily = client.daily_bars(sym, days=max(s["trend_sma_days"] + 5, 25))
    if daily.empty or len(daily) < s["trend_sma_days"]:
        return None

    trend = _trend_direction(daily, s["trend_sma_days"])
    if trend is None:
        return None

    minutes_since_open = 480  # pull enough for full session
    mbars = client.minute_bars(sym, lookback_minutes=minutes_since_open)
    if mbars.empty:
        return None

    or_result = _opening_range(mbars, s["opening_range_minutes"], session_date)
    if or_result is None:
        return None
    or_high, or_low, or_volume = or_result

    last = float(mbars["close"].iloc[-1])
    range_pct = (or_high - or_low) / or_low * 100
    if range_pct < s["min_range_pct"] or range_pct > s["max_range_pct"]:
        return None

    sma = daily["close"].tail(s["trend_sma_days"]).mean()
    trend_strength = abs(float(daily["close"].iloc[-1]) - sma) / sma

    avg_or_volume = daily["volume"].tail(20).mean() * (s["opening_range_minutes"] / 390)
    vol_ratio = or_volume / avg_or_volume if avg_or_volume > 0 else 0

    if vol_ratio < s["volume_confirm_multiplier"]:
        return None

    grade = _grade_setup(range_pct, vol_ratio, trend_strength)
    reason = f"range={range_pct:.2f}% vol={vol_ratio:.1f}x trend_str={trend_strength*100:.1f}%"

    if trend == "long" and last > or_high:
        risk = or_high - or_low
        return Signal(
            symbol=sym,
            side="long",
            entry_price=last,
            stop_price=or_low,
            target_price=last + risk * s["target_r_multiple"],
            grade=grade,
            reason=f"ORB long breakout ({reason})",
        )
    if trend == "short" and last < or_low:
        risk = or_high - or_low
        return Signal(
            symbol=sym,
            side="short",
            entry_price=last,
            stop_price=or_high,
            target_price=last - risk * s["target_r_multiple"],
            grade=grade,
            reason=f"ORB short breakdown ({reason})",
        )
    return None
