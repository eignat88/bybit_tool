from __future__ import annotations

import json
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
    return lines


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
