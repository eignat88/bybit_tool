from __future__ import annotations

import compileall
import os

from app.testing.cli_validation import (
    validate_cli_commands,
    validate_compact_error,
    validate_interval_consistency,
    validate_market_type_consistency,
)
from app.testing.db_validation import validate_db_objects
from app.testing.ingestion_validation import validate_duplicates, validate_ingestion
from app.testing.models import CheckResult, SelfTestReport
from app.testing.report import maybe_write_report
from app.testing.scheduler_validation import validate_scheduler_once


def run_self_test(*, quick: bool = False, write_artifacts: bool | None = None) -> SelfTestReport:
    report = SelfTestReport()
    if not quick:
        report.add(CheckResult(name="compileall", ok=compileall.compile_dir("app", quiet=1), message="compiled"))
    for result in validate_db_objects():
        report.add(result)
    for result in validate_ingestion():
        report.add(result)
    report.add(validate_duplicates())
    for result in validate_cli_commands():
        report.add(result)
    report.add(validate_compact_error())
    report.add(validate_interval_consistency())
    report.add(validate_scheduler_once())
    report.add(validate_market_type_consistency())
    if write_artifacts is None:
        write_artifacts = os.getenv("SELF_TEST_WRITE_ARTIFACTS", "1").lower() not in {"0", "false", "no", "off"}
    maybe_write_report(report, write_artifacts=write_artifacts)
    return report
