from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.testing.models import SelfTestReport


def render_lines(report: SelfTestReport) -> list[str]:
    lines: list[str] = []
    for r in report.results:
        status = "OK" if r.ok else "FAIL"
        lines.append(f"[{status}] {r.name}: {r.message}")
        for d in r.details:
            lines.append(f"  - {d}")
    lines.append(f"SELF_TEST_RESULT={'OK' if report.success else 'FAIL'}")
    if not report.success:
        lines.append("failed_checks:")
        for r in report.results:
            if not r.ok:
                lines.append(f"- {r.name} {r.message}")
                for d in r.details:
                    lines.append(f"- {r.name} {d}")
    return lines


def is_local_mode() -> bool:
    return os.getenv("CI", "").lower() not in {"1", "true", "yes", "on"}


def maybe_write_report(report: SelfTestReport, *, write_artifacts: bool = True) -> tuple[Path, Path] | None:
    if write_artifacts and is_local_mode():
        return write_report(report)
    return None


def write_report(report: SelfTestReport) -> tuple[Path, Path]:
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / "self_test_report.txt"
    json_path = out_dir / "self_test_report.json"
    txt_path.write_text("\n".join(render_lines(report)) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "success": report.success,
                "results": [r.__dict__ for r in report.results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return txt_path, json_path
