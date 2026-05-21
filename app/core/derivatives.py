from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from app.config.settings import settings
from app.core.bybit_client import BybitClient


@dataclass(slots=True)
class DerivativesSignals:
    funding_rate: float | None
    funding_bias: str
    open_interest: float | None
    open_interest_change_pct: float | None
    bid_ask_imbalance: float | None
    orderbook_bias: str


class DerivativesAnalyzer:
    def __init__(self, client: BybitClient, market_type: str = settings.default_market_type) -> None:
        self.client = client
        self.market_type = market_type

    def _extract_funding(self, funding_payload: dict[str, Any]) -> tuple[float | None, str]:
        rows = funding_payload.get("result", {}).get("list", [])
        if not rows:
            return None, "neutral"
        values = [float(x.get("fundingRate", 0.0)) for x in rows]
        last = values[0]
        avg = mean(values)
        if last > max(avg * 1.25, 0.0):
            return last, "long_crowded"
        if last < min(avg * 1.25, 0.0):
            return last, "short_crowded"
        return last, "neutral"

    def _extract_open_interest(self, oi_payload: dict[str, Any]) -> tuple[float | None, float | None]:
        rows = oi_payload.get("result", {}).get("list", [])
        if len(rows) < 2:
            return None, None
        latest = float(rows[0].get("openInterest", 0.0))
        prev = float(rows[-1].get("openInterest", 0.0))
        if prev == 0:
            return latest, None
        change_pct = ((latest / prev) - 1.0) * 100
        return latest, round(change_pct, 3)

    def _extract_orderbook(self, orderbook_payload: dict[str, Any]) -> tuple[float | None, str]:
        result = orderbook_payload.get("result", {})
        bids = result.get("b", [])
        asks = result.get("a", [])
        if not bids or not asks:
            return None, "neutral"

        bid_sum = sum(float(price) * float(size) for price, size in bids)
        ask_sum = sum(float(price) * float(size) for price, size in asks)
        total = bid_sum + ask_sum
        if total == 0:
            return 0.0, "neutral"

        imbalance = (bid_sum - ask_sum) / total
        if imbalance > 0.1:
            bias = "bid_dominant"
        elif imbalance < -0.1:
            bias = "ask_dominant"
        else:
            bias = "balanced"
        return round(imbalance, 4), bias

    def analyze(self, symbol: str) -> DerivativesSignals:
        funding = self.client.get_funding_rates(symbol=symbol, market_type=self.market_type, limit=30)
        oi = self.client.get_open_interest(symbol=symbol, market_type=self.market_type, interval="5min")
        ob = self.client.get_orderbook(symbol=symbol, market_type=self.market_type, limit=50)

        funding_rate, funding_bias = self._extract_funding(funding)
        open_interest, open_interest_change_pct = self._extract_open_interest(oi)
        bid_ask_imbalance, orderbook_bias = self._extract_orderbook(ob)

        return DerivativesSignals(
            funding_rate=funding_rate,
            funding_bias=funding_bias,
            open_interest=open_interest,
            open_interest_change_pct=open_interest_change_pct,
            bid_ask_imbalance=bid_ask_imbalance,
            orderbook_bias=orderbook_bias,
        )
