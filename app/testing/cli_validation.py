from __future__ import annotations

import subprocess
import sys

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
