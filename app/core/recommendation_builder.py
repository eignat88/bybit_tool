from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select

from app.db.models import AnalysisReport, BotRecommendation, Candle, IndicatorValue, Level, ScanResult

from app.core.domain_errors import DataNotFoundWarning, RecommendationInputError

ALLOWED_STRUCTURE_EVENTS = {"bos", "choch"}
EVENT_WINDOW = 5
MIN_CONFIDENCE_TO_ACT = 0.6
ALLOWED_STRATEGIES = {"grid", "trend_follow", "range_trade", "skip"}


@dataclass(slots=True)
class RecommendationResult:
    status: str
    reason: str | None = None
    warnings: list[str] | None = None
    strategy_type: str | None = None
    params: dict[str, Any] | None = None
    confidence: float | None = None


class RecommendationBuilder:
    """Build trading recommendation from analysis payload."""

    def build(self, report_payload: dict[str, Any] | None) -> RecommendationResult:
        if not report_payload:
            raise DataNotFoundWarning("no_analysis_report")

        if not isinstance(report_payload, dict):
            raise RecommendationInputError("report_payload must be a JSON object")

        basis = report_payload.get("recommendation_basis")
        if not isinstance(basis, dict):
            return RecommendationResult(
                status="skip",
                reason="no_recommendation_basis",
                warnings=["recommendation_basis_missing"],
            )

        direction = self._read_direction(report_payload, basis)
        if direction is None:
            return RecommendationResult(status="skip", reason="no_direction", warnings=["direction_not_available"])

        if not self._direction_confirmed(report_payload, basis, direction):
            return RecommendationResult(
                status="skip",
                reason="direction_not_confirmed",
                warnings=["structure_or_level_confirmation_missing"],
            )

        if not basis.get("eligible_for_recommendation", False):
            return RecommendationResult(status="skip", reason="not_eligible")

        candidate_strategy = str(basis.get("candidate_strategy") or "grid")
        confidence = float(basis.get("confidence_score", 0.0))

        actionable_strategies = {"grid", "range", "trend", "trend_follow"}
        if candidate_strategy in actionable_strategies and confidence < MIN_CONFIDENCE_TO_ACT:
            return RecommendationResult(
                status="skip",
                reason="low_confidence",
                strategy_type="skip",
                confidence=confidence,
            )

        suggested_params = basis.get("suggested_bot_params")
        params: dict[str, Any] = {"source": "analysis_report"}
        if isinstance(suggested_params, dict):
            params.update(suggested_params)
        return RecommendationResult(
            status="ok",
            strategy_type=candidate_strategy,
            params=params,
            confidence=confidence,
        )

    def _read_direction(self, report_payload: dict[str, Any], basis: dict[str, Any]) -> str | None:
        reference_interval = ((basis.get("suggested_bot_params") or {}).get("reference_interval")) or (
            (report_payload.get("nearest_levels") or {}).get("primary_interval")
        )
        market_structure = report_payload.get("market_structure")
        if not isinstance(market_structure, dict) or reference_interval is None:
            return None
        trend = (market_structure.get(str(reference_interval)) or {}).get("trend_regime")
        return trend if trend in {"trend_up", "trend_down"} else None

    def _direction_confirmed(self, report_payload: dict[str, Any], basis: dict[str, Any], direction: str) -> bool:
        expected_event_side = "bullish" if direction == "trend_up" else "bearish"
        expected_level_key = "strongest_support" if direction == "trend_up" else "strongest_resistance"

        reference_interval = ((basis.get("suggested_bot_params") or {}).get("reference_interval")) or (
            (report_payload.get("nearest_levels") or {}).get("primary_interval")
        )
        levels_summary = (report_payload.get("levels_summary") or {}).get(str(reference_interval), {})
        recent_events = levels_summary.get("recent_structure_events") or []

        valid_events = [
            e
            for e in recent_events[-EVENT_WINDOW:]
            if isinstance(e, dict)
            and str(e.get("type", "")).lower() in ALLOWED_STRUCTURE_EVENTS
            and str(e.get("side", "")).lower() == expected_event_side
        ]
        has_structure_confirmation = len(valid_events) > 0

        strong_level = levels_summary.get(expected_level_key)
        has_level_confirmation = isinstance(strong_level, dict) and (strong_level.get("strength_score") is not None)
        return has_structure_confirmation and has_level_confirmation


