from __future__ import annotations

import compileall

from app.testing.cli_validation import validate_cli_commands, validate_compact_error
from app.testing.db_validation import validate_db_schema
from app.testing.ingestion_validation import validate_duplicates, validate_ingestion
from app.testing.models import CheckResult, SelfTestReport
from app.testing.report import write_report
from app.testing.scheduler_validation import validate_scheduler_once


def run_self_test() -> SelfTestReport:
    report = SelfTestReport()
    report.add(CheckResult(name="compileall", ok=compileall.compile_dir("app", quiet=1), message="compiled"))
    for result in validate_db_schema():
        report.add(result)
    for result in validate_ingestion():
        report.add(result)
    report.add(validate_duplicates())
    for result in validate_cli_commands():
        report.add(result)
    report.add(validate_compact_error())
    report.add(validate_scheduler_once())
    write_report(report)
    return report
