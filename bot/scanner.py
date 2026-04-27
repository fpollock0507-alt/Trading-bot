from __future__ import annotations

import pandas as pd

from .alpaca_client import AlpacaClient
from .logger import get_logger

log = get_logger(__name__)


def build_universe(client: AlpacaClient, cfg: dict) -> list[str]:
    u = cfg["universe"]
    base = list(u["watchlist"])
    movers = fetch_premarket_movers(client, u["premarket_movers_count"])
    combined = list(dict.fromkeys(base + movers))
    filtered = filter_tradable(client, combined, u)
    log.info(f"Universe: {len(filtered)} symbols — {filtered}")
    return filtered


def fetch_premarket_movers(client: AlpacaClient, n: int) -> list[str]:
    """Fetch top premarket gainers/losers by % change.

    Uses Alpaca's screener endpoint via the SDK where available;
    falls back to empty list if endpoint unavailable.
    """
    try:
        from alpaca.data.requests import MostActivesRequest
        from alpaca.data.historical.screener import ScreenerClient
        from .config import load_credentials

        creds = load_credentials()
        screener = ScreenerClient(creds.api_key, creds.api_secret)
        actives = screener.get_most_actives(MostActivesRequest(top=n * 2))
        return [a.symbol for a in actives.most_actives[:n]]
    except Exception as e:
        log.warning(f"Premarket movers unavailable, skipping: {e}")
        return []


def filter_tradable(client: AlpacaClient, symbols: list[str], u: dict) -> list[str]:
    out = []
    for sym in symbols:
        try:
            bars = client.daily_bars(sym, days=20)
            if bars.empty or len(bars) < 10:
                continue
            avg_vol = bars["volume"].mean()
            last_price = float(bars["close"].iloc[-1])
            if avg_vol < u["min_avg_volume"]:
                continue
            if last_price < u["min_price"] or last_price > u["max_price"]:
                continue
            asset = client.trading.get_asset(sym)
            if not asset.tradable or not asset.fractionable is not None:
                pass
            if not asset.tradable:
                continue
            out.append(sym)
        except Exception as e:
            log.debug(f"Skipping {sym}: {e}")
    return out
