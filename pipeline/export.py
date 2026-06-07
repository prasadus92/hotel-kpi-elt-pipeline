"""Serve step: export the kpi_report mart to the contract CSV.

The transform (dbt) has already produced ``kpi_report`` for the requested hotel
and date range, formatted and sorted exactly per the contract. Here we simply
copy it to a file named per the required convention.
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def output_filename(hotel_id: str, from_date: str, to_date: str) -> str:
    """kpi_<hotel_id>_<yyyy>_<mm>_<dd>_to_<yyyy>_<mm>_<dd>.csv"""
    return (
        f"kpi_{hotel_id}_"
        f"{from_date.replace('-', '_')}_to_{to_date.replace('-', '_')}.csv"
    )


def write_csv(
    duckdb_path: str | Path,
    hotel_id: str,
    from_date: str,
    to_date: str,
    output_dir: str | Path,
) -> Path:
    """Copy kpi_report to a CSV and return the path written."""
    duckdb_path = Path(duckdb_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / output_filename(hotel_id, from_date, to_date)

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        con.execute(
            """
            COPY (SELECT * FROM main.kpi_report)
            TO ? (HEADER, DELIMITER ',');
            """,
            [str(out_path)],
        )
    finally:
        con.close()

    return out_path