def build_recommendation(
    db: sa.orm.Session,
    symbol: str,
    market_type: str,
    intervals: list[str],
    source_report_id: int | None = None,
) -> BotRecommendation:
    normalized_symbol = symbol.upper()
    report = None
    if source_report_id is not None:
        report = db.execute(select(AnalysisReport).where(AnalysisReport.id == source_report_id)).scalar_one_or_none()
    if report is None:
        report = db.execute(
            select(AnalysisReport)
            .where(AnalysisReport.symbol == normalized_symbol)
            .order_by(AnalysisReport.created_at.desc(), AnalysisReport.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    scan = db.execute(
        select(ScanResult).where(ScanResult.symbol == normalized_symbol).order_by(ScanResult.id.desc()).limit(1)
    ).scalar_one_or_none()
    current_price = float(scan.price) if scan is not None else None
    if current_price is None:
        candle = db.execute(
            select(Candle)
            .where(Candle.symbol == normalized_symbol, Candle.market_type == market_type)
            .order_by(Candle.open_time.desc(), Candle.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        current_price = float(candle.close) if candle is not None else None

    interval = intervals[-1] if intervals else "60"
    level_rows = db.execute(
        select(Level).where(Level.symbol == normalized_symbol, Level.market_type == market_type, Level.interval == interval)
    ).scalars().all()
    supports = sorted([lv for lv in level_rows if lv.level_type == "support"], key=lambda x: x.level_price)
    resistances = sorted([lv for lv in level_rows if lv.level_type == "resistance"], key=lambda x: x.level_price)

    nearest_support = max((s.level_price for s in supports if current_price is not None and s.level_price < current_price), default=None)
    nearest_resistance = min((r.level_price for r in resistances if current_price is not None and r.level_price > current_price), default=None)

    indicators = db.execute(
        select(IndicatorValue)
        .where(IndicatorValue.symbol == normalized_symbol, IndicatorValue.interval == interval)
        .order_by(IndicatorValue.open_time.desc(), IndicatorValue.id.desc())
        .limit(50)
    ).scalars().all()
    ind_map = {it.indicator_name: float(it.value) for it in indicators}
    adx = float(getattr(scan, "adx", ind_map.get("adx", 0.0)) or 0.0)
    rsi = float(getattr(scan, "rsi", ind_map.get("rsi", 50.0)) or 50.0)
    grid_score = float(getattr(scan, "grid_score", 0.0) or 0.0)
    tier = str(getattr(scan, "tier", "") or "")

    reasons: list[str] = []
    warnings: list[str] = []
    strategy_type = "skip"
    range_width_pct = None
    if current_price and nearest_support and nearest_resistance:
        range_width_pct = ((nearest_resistance - nearest_support) / current_price) * 100

    trend = None
    if report and isinstance(report.report_json, dict):
        market_structure = report.report_json.get("market_structure") or {}
        trend = (market_structure.get(str(interval)) or {}).get("trend_regime")

    if current_price is None:
        warnings.append("no_current_price")
    if report is None:
        warnings.append("no_analysis_report")
    if not level_rows:
        warnings.append("no_levels")

    if all([current_price, nearest_support, nearest_resistance, range_width_pct is not None]):
        if grid_score >= 55 and tier in {"A", "B", "C"} and adx < 25 and range_width_pct >= 1.0:
            strategy_type = "grid"
            reasons.extend(["grid_score >= 55", "ADX < 25", "support and resistance found"])
        elif adx < 20 and 40 <= rsi <= 60 and range_width_pct >= 0.8:
            strategy_type = "range_trade"
            reasons.extend(["ADX < 20", "RSI in 40..60", "support and resistance found"])
        elif adx >= 25 and trend in {"trend_up", "trend_down"}:
            strategy_type = "trend_follow"
            reasons.extend(["ADX >= 25", "trend defined in analysis_report", "structure/level confirmation present"])

    confidence = 0.0
    confidence += 0.25 if scan is not None else 0.0
    confidence += 0.20 if level_rows else 0.0
    confidence += 0.20 if indicators else 0.0
    confidence += 0.20 if report is not None else 0.0
    confidence += 0.15 if strategy_type != "skip" else 0.0
    confidence = min(max(confidence, 0.0), 1.0)

    if strategy_type not in ALLOWED_STRATEGIES:
        strategy_type = "skip"
        warnings.append("invalid_strategy_normalized_to_skip")

    params_json = {
        "symbol": normalized_symbol,
        "market_type": market_type,
        "strategy_type": strategy_type,
        "timeframes": intervals,
        "current_price": current_price,
        "source": {"analysis_report_id": report.id if report else None, "scan_result_id": scan.id if scan else None},
        "scanner": {
            "grid_score": grid_score,
            "tier": tier,
            "rsi": rsi,
            "adx": adx,
        },
        "levels": {
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "support_count": len(supports),
            "resistance_count": len(resistances),
            "strong_levels_count": len([x for x in level_rows if float(x.strength_score or 0.0) >= 0.7]),
        },
        "recommendation": {
            "strategy_type": strategy_type,
            "confidence": confidence,
            "direction": trend,
            "lower_bound": nearest_support,
            "upper_bound": nearest_resistance,
            "range_width_pct": range_width_pct,
            "risk_level": "medium",
        },
        "reasons": reasons,
        "warnings": warnings,
    }

    recommendation = BotRecommendation(
        symbol=normalized_symbol,
        market_type=market_type,
        strategy_type=strategy_type,
        params_json=json.dumps(params_json),
        confidence=confidence,
        source_report_id=report.id if report else None,
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation
