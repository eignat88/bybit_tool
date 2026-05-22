from __future__ import annotations

from unittest.mock import patch

from app.testing.db_validation import validate_db_objects, validate_db_schema


class _FakeInspector:
    def __init__(self) -> None:
        self._columns = {
            "id": {"name": "id", "type": "INTEGER", "nullable": False},
            "symbol": {"name": "symbol", "type": "VARCHAR(30)", "nullable": False},
            "market_type": {"name": "market_type", "type": "VARCHAR(10)", "nullable": False},
            "base_coin": {"name": "base_coin", "type": "VARCHAR(20)", "nullable": False},
            "quote_coin": {"name": "quote_coin", "type": "VARCHAR(20)", "nullable": False},
            "status": {"name": "status", "type": "VARCHAR(20)", "nullable": False},
            "tick_size": {"name": "tick_size", "type": "FLOAT", "nullable": False},
            "qty_step": {"name": "qty_step", "type": "FLOAT", "nullable": False},
            "min_order_qty": {"name": "min_order_qty", "type": "FLOAT", "nullable": False},
            "launch_time": {"name": "launch_time", "type": "DATETIME", "nullable": True},
            "updated_at": {"name": "updated_at", "type": "DATETIME", "nullable": False},
        }

    def has_table(self, _table: str) -> bool:
        return True

    def get_columns(self, table: str):
        if table == "symbols":
            return list(self._columns.values())
        return []

    def get_indexes(self, table: str):
        if table == "symbols":
            return [{"name": "ix_symbols_symbol"}, {"name": "ix_symbols_market_type"}]
        return []

    def get_unique_constraints(self, table: str):
        if table == "symbols":
            return [{"name": "symbols_symbol_market_type_key", "column_names": ["symbol", "market_type"]}]
        return []


def test_schema_and_object_validation_agree_for_equivalent_unique_constraint() -> None:
    fake = _FakeInspector()
    with patch("app.testing.schema_inspection.inspect", return_value=fake):
        schema_results = {r.name: r.ok for r in validate_db_schema() if r.name == "schema symbols"}
        object_results = {r.name: r.ok for r in validate_db_objects() if r.name == "db-check symbols"}

    assert schema_results["schema symbols"] is True
    assert object_results["db-check symbols"] is True
