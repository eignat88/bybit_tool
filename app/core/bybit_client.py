from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)


class BybitAPIError(RuntimeError):
    """Raised when Bybit API returns an unrecoverable error."""


@dataclass(slots=True)
class BybitResponse:
    endpoint: str
    payload: dict[str, Any]


class BybitClient:
    """Bybit Unified Trading API client with retry and rate-limit handling."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.bybit.com",
        timeout: float = 15.0,
        max_retries: int = 5,
        retry_delay: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client = httpx.Client(timeout=self.timeout)

    def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> BybitResponse:
        params = params or {}
        url = f"{self.base_url}{endpoint}"
        for attempt in range(1, self.max_retries + 1):
            try:
                LOGGER.info("Bybit request", extra={"url": url, "params": params, "attempt": attempt})
                response = self._client.get(url, params=params)
                if response.status_code == 429:
                    wait = self.retry_delay * attempt
                    LOGGER.warning("Bybit rate-limited. Retrying in %.2fs", wait)
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                body = response.json()
                ret_code = body.get("retCode", -1)
                if ret_code == 0:
                    return BybitResponse(endpoint=endpoint, payload=body)

                if ret_code in {10006, 10016} and attempt < self.max_retries:
                    wait = self.retry_delay * attempt
                    LOGGER.warning("Bybit temporary error code %s, retry in %.2fs", ret_code, wait)
                    time.sleep(wait)
                    continue
                raise BybitAPIError(f"Bybit API error retCode={ret_code}: {body.get('retMsg')}")
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                if attempt >= self.max_retries:
                    LOGGER.exception("Bybit request failed after retries")
                    raise BybitAPIError(f"Request failed for {endpoint}") from exc
                wait = self.retry_delay * attempt
                LOGGER.warning("Bybit request failed (%s), retry in %.2fs", type(exc).__name__, wait)
                time.sleep(wait)

        raise BybitAPIError(f"Retries exhausted for endpoint={endpoint}")

    def get_symbols(self, market_type: str = "linear", cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"category": market_type}
        if cursor:
            params["cursor"] = cursor
        return self._request("/v5/market/instruments-info", params).payload

    def get_klines(
        self,
        symbol: str,
        interval: str,
        market_type: str = "linear",
        limit: int = 200,
        start_ms: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": market_type,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["start"] = start_ms
        return self._request("/v5/market/kline", params).payload

    def get_tickers(self, market_type: str = "linear", symbol: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"category": market_type}
        if symbol:
            params["symbol"] = symbol
        return self._request("/v5/market/tickers", params).payload

    def get_open_interest(self, symbol: str, interval: str = "5min", market_type: str = "linear") -> dict[str, Any]:
        return self._request(
            "/v5/market/open-interest",
            {"category": market_type, "symbol": symbol, "intervalTime": interval},
        ).payload

    def get_funding_rates(self, symbol: str, market_type: str = "linear", limit: int = 50) -> dict[str, Any]:
        return self._request(
            "/v5/market/funding/history",
            {"category": market_type, "symbol": symbol, "limit": limit},
        ).payload

    def get_orderbook(self, symbol: str, market_type: str = "linear", limit: int = 50) -> dict[str, Any]:
        return self._request(
            "/v5/market/orderbook",
            {"category": market_type, "symbol": symbol, "limit": limit},
        ).payload
