from __future__ import annotations

from pathlib import Path

from app.cli.commands import scheduler
from app.testing.models import CheckResult


def validate_scheduler_once() -> CheckResult:
    try:
        scheduler(symbols="BTCUSDT", once=True)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="scheduler validation", ok=False, message=f"error: {type(exc).__name__}: {exc}")
    log_ok = Path("logs/scheduler.log").exists()
    return CheckResult(name="scheduler validation", ok=log_ok, message="scheduler once completed" if log_ok else "scheduler log missing")
