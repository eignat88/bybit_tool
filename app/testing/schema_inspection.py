from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import UniqueConstraint, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table


@dataclass(slots=True)
class SchemaSnapshot:
    has_table: bool
    columns: dict[str, dict[str, Any]]
    indexes_by_name: set[str]
    unique_by_name: set[str]
    unique_signatures: set[tuple[str, ...]]


def _normalize_column_signature(columns: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    return tuple(columns or ())


def build_schema_snapshots(engine: Engine, tables: list[Table]) -> dict[str, SchemaSnapshot]:
    inspector = inspect(engine)
    snapshots: dict[str, SchemaSnapshot] = {}
    for table in tables:
        table_name = table.name
        has_table = inspector.has_table(table_name)
        if not has_table:
            snapshots[table_name] = SchemaSnapshot(False, {}, set(), set(), set())
            continue

        db_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
        db_indexes = {idx["name"] for idx in inspector.get_indexes(table_name) if idx.get("name")}
        db_uq_meta = inspector.get_unique_constraints(table_name)
        db_uq_names = {c["name"] for c in db_uq_meta if c.get("name")}
        db_uq_signatures = {_normalize_column_signature(c.get("column_names")) for c in db_uq_meta}
        snapshots[table_name] = SchemaSnapshot(
            has_table=True,
            columns=db_columns,
            indexes_by_name=db_indexes,
            unique_by_name=db_uq_names,
            unique_signatures=db_uq_signatures,
        )
    return snapshots


def model_unique_constraints(table: Table) -> tuple[set[str], set[tuple[str, ...]]]:
    named = {c.name for c in table.constraints if isinstance(c, UniqueConstraint) and c.name}
    signatures = {
        _normalize_column_signature([col.name for col in c.columns])
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
    }
    return named, signatures
