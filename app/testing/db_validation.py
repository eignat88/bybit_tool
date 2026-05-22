from __future__ import annotations

from app.db.models import Base
from app.db.repository import engine
from app.testing.models import CheckResult
from app.testing.schema_inspection import build_schema_snapshots, model_unique_constraints


def validate_db_schema() -> list[CheckResult]:
    snapshots = build_schema_snapshots(engine, list(Base.metadata.sorted_tables))
    results: list[CheckResult] = []
    for table in Base.metadata.sorted_tables:
        table_name = table.name
        snapshot = snapshots[table_name]
        if not snapshot.has_table:
            results.append(CheckResult(name=f"schema {table_name}", ok=False, message="table missing"))
            continue

        model_columns = {c.name: c for c in table.columns}
        details: list[str] = []
        ok = True

        for col_name, col in model_columns.items():
            if col_name not in snapshot.columns:
                ok = False
                details.append(f"{table_name}.{col_name} missing in database")
                continue
            db_col = snapshot.columns[col_name]
            db_type = str(db_col["type"]).lower()
            model_type = str(col.type).lower()
            if model_type.split("(")[0] not in db_type:
                ok = False
                details.append(f"{table_name}.{col_name} type mismatch model={model_type} db={db_type}")
            if bool(col.nullable) != bool(db_col["nullable"]):
                ok = False
                details.append(
                    f"{table_name}.{col_name} nullable mismatch model={col.nullable} db={db_col['nullable']}"
                )

        for col_name in snapshot.columns:
            if col_name not in model_columns:
                ok = False
                details.append(f"{table_name}.{col_name} extra in database")

        msg = "schema valid" if ok else "schema drift detected"
        results.append(CheckResult(name=f"schema {table_name}", ok=ok, message=msg, details=details))
    return results


def validate_db_objects() -> list[CheckResult]:
    snapshots = build_schema_snapshots(engine, list(Base.metadata.sorted_tables))
    results: list[CheckResult] = []
    for table in Base.metadata.sorted_tables:
        table_name = table.name
        snapshot = snapshots[table_name]
        if not snapshot.has_table:
            results.append(CheckResult(name=f"db-check {table_name}", ok=False, message="table missing"))
            continue

        model_indexes = {idx.name for idx in table.indexes if idx.name}
        missing_indexes = sorted(model_indexes - snapshot.indexes_by_name)

        model_uq_names, model_uq_signatures = model_unique_constraints(table)
        missing_uq = sorted(
            uq_name
            for uq_name in model_uq_names
            if uq_name not in snapshot.unique_by_name
            and _signature_from_name(table, uq_name, model_uq_signatures) not in snapshot.unique_signatures
        )

        ok = not missing_indexes and not missing_uq
        details = [f"missing index: {x}" for x in missing_indexes] + [f"missing unique: {x}" for x in missing_uq]
        results.append(
            CheckResult(
                name=f"db-check {table_name}",
                ok=ok,
                message="objects valid" if ok else "objects missing",
                details=details,
            )
        )
    return results


def _signature_from_name(table, uq_name: str, signatures: set[tuple[str, ...]]) -> tuple[str, ...]:
    for constraint in table.constraints:
        if getattr(constraint, "name", None) == uq_name:
            return tuple(col.name for col in constraint.columns)
    return () if () in signatures else ()
