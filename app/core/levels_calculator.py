from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from statistics import mean

from sqlalchemy import delete, select

from app.db.models import Candle, Level
from app.db.repository import SessionLocal

logger = logging.getLogger(__name__)


@dataclass
class LevelResult:
    level_price: float
    level_type: str
    source_type: str
    description: str
    strength_score: float
    cluster_id: str | None = None
    cluster_size: int = 1
    merged_sources: str = ""
    merged_level_count: int = 1
    original_prices: str = ""
    normalized_price: float | None = None
    cluster_strength: float = 0.0
    raw_cluster_strength: float = 0.0
    percentile_rank: float = 0.0
    merged_from_count: int = 1
    is_cluster_primary: bool = True
    event_open_time: datetime | None = None
    event_age_candles: float | None = None


class LevelsCalculator:
    LOOKBACK = 350
    SWING_WINDOW = 2
    MAX_LEVELS_PER_SOURCE = 25

    NORMALIZATION_MODE = "atr"  # atr|percent
    CLUSTER_ATR_MULTIPLIER = 0.15
    CLUSTER_PERCENT_THRESHOLD = 0.0015

    SOURCE_PRIORITY = {"choch": 4, "bos": 3, "swing_high": 2, "swing_low": 2, "fvg": 1}
    SOURCE_WEIGHT = {"choch": 1.0, "bos": 0.9, "swing": 0.7, "fvg": 0.5}
    SOURCE_STRENGTH_MULTIPLIER = {"choch": 1.0, "bos": 1.0, "swing_high": 1.0, "swing_low": 1.0, "fvg": 1.0}

    FVG_MIN_GAP_SIZE = 5.0
    FVG_ATR_MIN_FACTOR = 0.08
    FVG_DISPLACEMENT_FACTOR = 1.2
    FVG_USE_VOLUME_CONFIRMATION = False
    FVG_VOLUME_FACTOR = 1.3

    CLUSTER_SIZE_BONUS_FACTOR = 9.0
    TOUCH_BONUS_FACTOR = 1.8
    PROXIMITY_BONUS_FACTOR = 2.2
    PROXIMITY_DISTANCE_FACTOR = 1.8
    DECAY_TAU_CANDLES = 120.0
    WIDTH_PENALTY_ATR_K = 1.0
    WIDTH_PENALTY_BETA = 1.4

    def calculate(self, symbol: str, interval: str, market_type: str = "linear") -> list[LevelResult]:
        symbol_u = symbol.upper()
        with SessionLocal() as db:
            candles = list(
                db.execute(
                    select(Candle)
                    .where(Candle.symbol == symbol_u, Candle.interval == interval, Candle.market_type == market_type)
                    .order_by(Candle.open_time.desc())
                    .limit(self.LOOKBACK)
                )
                .scalars()
            )
            candles.reverse()
            if len(candles) < 20:
                db.execute(
                    delete(Level).where(
                        Level.symbol == symbol_u,
                        Level.interval == interval,
                        Level.market_type == market_type,
                    )
                )
                db.commit()
                return []

            results = self._detect_levels(candles)

            db.execute(
                delete(Level).where(
                    Level.symbol == symbol_u,
                    Level.interval == interval,
                    Level.market_type == market_type,
                )
            )
            db.add_all(
                [
                    Level(
                        symbol=symbol_u,
                        market_type=market_type,
                        interval=interval,
                        level_price=row.level_price,
                        level_type=row.level_type,
                        source_type=row.source_type,
                        description=row.description,
                        strength_score=row.strength_score,
                        cluster_id=row.cluster_id,
                        normalized_price=row.normalized_price or row.level_price,
                        cluster_strength=row.cluster_strength or row.strength_score,
                        merged_from_count=row.merged_from_count,
                        is_cluster_primary=row.is_cluster_primary,
                        event_open_time=row.event_open_time,
                        event_age_candles=row.event_age_candles,
                    )
                    for row in results
                ]
            )
            db.commit()
            return results

    def _detect_levels(self, candles: list[Candle]) -> list[LevelResult]:
        avg_range = mean([(c.high - c.low) for c in candles[-100:]])
        atr = self._calculate_atr(candles)
        out: list[LevelResult] = []
        out.extend(self._detect_swings(candles, avg_range))
        out.extend(self._detect_bos_choch(candles, avg_range))
        out.extend(self._detect_fvg(candles, avg_range, atr))

        normalized = self._normalize_levels(out, candles, atr)
        scored = self._apply_percentile_scoring(normalized)
        scored.sort(key=lambda x: x.cluster_strength, reverse=True)
        return scored[: self.MAX_LEVELS_PER_SOURCE * 4]

    def _apply_percentile_scoring(self, clusters: list[LevelResult]) -> list[LevelResult]:
        if not clusters:
            return []
        sorted_scores = sorted(c.cluster_strength for c in clusters)
        n = len(sorted_scores)

        for cluster in clusters:
            raw_score = cluster.cluster_strength
            less_count = sum(1 for score in sorted_scores if score < raw_score)
            equal_count = sum(1 for score in sorted_scores if score == raw_score)
            # Midrank percentile for ties: all tied values receive the same percentile.
            rank_position = less_count + (equal_count - 1) / 2
            percentile = 100.0 if n == 1 else (rank_position / (n - 1)) * 100.0

            percentile_score = self._map_percentile_to_score(percentile)
            cluster.raw_cluster_strength = round(raw_score, 2)
            cluster.percentile_rank = round(percentile, 2)
            cluster.cluster_strength = round(percentile_score, 2)
            cluster.strength_score = round(percentile_score, 2)
            cluster.description = (
                f"{cluster.description}; "
                f"raw_score={cluster.raw_cluster_strength:.2f}; "
                f"percentile={cluster.percentile_rank:.2f}; "
                f"percentile_score={cluster.cluster_strength:.2f}"
            )
        return clusters

    def _map_percentile_to_score(self, percentile: float) -> float:
        p = max(0.0, min(100.0, percentile))
        if p >= 99.0:
            # Top 1% -> 95..100
            return 95.0 + ((p - 99.0) / 1.0) * 5.0
        if p >= 95.0:
            # Top 5% -> 85..95
            return 85.0 + ((p - 95.0) / 4.0) * 10.0
        # Linear baseline where median is near 50.
        return p

    def _calculate_atr(self, candles: list[Candle], period: int = 14) -> float:
        trs: list[float] = []
        for i in range(1, len(candles)):
            curr = candles[i]
            prev = candles[i - 1]
            tr = max(curr.high - curr.low, abs(curr.high - prev.close), abs(curr.low - prev.close))
            trs.append(tr)
        sample = trs[-period:] if len(trs) >= period else trs
        return mean(sample) if sample else 0.0

    def _cluster_distance_threshold(self, ref_price: float, atr: float) -> float:
        if self.NORMALIZATION_MODE == "percent":
            return max(ref_price * self.CLUSTER_PERCENT_THRESHOLD, 1e-9)
        return max(atr * self.CLUSTER_ATR_MULTIPLIER, 1e-9)

    def _normalize_levels(self, raw: list[LevelResult], candles: list[Candle], atr: float) -> list[LevelResult]:
        if not raw:
            return []
        sorted_levels = sorted(raw, key=lambda x: x.level_price)
        clusters: list[list[LevelResult]] = []

        for level in sorted_levels:
            if not clusters:
                clusters.append([level])
                continue
            prev_cluster = clusters[-1]
            ref_price = mean(x.level_price for x in prev_cluster)
            threshold = self._cluster_distance_threshold(ref_price, atr)
            if abs(level.level_price - ref_price) <= threshold:
                prev_cluster.append(level)
            else:
                clusters.append([level])

        logger.debug("[LEVEL_NORMALIZER] cluster created count=%s", len(clusters))
        return [self._merge_cluster(cluster, idx, candles, atr, sorted_levels) for idx, cluster in enumerate(clusters, start=1)]

    def _merge_cluster(
        self,
        cluster: list[LevelResult],
        idx: int,
        candles: list[Candle],
        atr: float,
        all_levels: list[LevelResult],
    ) -> LevelResult:
        primary = max(cluster, key=lambda x: (self.SOURCE_PRIORITY.get(x.source_type, 0), x.strength_score))
        normalized_price = mean(x.level_price for x in cluster)
        merged_sources = sorted({x.source_type for x in cluster})
        weighted_score = self._weighted_cluster_score(cluster)
        cluster_size_bonus = math.log1p(max(0, len(cluster) - 1)) * self.CLUSTER_SIZE_BONUS_FACTOR
        source_bonus = self.SOURCE_PRIORITY.get(primary.source_type, 0) * 1.25
        touch_bonus = self._count_touches(candles, normalized_price, atr) * self.TOUCH_BONUS_FACTOR
        proximity_bonus = self._proximity_bonus(normalized_price, primary.source_type, all_levels, atr)
        age_candles = self._cluster_event_age_candles(cluster, candles)
        age_decay = self._age_decay_multiplier_by_event(age_candles)
        spread_penalty = self._cluster_spread_penalty(cluster, normalized_price, atr)

        new_score = (weighted_score + cluster_size_bonus + source_bonus + touch_bonus + proximity_bonus)
        new_score *= self.SOURCE_STRENGTH_MULTIPLIER.get(primary.source_type, 1.0)
        new_score *= age_decay
        new_score *= spread_penalty
        new_score = max(0.0, min(100.0, new_score))

        logger.debug(
            "[LEVEL_NORMALIZER] levels merged cluster_id=%s merged=%s score=%.2f",
            idx,
            len(cluster),
            new_score,
        )

        return LevelResult(
            level_price=normalized_price,
            level_type=primary.level_type,
            source_type=primary.source_type,
            description=f"Normalized cluster from {len(cluster)} levels",
            strength_score=round(new_score, 2),
            cluster_id=f"cluster_{idx}",
            cluster_size=len(cluster),
            merged_sources=",".join(merged_sources),
            merged_level_count=len(cluster),
            original_prices=",".join(f"{x.level_price:.4f}" for x in cluster),
            normalized_price=normalized_price,
            cluster_strength=round(new_score, 2),
            raw_cluster_strength=round(new_score, 2),
            merged_from_count=len(cluster),
            is_cluster_primary=True,
            event_open_time=self._cluster_newest_event_time(cluster),
            event_age_candles=age_candles,
        )

    def _weighted_cluster_score(self, cluster: list[LevelResult]) -> float:
        weighted_sum = 0.0
        weight_total = 0.0
        for level in cluster:
            weight = self.SOURCE_WEIGHT.get(self._weight_source_group(level.source_type), 1.0)
            weighted_sum += level.strength_score * weight
            weight_total += weight
        if weight_total <= 0.0:
            return mean(x.strength_score for x in cluster)
        return weighted_sum / weight_total

    def _weight_source_group(self, source_type: str) -> str:
        if source_type in {"swing_high", "swing_low"}:
            return "swing"
        return source_type

    def _cluster_spread_penalty(self, cluster: list[LevelResult], center_price: float, atr: float) -> float:
        if len(cluster) <= 1:
            return 1.0
        spread = max(x.level_price for x in cluster) - min(x.level_price for x in cluster)
        threshold = max(atr * self.WIDTH_PENALTY_ATR_K, 1e-9)
        if spread <= threshold:
            return 1.0
        excess_ratio = (spread - threshold) / threshold
        return 1.0 / (1.0 + self.WIDTH_PENALTY_BETA * excess_ratio)

    def _count_touches(self, candles: list[Candle], price: float, atr: float) -> int:
        threshold = max(atr * 0.1, price * 0.0005)
        return sum(1 for c in candles if c.low <= price + threshold and c.high >= price - threshold)

    def _proximity_bonus(self, price: float, source_type: str, all_levels: list[LevelResult], atr: float) -> float:
        threshold = max(atr * self.PROXIMITY_DISTANCE_FACTOR, price * self.CLUSTER_PERCENT_THRESHOLD)
        strong_neighbors = [
            lvl for lvl in all_levels if lvl.source_type != source_type and abs(lvl.level_price - price) <= threshold and lvl.strength_score >= 60
        ]
        return len(strong_neighbors) * self.PROXIMITY_BONUS_FACTOR

    def _cluster_newest_event_time(self, cluster: list[LevelResult]) -> datetime | None:
        timestamps = [lvl.event_open_time for lvl in cluster if lvl.event_open_time is not None]
        return max(timestamps) if timestamps else None

    def _cluster_event_age_candles(self, cluster: list[LevelResult], candles: list[Candle]) -> float:
        if not candles:
            return 0.0
        last_open_time = candles[-1].open_time
        weighted_age = 0.0
        weight_total = 0.0
        for level in cluster:
            if level.event_open_time is None:
                continue
            age = max(0.0, float((last_open_time - level.event_open_time).total_seconds()))
            weight = self.SOURCE_WEIGHT.get(self._weight_source_group(level.source_type), 1.0)
            weighted_age += age * weight
            weight_total += weight
        if weight_total <= 0.0:
            return 0.0
        avg_age_seconds = weighted_age / weight_total
        candle_seconds = max(1.0, float((candles[-1].open_time - candles[-2].open_time).total_seconds())) if len(candles) > 1 else 1.0
        return avg_age_seconds / candle_seconds

    def _age_decay_multiplier_by_event(self, age_candles: float) -> float:
        return math.exp(-(max(0.0, age_candles) / max(self.DECAY_TAU_CANDLES, 1e-9)))

    def _detect_swings(self, candles: list[Candle], avg_range: float) -> list[LevelResult]:
        swings: list[LevelResult] = []
        w = self.SWING_WINDOW
        for i in range(w, len(candles) - w):
            center = candles[i]
            left = candles[i - w : i]
            right = candles[i + 1 : i + 1 + w]
            if all(center.high > c.high for c in left + right):
                score = min(100.0, 45.0 + (center.high - max(c.high for c in left + right)) / max(avg_range, 1e-9) * 12.0)
                swings.append(
                    LevelResult(
                        center.high,
                        "resistance",
                        "swing_high",
                        "Liquidity swing high",
                        round(score, 2),
                        event_open_time=center.open_time,
                    )
                )
            if all(center.low < c.low for c in left + right):
                score = min(100.0, 45.0 + (min(c.low for c in left + right) - center.low) / max(avg_range, 1e-9) * 12.0)
                swings.append(
                    LevelResult(
                        center.low,
                        "support",
                        "swing_low",
                        "Liquidity swing low",
                        round(score, 2),
                        event_open_time=center.open_time,
                    )
                )
        return swings[-self.MAX_LEVELS_PER_SOURCE :]

    def _detect_bos_choch(self, candles: list[Candle], avg_range: float) -> list[LevelResult]:
        levels: list[LevelResult] = []
        recent_high = candles[0].high
        recent_low = candles[0].low
        trend = 0
        for c in candles[1:]:
            if c.close > recent_high:
                source = "bos" if trend >= 0 else "choch"
                trend = 1
                score = min(100.0, 55.0 + (c.close - recent_high) / max(avg_range, 1e-9) * 15.0)
                levels.append(
                    LevelResult(
                        recent_high,
                        "support",
                        source,
                        f"{source.upper()} up confirmed by close breakout",
                        round(score, 2),
                        event_open_time=c.open_time,
                    )
                )
            if c.close < recent_low:
                source = "bos" if trend <= 0 else "choch"
                trend = -1
                score = min(100.0, 55.0 + (recent_low - c.close) / max(avg_range, 1e-9) * 15.0)
                levels.append(
                    LevelResult(
                        recent_low,
                        "resistance",
                        source,
                        f"{source.upper()} down confirmed by close breakout",
                        round(score, 2),
                        event_open_time=c.open_time,
                    )
                )
            recent_high = max(recent_high, c.high)
            recent_low = min(recent_low, c.low)
        return levels[-self.MAX_LEVELS_PER_SOURCE :]

    def _detect_fvg(self, candles: list[Candle], avg_range: float, atr: float) -> list[LevelResult]:
        fvgs: list[LevelResult] = []
        avg_volume = mean([c.volume for c in candles[-100:]]) if candles else 0.0
        for i in range(2, len(candles)):
            c0 = candles[i - 2]
            c1 = candles[i - 1]
            c2 = candles[i]
            displacement = abs(c1.close - c1.open)
            if c2.low > c0.high:
                gap = c2.low - c0.high
                if not self._fvg_passes_filters(gap, atr, displacement, avg_range, c1.volume, avg_volume):
                    logger.debug("[LEVEL_NORMALIZER] fvg filtered type=bull gap=%.4f", gap)
                    continue
                score = min(100.0, 50.0 + gap / max(avg_range, 1e-9) * 18.0)
                fvgs.append(
                    LevelResult(
                        (c2.low + c0.high) / 2.0,
                        "support",
                        "fvg",
                        "Bullish FVG midpoint",
                        round(score, 2),
                        event_open_time=c2.open_time,
                    )
                )
            elif c2.high < c0.low:
                gap = c0.low - c2.high
                if not self._fvg_passes_filters(gap, atr, displacement, avg_range, c1.volume, avg_volume):
                    logger.debug("[LEVEL_NORMALIZER] fvg filtered type=bear gap=%.4f", gap)
                    continue
                score = min(100.0, 50.0 + gap / max(avg_range, 1e-9) * 18.0)
                fvgs.append(
                    LevelResult(
                        (c2.high + c0.low) / 2.0,
                        "resistance",
                        "fvg",
                        "Bearish FVG midpoint",
                        round(score, 2),
                        event_open_time=c2.open_time,
                    )
                )
        return fvgs[-self.MAX_LEVELS_PER_SOURCE :]

    def _fvg_passes_filters(
        self,
        gap: float,
        atr: float,
        displacement: float,
        avg_range: float,
        candle_volume: float,
        avg_volume: float,
    ) -> bool:
        if gap < self.FVG_MIN_GAP_SIZE:
            return False
        if gap < atr * self.FVG_ATR_MIN_FACTOR:
            return False
        if displacement < avg_range * self.FVG_DISPLACEMENT_FACTOR:
            return False
        if self.FVG_USE_VOLUME_CONFIRMATION and candle_volume < avg_volume * self.FVG_VOLUME_FACTOR:
            return False
        return True

    def to_tradingview_csv(self, levels: list[LevelResult]) -> str:
        lines = ["price,type,source,description,strength,cluster_id,cluster_size,merged_from_count"]
        for lvl in levels:
            safe_desc = lvl.description.replace(",", " ")
            lines.append(
                f"{lvl.level_price:.8f},{lvl.level_type},{lvl.source_type},{safe_desc},{lvl.strength_score:.2f},{lvl.cluster_id or ''},{lvl.cluster_size},{lvl.merged_from_count}"
            )
        return "\n".join(lines)
