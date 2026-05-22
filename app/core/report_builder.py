from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.bybit_client import BybitClient
from app.core.derivatives import DerivativesAnalyzer
from app.core.indicators import calculate_indicators
from app.core.market_structure import build_market_structure, parse_timeframes_csv
from app.db.models import AnalysisReport, Candle, IndicatorValue, Level, ScanResult, ScanRun


MIN_CANDLES_BY_INTERVAL: dict[str, int] = {
    "D": 90,
    "240": 120,
    "H4": 120,
    "60": 120,
    "H1": 120,
    "15": 120,
}

SNAPSHOT_INDICATORS = ("atr_pct", "rsi", "adx", "vwap_deviation_pct", "bb_width_pct")


def _required_candles(interval: str) -> int:
    return MIN_CANDLES_BY_INTERVAL.get(interval.upper(), 120)


def _load_candle_rows(db: Session, symbol: str, market_type: str, interval: str, limit: int = 220) -> list[Candle]:
    stmt = (
        select(Candle)
        .where(Candle.symbol == symbol, Candle.market_type == market_type, Candle.interval == interval)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars())
    rows.reverse()
    return rows


def _load_candles(db: Session, symbol: str, market_type: str, interval: str, limit: int = 220) -> list[dict[str, float]]:
    rows = _load_candle_rows(db=db, symbol=symbol, market_type=market_type, interval=interval, limit=limit)
    return [{"close": c.close, "high": c.high, "low": c.low} for c in rows]


def _round(v: float | None) -> float | None:
    return None if v is None else round(float(v), 4)


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


def build_indicator_snapshot(*, db: Session, symbol: str, market_type: str, intervals: list[str]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for interval in intervals:
        candles = _load_candle_rows(db=db, symbol=symbol, market_type=market_type, interval=interval, limit=300)
        if not candles:
            snapshot[interval] = {"status": "insufficient_history", "source": "runtime"}
            continue

        latest_open_time = candles[-1].open_time
        iv_rows = list(
            db.execute(
                select(IndicatorValue).where(
                    IndicatorValue.symbol == symbol,
                    IndicatorValue.interval == interval,
                    IndicatorValue.open_time == latest_open_time,
                    IndicatorValue.indicator_name.in_(SNAPSHOT_INDICATORS),
                )
            ).scalars()
        )
        iv_map = {r.indicator_name: r for r in iv_rows}
        if all(name in iv_map for name in SNAPSHOT_INDICATORS):
            one = iv_rows[0]
            snapshot[interval] = {
                "open_time": latest_open_time.isoformat(),
                **{name: _round(iv_map[name].value) for name in SNAPSHOT_INDICATORS},
                "calc_version": one.calc_version,
                "source": "indicator_values",
                "status": "ok",
            }
            continue

        if len(candles) < 30:
            snapshot[interval] = {
                "open_time": latest_open_time.isoformat(),
                "source": "runtime",
                "status": "insufficient_history",
            }
            continue

        calc = calculate_indicators(
            highs=[c.high for c in candles],
            lows=[c.low for c in candles],
            closes=[c.close for c in candles],
            volumes=[c.volume for c in candles],
        )
        snapshot[interval] = {
            "open_time": latest_open_time.isoformat(),
            "atr_pct": _round(calc.atr_pct),
            "rsi": _round(calc.rsi),
            "adx": _round(calc.adx),
            "vwap_deviation_pct": _round(calc.vwap_deviation_pct),
            "bb_width_pct": _round(calc.bb_width_pct),
            "calc_version": "v1",
            "source": "runtime",
            "status": "ok",
        }
    return snapshot


def build_levels_summary(*, db: Session, symbol: str, market_type: str, intervals: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for interval in intervals:
        levels = list(
            db.execute(
                select(Level).where(Level.symbol == symbol, Level.market_type == market_type, Level.interval == interval)
            ).scalars()
        )
        if not levels:
            out[interval] = {"total": 0, "support_count": 0, "resistance_count": 0, "status": "no_levels"}
            continue
        supports = [l for l in levels if l.level_type.lower() == "support"]
        resistances = [l for l in levels if l.level_type.lower() == "resistance"]
        by_source = Counter(l.source_type for l in levels)
        strongest_support = max(supports, key=lambda l: l.strength_score) if supports else None
        strongest_resistance = max(resistances, key=lambda l: l.strength_score) if resistances else None
        out[interval] = {
            "total": len(levels),
            "support_count": len(supports),
            "resistance_count": len(resistances),
            "by_source_type": dict(by_source),
            "strongest_support": (
                {
                    "level_price": _round(strongest_support.level_price),
                    "source_type": strongest_support.source_type,
                    "strength_score": _round(strongest_support.strength_score),
                    "description": strongest_support.description,
                }
                if strongest_support
                else None
            ),
            "strongest_resistance": (
                {
                    "level_price": _round(strongest_resistance.level_price),
                    "source_type": strongest_resistance.source_type,
                    "strength_score": _round(strongest_resistance.strength_score),
                    "description": strongest_resistance.description,
                }
                if strongest_resistance
                else None
            ),
            "has_bos": any(l.source_type.lower() == "bos" for l in levels),
            "has_choch": any(l.source_type.lower() == "choch" for l in levels),
            "has_fvg": any(l.source_type.lower() == "fvg" for l in levels),
            "status": "ok",
        }
    return out


def find_nearest_levels(*, db: Session, symbol: str, market_type: str, intervals: list[str]) -> dict[str, Any]:
    primary_interval = intervals[-1]
    primary_candles = _load_candle_rows(db=db, symbol=symbol, market_type=market_type, interval=primary_interval, limit=1)
    latest_row = primary_candles[-1] if primary_candles else None

    if latest_row is None:
        for interval in intervals:
            fallback = _load_candle_rows(db=db, symbol=symbol, market_type=market_type, interval=interval, limit=1)
            if fallback:
                latest_row = fallback[-1]
                break

    if latest_row is None:
        return {
            "primary_interval": primary_interval,
            "latest_close": None,
            "nearest_support": None,
            "nearest_resistance": None,
            "status": "no_price",
        }

    latest_close = float(latest_row.close)
    levels = list(
        db.execute(
            select(Level).where(Level.symbol == symbol, Level.market_type == market_type, Level.interval == primary_interval)
        ).scalars()
    )
    if not levels:
        return {
            "primary_interval": primary_interval,
            "latest_close": _round(latest_close),
            "nearest_support": None,
            "nearest_resistance": None,
            "status": "no_levels",
        }

    supports = [l for l in levels if l.level_type.lower() == "support" and l.level_price <= latest_close]
    resistances = [l for l in levels if l.level_type.lower() == "resistance" and l.level_price >= latest_close]
    nearest_support = max(supports, key=lambda l: l.level_price) if supports else None
    nearest_resistance = min(resistances, key=lambda l: l.level_price) if resistances else None

    def _pack(level: Level | None) -> dict[str, Any] | None:
        if level is None:
            return None
        distance_abs = abs(latest_close - float(level.level_price))
        distance_pct = (distance_abs / latest_close * 100.0) if latest_close else None
        return {
            "level_price": _round(level.level_price),
            "distance_abs": _round(distance_abs),
            "distance_pct": _round(distance_pct),
            "source_type": level.source_type,
            "strength_score": _round(level.strength_score),
        }

    status = "ok"
    if nearest_support is None or nearest_resistance is None:
        status = "partial"

    return {
        "primary_interval": primary_interval,
        "latest_close": _round(latest_close),
        "nearest_support": _pack(nearest_support),
        "nearest_resistance": _pack(nearest_resistance),
        "status": status,
    }


def build_scanner_summary(*, db: Session, symbol: str, primary_interval: str, market_type: str) -> dict[str, Any]:
    row = db.execute(
        select(ScanResult, ScanRun)
        .join(ScanRun, ScanRun.id == ScanResult.run_id)
        .where(ScanResult.symbol == symbol, ScanRun.strategy == "grid")
        .order_by(ScanRun.id.desc(), ScanResult.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return {"strategy": "grid", "primary_interval": primary_interval, "status": "no_scan_result"}
    result, run = row
    return {
        "strategy": run.strategy,
        "primary_interval": primary_interval,
        "grid_score": _round(result.grid_score),
        "tier": result.tier,
        "price": _round(result.price),
        "atr_pct": _round(result.atr_pct),
        "rsi": _round(result.rsi),
        "adx": _round(result.adx),
        "vwap_deviation_pct": _round(result.vwap_deviation_pct),
        "bb_width_pct": _round(result.bb_width_pct),
        "scan_run_id": run.id,
        "status": "ok",
        "limitation": "interval_not_tracked_in_scan_results",
    }


def build_risk_summary(*, nearest_levels: dict[str, Any], indicator_snapshot: dict[str, Any], scanner_summary: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    primary_interval = nearest_levels.get("primary_interval")
    ind = indicator_snapshot.get(primary_interval, {})

    latest_close = nearest_levels.get("latest_close")
    if latest_close is None:
        data_quality = "bad"
    elif ind.get("status") != "ok" or scanner_summary.get("status") != "ok":
        data_quality = "limited"
    else:
        data_quality = "ok"

    atr_pct = ind.get("atr_pct")
    if atr_pct is None:
        volatility_risk = "medium"
        warnings.append("atr_pct is unavailable")
    elif atr_pct < 1:
        volatility_risk = "low"
    elif atr_pct < 3:
        volatility_risk = "medium"
    else:
        volatility_risk = "high"

    adx = ind.get("adx")
    if adx is None:
        trend_strength = "weak"
        warnings.append("adx is unavailable")
    elif adx < 20:
        trend_strength = "weak"
    elif adx < 30:
        trend_strength = "medium"
    else:
        trend_strength = "strong"

    support = nearest_levels.get("nearest_support")
    resistance = nearest_levels.get("nearest_resistance")
    if support is None or resistance is None:
        level_distance_risk = "high"
    else:
        min_dist = min(support.get("distance_pct") or 0.0, resistance.get("distance_pct") or 0.0)
        level_distance_risk = "medium" if min_dist < 0.5 else "low"
        if min_dist < 0.5:
            warnings.append("nearest level is closer than 0.5%")

    tier = scanner_summary.get("tier")
    if scanner_summary.get("status") != "ok" or tier == "D":
        scanner_risk = "high"
        if scanner_summary.get("status") != "ok":
            warnings.append("scanner summary is unavailable")
        else:
            warnings.append("scanner tier is D")
    elif tier == "C":
        scanner_risk = "medium"
    else:
        scanner_risk = "low"

    timeframe_conflict = False

    medium_count = sum(x == "medium" for x in [volatility_risk, scanner_risk, level_distance_risk])
    if data_quality == "bad" or scanner_risk == "high" or volatility_risk == "high":
        overall_risk = "high"
    elif medium_count >= 2:
        overall_risk = "medium"
    else:
        overall_risk = "low"

    return {
        "data_quality": data_quality,
        "volatility_risk": volatility_risk,
        "trend_strength": trend_strength,
        "level_distance_risk": level_distance_risk,
        "scanner_risk": scanner_risk,
        "timeframe_conflict": timeframe_conflict,
        "overall_risk": overall_risk,
        "warnings": warnings,
    }


def build_recommendation_basis(*, risk_summary: dict[str, Any], nearest_levels: dict[str, Any], levels_summary: dict[str, Any]) -> dict[str, Any]:
    blocking_factors: list[str] = []
    if risk_summary.get("data_quality") == "bad":
        blocking_factors.append("data quality is bad")
    if nearest_levels.get("latest_close") is None:
        blocking_factors.append("latest_close is unavailable")
    if nearest_levels.get("nearest_support") is None:
        blocking_factors.append("nearest_support is unavailable")
    if nearest_levels.get("nearest_resistance") is None:
        blocking_factors.append("nearest_resistance is unavailable")
    if risk_summary.get("overall_risk") == "high":
        blocking_factors.append("overall_risk is high")

    eligible = len(blocking_factors) == 0
    primary_interval = nearest_levels.get("primary_interval")
    tf_levels = levels_summary.get(primary_interval, {})
    trend_strength = risk_summary.get("trend_strength")

    if not eligible:
        candidate_strategy = "skip"
    elif trend_strength == "strong" and tf_levels.get("has_bos"):
        candidate_strategy = "trend_follow"
    else:
        candidate_strategy = "grid"

    scanner_risk = risk_summary.get("scanner_risk")
    overall_risk = risk_summary.get("overall_risk")
    if not eligible:
        confidence_seed = 0.0
    elif scanner_risk == "low" and overall_risk == "low":
        confidence_seed = 0.7
    elif scanner_risk == "medium" and overall_risk in {"low", "medium"}:
        confidence_seed = 0.5
    else:
        confidence_seed = 0.3

    reasons = [
        f"overall risk is {overall_risk}",
        f"trend strength is {trend_strength}",
        f"scanner risk is {scanner_risk}",
    ]

    return {
        "eligible_for_recommendation": eligible,
        "candidate_strategy": candidate_strategy,
        "confidence_seed": confidence_seed,
        "reasons": reasons,
        "blocking_factors": blocking_factors,
        "suggested_bot_params": {
            "strategy_type": candidate_strategy,
            "lower_bound": (nearest_levels.get("nearest_support") or {}).get("level_price"),
            "upper_bound": (nearest_levels.get("nearest_resistance") or {}).get("level_price"),
            "reference_interval": primary_interval,
            "risk_profile": overall_risk,
        },
    }


def build_analysis_report(*, db: Session, client: BybitClient, symbol: str, intervals: str, market_type: str = settings.default_market_type) -> tuple[AnalysisReport, dict[str, Any], str]:
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

    indicator_snapshot = build_indicator_snapshot(db=db, symbol=symbol, market_type=market_type, intervals=normalized_intervals)
    levels_summary = build_levels_summary(db=db, symbol=symbol, market_type=market_type, intervals=normalized_intervals)
    nearest_levels = find_nearest_levels(db=db, symbol=symbol, market_type=market_type, intervals=normalized_intervals)
    scanner_summary = build_scanner_summary(
        db=db,
        symbol=symbol,
        primary_interval=nearest_levels["primary_interval"],
        market_type=market_type,
    )
    risk_summary = build_risk_summary(
        nearest_levels=nearest_levels,
        indicator_snapshot=indicator_snapshot,
        scanner_summary=scanner_summary,
    )
    recommendation_basis = build_recommendation_basis(
        risk_summary=risk_summary,
        nearest_levels=nearest_levels,
        levels_summary=levels_summary,
    )

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
        "indicator_snapshot": indicator_snapshot,
        "levels_summary": levels_summary,
        "nearest_levels": nearest_levels,
        "scanner_summary": scanner_summary,
        "risk_summary": risk_summary,
        "recommendation_basis": recommendation_basis,
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

    lines.extend(["", "## Indicators"])
    for tf, data in payload.get("indicator_snapshot", {}).items():
        lines.append(
            f"- **{tf}**: status={data.get('status')}, source={data.get('source')}, atr%={data.get('atr_pct')}, rsi={data.get('rsi')}, adx={data.get('adx')}"
        )

    lines.extend(["", "## Levels"])
    for tf, data in payload.get("levels_summary", {}).items():
        lines.append(
            f"- **{tf}**: status={data.get('status')}, total={data.get('total')}, support={data.get('support_count')}, resistance={data.get('resistance_count')}"
        )

    nearest = payload.get("nearest_levels", {})
    lines.extend([
        "",
        "## Nearest Levels",
        f"- Primary interval: {nearest.get('primary_interval')}",
        f"- Latest close: {nearest.get('latest_close')}",
        f"- Status: {nearest.get('status')}",
        f"- Nearest support: {nearest.get('nearest_support')}",
        f"- Nearest resistance: {nearest.get('nearest_resistance')}",
    ])

    scanner = payload.get("scanner_summary", {})
    lines.extend(["", "## Scanner", f"- Status: {scanner.get('status')}", f"- Tier: {scanner.get('tier')}", f"- Score: {scanner.get('grid_score')}"])

    risk = payload.get("risk_summary", {})
    lines.extend([
        "",
        "## Risk",
        f"- Data quality: {risk.get('data_quality')}",
        f"- Volatility risk: {risk.get('volatility_risk')}",
        f"- Scanner risk: {risk.get('scanner_risk')}",
        f"- Overall risk: {risk.get('overall_risk')}",
        f"- Warnings: {', '.join(risk.get('warnings', [])) or '-'}",
    ])

    rb = payload.get("recommendation_basis", {})
    lines.extend([
        "",
        "## Recommendation Basis",
        f"- Eligible: {rb.get('eligible_for_recommendation')}",
        f"- Candidate strategy: {rb.get('candidate_strategy')}",
        f"- Confidence seed: {rb.get('confidence_seed')}",
        f"- Blocking factors: {', '.join(rb.get('blocking_factors', [])) or '-'}",
    ])

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
