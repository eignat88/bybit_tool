from __future__ import annotations

from sqlalchemy import DateTime, Float, UniqueConstraint, inspect

from app.db.models import Base
from app.db.repository import engine
from app.testing.models import CheckResult


LEVELS_REQUIRED_COLUMNS = [
    "cluster_id",
    "normalized_price",
    "cluster_strength",
    "merged_from_count",
    "is_cluster_primary",
]

ANALYSIS_REPORTS_REQUIRED_INDEXES = [
    "ix_analysis_reports_report_json_gin",
    "ix_analysis_reports_json_market_type",
    "ix_analysis_reports_json_overall_risk",
    "ix_analysis_reports_json_candidate_strategy",
    "ix_analysis_reports_json_eligible",
]


def get_missing_levels_columns() -> list[str]:
    inspector = inspect(engine)
    if not inspector.has_table("levels"):
        return LEVELS_REQUIRED_COLUMNS.copy()

    columns = {c["name"] for c in inspector.get_columns("levels")}
    return [name for name in LEVELS_REQUIRED_COLUMNS if name not in columns]


def validate_db_schema() -> list[CheckResult]:
    inspector = inspect(engine)
    results: list[CheckResult] = []
    for table in Base.metadata.sorted_tables:
        table_name = table.name
        if not inspector.has_table(table_name):
            results.append(CheckResult(name=f"table {table_name}", ok=False, message="table missing"))
            continue

        db_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
        model_columns = {c.name: c for c in table.columns}
        details: list[str] = []
        ok = True

        for col_name, col in model_columns.items():
            if col_name not in db_columns:
                ok = False
                details.append(f"{table_name}.{col_name} missing in database")
                continue
            db_col = db_columns[col_name]
            db_type = str(db_col["type"]).lower()
            if not _types_equivalent(col.type, db_type):
                ok = False
                details.append(f"{table_name}.{col_name} type mismatch model={col.type} db={db_col['type']}")
            if bool(col.nullable) != bool(db_col["nullable"]):
                ok = False
                details.append(
                    f"{table_name}.{col_name} nullable mismatch model={col.nullable} db={db_col['nullable']}"
                )

        if table_name == "analysis_reports" and "report_json" in db_columns:
            actual_type = str(db_columns["report_json"]["type"]).lower()
            if "jsonb" not in actual_type:
                ok = False
                details.append(f"analysis_reports.report_json expected jsonb, found {db_columns['report_json']['type']}")

        for col_name in db_columns:
            if col_name not in model_columns:
                ok = False
                details.append(f"{table_name}.{col_name} extra in database")

        msg = "schema valid" if ok else "schema drift detected"
        if table_name == "analysis_reports":
            jsonb_error = next((d for d in details if d.startswith("analysis_reports.report_json expected jsonb")), None)
            if jsonb_error:
                msg = jsonb_error
        results.append(CheckResult(name=f"schema {table_name}", ok=ok, message=msg, details=details))
    return results


def _types_equivalent(model_type: object, db_type_text: str) -> bool:
    db_type = db_type_text.lower()

    if isinstance(model_type, Float):
        return any(token in db_type for token in ("float", "double precision", "real", "numeric", "decimal"))

    if isinstance(model_type, DateTime):
        tz_intended = bool(getattr(model_type, "timezone", False))
        if tz_intended:
            return "timestamp with time zone" in db_type or "timestamptz" in db_type
        return "timestamp without time zone" in db_type or (
            "timestamp" in db_type and "with time zone" not in db_type and "timestamptz" not in db_type
        )

    model_name = str(model_type).lower().split("(")[0]
    return model_name in db_type


def validate_db_objects() -> list[CheckResult]:
    inspector = inspect(engine)
    results: list[CheckResult] = []
    for table in Base.metadata.sorted_tables:
        t = table.name
        if not inspector.has_table(t):
            results.append(CheckResult(name=f"db-check {t}", ok=False, message="table missing"))
            continue
        model_indexes = {idx.name for idx in table.indexes if idx.name}
        db_indexes = {idx["name"] for idx in inspector.get_indexes(t) if idx.get("name")}
        missing_indexes = sorted(model_indexes - db_indexes)
        if t == "analysis_reports":
            missing_indexes.extend(name for name in ANALYSIS_REPORTS_REQUIRED_INDEXES if name not in db_indexes)
            missing_indexes = sorted(set(missing_indexes))

        model_uq = {c.name for c in table.constraints if isinstance(c, UniqueConstraint) and c.name}
        db_uq_meta = inspector.get_unique_constraints(t)
        db_uq_names = {c["name"] for c in db_uq_meta if c.get("name")}
        missing_uq = sorted(model_uq - db_uq_names)

        # Canonicalize symbols(symbol, market_type) unique constraint even when DB name differs.
        if t == "symbols" and "uq_symbol_market_type" in missing_uq:
            has_equivalent = any(tuple(uq.get("column_names") or []) == ("symbol", "market_type") for uq in db_uq_meta)
            if has_equivalent:
                missing_uq.remove("uq_symbol_market_type")

        ok = not missing_indexes and not missing_uq
        details = [f"missing index: {x}" for x in missing_indexes] + [f"missing unique: {x}" for x in missing_uq]
        results.append(CheckResult(name=f"db-check {t}", ok=ok, message="objects valid" if ok else "objects missing", details=details))
    return results
