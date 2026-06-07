#!/usr/bin/env python3
"""RoomPriceGenie daily-KPI pipeline — CLI entrypoint.

Runs the three pipeline stages end to end for a given hotel and date range:

    1. EXTRACT/LOAD  (pipeline.extract)  raw PMS JSON  -> DuckDB raw table
    2. TRANSFORM     (dbt)               raw           -> staging/intermediate/marts
    3. EXPORT/SERVE  (pipeline.export)   kpi_report    -> contract CSV

Example
-------
    python run_pipeline.py --hotel-id 1035 --from-date 2026-05-01 --to-date 2026-05-31

All three arguments are required-with-defaults so the headline deliverable
(hotel 1035, May 2026) reproduces with a bare ``python run_pipeline.py``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline import export, extract

REPO_ROOT = Path(__file__).resolve().parent
DBT_PROJECT_DIR = REPO_ROOT / "dbt" / "rpg_kpi"
DEFAULT_INPUT = REPO_ROOT / "data" / "reservations_data.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output"
DUCKDB_PATH = DBT_PROJECT_DIR / "rpg.duckdb"


def _valid_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse surfaces the message
        raise argparse.ArgumentTypeError(
            f"'{value}' is not a valid YYYY-MM-DD date"
        ) from exc
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate daily hotel performance KPIs (CSV) from PMS data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--hotel-id", default="1035", help="Hotel to report on.")
    parser.add_argument(
        "--from-date", default="2026-05-01", type=_valid_date,
        help="Start of the date range (inclusive), YYYY-MM-DD.",
    )
    parser.add_argument(
        "--to-date", default="2026-05-31", type=_valid_date,
        help="End of the date range (inclusive), YYYY-MM-DD.",
    )
    parser.add_argument(
        "--input", default=str(DEFAULT_INPUT), type=Path,
        help="Path to the raw reservations JSON.",
    )
    parser.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path,
        help="Directory to write the CSV into.",
    )
    args = parser.parse_args(argv)

    if args.from_date > args.to_date:
        parser.error("--from-date must not be after --to-date")
    return args


def run_dbt(hotel_id: str, from_date: str, to_date: str) -> None:
    """Invoke dbt to build seeds + models for the requested parameters."""
    dbt_bin = shutil.which("dbt")
    if dbt_bin is None:
        raise RuntimeError(
            "dbt executable not found on PATH. Activate the virtualenv "
            "(source .venv/bin/activate) or `pip install dbt-duckdb`."
        )

    dbt_vars = json.dumps(
        {"hotel_id": hotel_id, "from_date": from_date, "to_date": to_date}
    )
    env = {**os.environ, "RPG_DUCKDB_PATH": str(DUCKDB_PATH)}

    cmd = [
        dbt_bin, "build",
        "--project-dir", str(DBT_PROJECT_DIR),
        "--profiles-dir", str(DBT_PROJECT_DIR),
        "--vars", dbt_vars,
    ]
    print(f"$ {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True, env=env)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print("=" * 70)
    print(f"RoomPriceGenie KPI pipeline | hotel={args.hotel_id} "
          f"range={args.from_date}..{args.to_date}")
    print("=" * 70)

    # 1) EXTRACT / LOAD
    print("\n[1/3] Extract+Load: raw JSON -> DuckDB ...")
    n = extract.load_raw(args.input, DUCKDB_PATH)
    print(f"      loaded {n:,} raw reservation rows into raw.raw_reservations")

    # 2) TRANSFORM
    print("\n[2/3] Transform: dbt build (seed + models) ...")
    run_dbt(args.hotel_id, args.from_date, args.to_date)

    # 3) EXPORT / SERVE
    print("\n[3/3] Export: kpi_report -> CSV ...")
    out_path = export.write_csv(
        DUCKDB_PATH, args.hotel_id, args.from_date, args.to_date, args.output_dir
    )
    print(f"      wrote {out_path}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
