"""Typed helpers for reading DuckDB query results."""

from typing import Any, cast

import duckdb
from pandas import DataFrame

Row = dict[str, Any]


def scalar(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> Any:
    """First column of the first row. Raises if the query returns no rows."""
    row = con.execute(sql, params).fetchone()
    if row is None:
        raise RuntimeError(f"query returned no rows: {sql}")
    return row[0]


def records(df: DataFrame) -> list[Row]:
    """DataFrame rows as dicts keyed by column name."""
    return cast(list[Row], df.to_dict("records"))
