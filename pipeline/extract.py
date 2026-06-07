"""EL step: load the raw the PMS JSON into DuckDB.

Design choice (ELT, not ETL): we land the data essentially untouched. Every
field is read as text and the nested ``stay_dates`` array is preserved as a
LIST of STRUCTs. No validation, casting, or business logic happens here; that
is the transform layer's job (dbt models). This keeps extraction dumb and
replayable, and means the raw landing table is a faithful copy of the source.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

# Explicit schema-on-read: read EVERYTHING as VARCHAR. The PMS sends numbers as
# strings ("117.5") and may send malformed values; casting/validation belongs in
# the transform layer, so we refuse to let the reader coerce or reject anything.
_STAY_DATE_STRUCT = (
    "STRUCT("
    "start_date VARCHAR, "
    "end_date VARCHAR, "
    "room_type_id VARCHAR, "
    "room_type_name VARCHAR, "
    "room_revenue_gross_amount VARCHAR, "
    "room_revenue_net_amount VARCHAR, "
    "fnb_gross_amount VARCHAR, "
    "fnb_net_amount VARCHAR"
    ")"
)

_RESERVATION_STRUCT = (
    "STRUCT("
    "hotel_id VARCHAR, "
    "reservation_id VARCHAR, "
    "status VARCHAR, "
    "arrival_date VARCHAR, "
    "departure_date VARCHAR, "
    "created_at VARCHAR, "
    "updated_at VARCHAR, "
    f"stay_dates {_STAY_DATE_STRUCT}[]"
    ")"
)


def load_raw(json_path: str | Path, duckdb_path: str | Path) -> int:
    """Load the reservations JSON into ``raw.raw_reservations`` in DuckDB.

    Returns the number of raw reservation rows loaded.
    """
    json_path = Path(json_path).resolve()
    duckdb_path = Path(duckdb_path).resolve()
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    if not json_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {json_path}")

    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        # The top-level document is {"data": [ <reservation>, ... ]}. We declare
        # the column type explicitly and UNNEST the array into one row each.
        con.execute(
            f"""
            CREATE OR REPLACE TABLE raw.raw_reservations AS
            SELECT res.*
            FROM (
                SELECT unnest(data) AS res
                FROM read_json(
                    ?,
                    columns = {{'data': '{_RESERVATION_STRUCT}[]'}},
                    maximum_object_size = 1000000000
                )
            );
            """,
            [str(json_path)],
        )
        (row_count,) = con.execute("SELECT count(*) FROM raw.raw_reservations;").fetchone()
    finally:
        con.close()

    return int(row_count)
