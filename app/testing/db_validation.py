from __future__ import annotations

from sqlalchemy import UniqueConstraint, inspect

from app.db.models import Base
from app.db.repository import engine
from app.testing.models import CheckResult


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
            model_type = str(col.type).lower()
            if model_type.split("(")[0] not in db_type:
                ok = False
                details.append(f"{table_name}.{col_name} type mismatch model={model_type} db={db_type}")
            if bool(col.nullable) != bool(db_col["nullable"]):
                ok = False
                details.append(
                    f"{table_name}.{col_name} nullable mismatch model={col.nullable} db={db_col['nullable']}"
                )

        for col_name in db_columns:
            if col_name not in model_columns:
                ok = False
                details.append(f"{table_name}.{col_name} extra in database")

        msg = "schema valid" if ok else "schema drift detected"
        results.append(CheckResult(name=f"schema {table_name}", ok=ok, message=msg, details=details))
    return results


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
