from __future__ import annotations

import json
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.bybit_client import BybitClient
from app.core.derivatives import DerivativesAnalyzer
from app.core.market_structure import build_market_structure, parse_timeframes_csv
from app.db.models import AnalysisReport, Candle


MIN_CANDLES_BY_INTERVAL: dict[str, int] = {
    "D": 90,
    "240": 120,
    "H4": 120,
    "60": 120,
    "H1": 120,
    "15": 120,
}


def _required_candles(interval: str) -> int:
    return MIN_CANDLES_BY_INTERVAL.get(interval.upper(), 120)


def _load_candles(db: Session, symbol: str, market_type: str, interval: str, limit: int = 220) -> list[dict[str, float]]:
    stmt = (
        select(Candle)
        .where(Candle.symbol == symbol, Candle.market_type == market_type, Candle.interval == interval)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars())
    rows.reverse()
    return [{"close": c.close, "high": c.high, "low": c.low} for c in rows]


def _corr(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 3:
        return None
    ma, mb = mean(a), mean(b)
    da = [x - ma for x in a]
    db = [x - mb for x in b]
    cov = sum(x * y for x, y in zip(da, db, strict=False))
    va = sum(x * x for x in da)
    vb = sum(y * y for y in db)
    if va == 0 or vb == 0:
        return None
    return round(cov / (va * vb) ** 0.5, 4)


def _returns(candles: list[dict[str, float]], window: int = 80) -> list[float]:
    closes = [float(c["close"]) for c in candles][-window:]
    out: list[float] = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        if prev != 0:
            out.append(closes[idx] / prev - 1.0)
    return out


def build_analysis_report(
    *,
    db: Session,
    client: BybitClient,
    symbol: str,
    intervals: str,
    market_type: str = settings.default_market_type,
) -> tuple[AnalysisReport, dict[str, Any], str]:
    normalized_intervals = parse_timeframes_csv(intervals)
    derivatives = DerivativesAnalyzer(client=client, market_type=market_type).analyze(symbol)

    market_structure: dict[str, Any] = {}
    correlation: dict[str, Any] = {}

    for interval in normalized_intervals:
        candles = _load_candles(db=db, symbol=symbol, market_type=market_type, interval=interval)
        required = _required_candles(interval)
        if len(candles) < required:
            raise ValueError(
                f"Недостаточно свечей для symbol={symbol} interval={interval}: "
                f"получено={len(candles)}, требуется>={required}"
            )

        snapshot = build_market_structure(timeframe=interval, candles=candles)
        market_structure[interval] = {
            "trend_regime": snapshot.trend_regime,
            "swing_state": snapshot.swing_state,
            "volatility_state": snapshot.volatility_state,
            "latest_close": snapshot.latest_close,
            "returns_volatility_pct": snapshot.returns_volatility_pct,
        }

        base_returns = _returns(candles)
        btc_returns = _returns(_load_candles(db=db, symbol="BTCUSDT", market_type=market_type, interval=interval))
        eth_returns = _returns(_load_candles(db=db, symbol="ETHUSDT", market_type=market_type, interval=interval))
        min_len_btc = min(len(base_returns), len(btc_returns))
        min_len_eth = min(len(base_returns), len(eth_returns))
        correlation[interval] = {
            "btc": _corr(base_returns[-min_len_btc:], btc_returns[-min_len_btc:]) if min_len_btc >= 3 else None,
            "eth": _corr(base_returns[-min_len_eth:], eth_returns[-min_len_eth:]) if min_len_eth >= 3 else None,
        }

    payload: dict[str, Any] = {
        "symbol": symbol,
        "market_type": market_type,
        "timeframes": normalized_intervals,
        "generated_at": datetime.now(UTC).isoformat(),
        "market_structure": market_structure,
        "derivatives": {
            "funding_rate": derivatives.funding_rate,
            "funding_bias": derivatives.funding_bias,
            "open_interest": derivatives.open_interest,
            "open_interest_change_pct": derivatives.open_interest_change_pct,
            "bid_ask_imbalance": derivatives.bid_ask_imbalance,
            "orderbook_bias": derivatives.orderbook_bias,
        },
        "correlation": correlation,
    }

    report = AnalysisReport(symbol=symbol, timeframe_set=",".join(normalized_intervals), report_json=json.dumps(payload))
    db.add(report)
    db.commit()
    db.refresh(report)

    md = render_markdown_summary(report_id=report.id, payload=payload)
    return report, payload, md


def render_markdown_summary(*, report_id: int, payload: dict[str, Any]) -> str:
    lines = [
        f"# Analysis Report #{report_id}",
        f"- Symbol: **{payload['symbol']}** ({payload['market_type']})",
        f"- Timeframes: {', '.join(payload['timeframes'])}",
        "",
        "## Market Structure",
    ]
    for tf, data in payload["market_structure"].items():
        lines.append(
            f"- **{tf}**: trend={data['trend_regime']}, swings={data['swing_state']}, vol={data['volatility_state']}, close={data['latest_close']:.6f}"
        )

    d = payload["derivatives"]
    lines.extend(
        [
            "",
            "## Derivatives",
            f"- Funding: {d['funding_rate']} ({d['funding_bias']})",
            f"- Open interest: {d['open_interest']} ({d['open_interest_change_pct']}%)",
            f"- Orderbook imbalance: {d['bid_ask_imbalance']} ({d['orderbook_bias']})",
            "",
            "## Correlation",
        ]
    )
    for tf, data in payload["correlation"].items():
        lines.append(f"- **{tf}**: BTC={data['btc']}, ETH={data['eth']}")
    return "\n".join(lines)


def build_json_report(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
