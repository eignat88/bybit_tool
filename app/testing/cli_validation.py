from __future__ import annotations

import subprocess
import sys

from sqlalchemy import func, select

from app.config.settings import settings
from app.db.models import AnalysisReport, BotRecommendation, IndicatorValue
from app.db.repository import SessionLocal
from app.testing.models import CheckResult


def _run(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    ok = proc.returncode == 0 and "Traceback (most recent call last)" not in out
    return ok, out.strip()


def validate_cli_commands() -> list[CheckResult]:
    checks = [
        [sys.executable, "main.py", "db-stats"],
        [sys.executable, "main.py", "candles", "BTCUSDT", "60", "--tail", "5"],
        [sys.executable, "main.py", "load", "--symbols", "BTCUSDT", "--intervals", "15,60"],
    ]
    results: list[CheckResult] = []
    for cmd in checks:
        ok, out = _run(cmd)
        results.append(CheckResult(name=f"cli {' '.join(cmd[2:])}", ok=ok, message="ok" if ok else "failed", details=[out[-500:]] if out else []))
    return results


def validate_compact_error() -> CheckResult:
    ok, out = _run([sys.executable, "main.py", "load", "--symbols", "BADUSDT", "--intervals", "60"])
    has_trace = "Traceback (most recent call last)" in out
    return CheckResult(name="compact error validation", ok=not has_trace, message="no traceback" if not has_trace else "traceback detected", details=[out[-500:]] if out else [])


def validate_interval_consistency() -> CheckResult:
    from app.core.intervals import INTERVAL_TO_MS, validate_intervals_csv

    allowed_only = set(validate_intervals_csv(",".join(INTERVAL_TO_MS))) == set(INTERVAL_TO_MS)
    invalid_rejected = False
    try:
        validate_intervals_csv("15,INVALID")
    except ValueError:
        invalid_rejected = True

    ok = allowed_only and invalid_rejected
    details = [f"allowed={sorted(INTERVAL_TO_MS)}", f"invalid_rejected={invalid_rejected}"]
    return CheckResult(name="interval validation consistency", ok=ok, message="ok" if ok else "mismatch", details=details)


def validate_market_type_consistency() -> CheckResult:
    expected = settings.default_market_type
    checks = [
        [sys.executable, "main.py", "sync-symbols"],
        [sys.executable, "main.py", "load", "--symbols", "BTCUSDT", "--intervals", "60"],
    ]
    mismatches: list[str] = []
    for cmd in checks:
        ok, out = _run(cmd)
        if not ok:
            mismatches.append(f"command failed: {' '.join(cmd[2:])}")
            continue
        if f"market_type={expected}" not in out and "sync-symbols" in cmd:
            mismatches.append(f"sync-symbols output does not include market_type={expected}")
    ok = not mismatches
    return CheckResult(
        name="market type consistency",
        ok=ok,
        message="ok" if ok else "mismatch",
        details=mismatches or [f"default_market_type={expected}"],
    )


def validate_db_check_ok() -> CheckResult:
    ok, out = _run([sys.executable, "main.py", "db-check"])
    has_fail = "[FAIL]" in out or "DB schema is outdated" in out
    result_ok = ok and not has_fail
    details = [] if result_ok else [out[-500:]]
    return CheckResult(name="db-check status", ok=result_ok, message="OK" if result_ok else "db-check failed", details=details)


def validate_indicators_no_duplicates() -> CheckResult:
    with SessionLocal() as db:
        before = db.execute(select(func.count()).select_from(IndicatorValue)).scalar_one()
    first_ok, first_out = _run([sys.executable, "main.py", "indicators", "--symbols", "BTCUSDT", "--interval", "60"])
    second_ok, second_out = _run([sys.executable, "main.py", "indicators", "--symbols", "BTCUSDT", "--interval", "60"])
    with SessionLocal() as db:
        after = db.execute(select(func.count()).select_from(IndicatorValue)).scalar_one()
        dupes = list(
            db.execute(
                select(
                    IndicatorValue.symbol,
                    IndicatorValue.market_type,
                    IndicatorValue.interval,
                    IndicatorValue.open_time,
                    IndicatorValue.indicator_name,
                    IndicatorValue.calc_version,
                    func.count().label("cnt"),
                )
                .group_by(
                    IndicatorValue.symbol,
                    IndicatorValue.market_type,
                    IndicatorValue.interval,
                    IndicatorValue.open_time,
                    IndicatorValue.indicator_name,
                    IndicatorValue.calc_version,
                )
                .having(func.count() > 1)
            )
        )
    ok = first_ok and second_ok and len(dupes) == 0 and after >= before
    details: list[str] = []
    if not first_ok:
        details.append(f"first indicators run failed: {first_out[-250:]}")
    if not second_ok:
        details.append(f"second indicators run failed: {second_out[-250:]}")
    if dupes:
        details.append(f"duplicates_detected={len(dupes)}")
    details.append(f"rows_before={before} rows_after={after}")
    return CheckResult(name="indicators duplicate safety", ok=ok, message="no duplicates" if ok else "duplicates or command failure", details=details)


def validate_analyze_saves_report_json() -> CheckResult:
    ok_cmd, out = _run([sys.executable, "main.py", "analyze", "BTCUSDT"])
    with SessionLocal() as db:
        latest = db.execute(select(AnalysisReport).where(AnalysisReport.symbol == "BTCUSDT").order_by(AnalysisReport.id.desc()).limit(1)).scalar_one_or_none()
    payload = latest.report_json if latest is not None else None
    has_payload = isinstance(payload, dict) and bool(payload) and bool(payload.get("timeframes"))
    ok = ok_cmd and has_payload
    details: list[str] = []
    if not ok_cmd:
        details.append(out[-500:])
    if latest is None:
        details.append("analysis report row not found")
    elif not has_payload:
        details.append(f"report_json invalid for id={latest.id}")
    return CheckResult(name="analyze report_json persistence", ok=ok, message="report_json saved" if ok else "report_json missing", details=details)


def validate_bot_recommendations_growth() -> CheckResult:
    with SessionLocal() as db:
        before = db.execute(select(func.count()).select_from(BotRecommendation)).scalar_one()
    ok_cmd, out = _run([sys.executable, "main.py", "analyze", "BTCUSDT", "--recommend"])
    with SessionLocal() as db:
        after = db.execute(select(func.count()).select_from(BotRecommendation)).scalar_one()
    ok = ok_cmd and after > before
    details = [f"rows_before={before}", f"rows_after={after}"]
    if not ok_cmd:
        details.append(out[-500:])
    return CheckResult(name="bot_recommendations growth", ok=ok, message="new rows inserted" if ok else "no new recommendations", details=details)
