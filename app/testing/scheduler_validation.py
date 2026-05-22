from __future__ import annotations

import re
import subprocess

from app.testing.models import CheckResult


def validate_scheduler_once() -> CheckResult:
    cmd = ["python", "main.py", "scheduler", "--symbols", "BTCUSDT,ETHUSDT", "--once"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = f"{proc.stdout}\n{proc.stderr}"
    forbidden = ["ProgrammingError", "OptionInfo", "Traceback", "error="]
    violations = [token for token in forbidden if token in output]
    symbols_match = re.search(r"symbols_processed=(\d+)", output)
    intervals_match = re.search(r"intervals_processed=(\d+)", output)
    symbols_ok = bool(symbols_match and int(symbols_match.group(1)) > 0)
    intervals_ok = bool(intervals_match and int(intervals_match.group(1)) > 0)
    ok = proc.returncode == 0 and not violations and symbols_ok and intervals_ok

    details: list[str] = []
    if proc.returncode != 0:
        details.append(f"returncode={proc.returncode}")
    for token in violations:
        details.append(f"forbidden token in output: {token}")
    if not symbols_ok:
        details.append("symbols_processed is missing or <= 0")
    if not intervals_ok:
        details.append("intervals_processed is missing or <= 0")
    return CheckResult(
        name="scheduler validation",
        ok=ok,
        message="scheduler once completed" if ok else "scheduler validation failed",
        details=details,
    )
