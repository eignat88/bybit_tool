from __future__ import annotations

import subprocess
import sys

from app.config.settings import settings
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
