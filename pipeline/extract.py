"""EL step: land each raw PMS source into DuckDB, untouched.

Design choice (ELT, not ETL): we land the data essentially untouched. Every
field is read as text and nested arrays are preserved as LISTs of STRUCTs. No
validation, casting, or business logic happens here; that is the transform
layer's job (the per-source dbt adapter models). This keeps extraction dumb and
replayable, and means each raw landing table is a faithful copy of its source.

Three sources land into three raw tables. Each has its own native shape, so each
gets its own reader. Normalizing them onto the shared reservation contract is a
transform concern, handled by the `stg_pms_*` adapter models.

  * raw.raw_pms_native  <- data/reservations_data.json      (nested JSON)
  * raw.raw_pms_nordic  <- data/pms_nordic_stays.csv        (flat CSV)
  * raw.raw_pms_cloud   <- data/pms_cloud_reservations.json (nested JSON)
"""

from __future__ import annotations

from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# --- Native PMS (source A) -------------------------------------------------
# Read EVERYTHING as VARCHAR. The PMS sends numbers as strings ("117.5") and may
# send malformed values; casting/validation belongs in the transform layer, so
# we refuse to let the reader coerce or reject anything.
_NATIVE_STAY_STRUCT = (
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
_NATIVE_RESERVATION_STRUCT = (
    "STRUCT("
    "hotel_id VARCHAR, "
    "reservation_id VARCHAR, "
    "status VARCHAR, "
    "arrival_date VARCHAR, "
    "departure_date VARCHAR, "
    "created_at VARCHAR, "
    "updated_at VARCHAR, "
    f"stay_dates {_NATIVE_STAY_STRUCT}[]"
    ")"
)

# --- Cloud PMS (source C) --------------------------------------------------
# camelCase keys, nested nightlyRates, ISO-8601 timestamps with tz offsets.
_CLOUD_RATE_STRUCT = (
    "STRUCT("
    "roomCode VARCHAR, "
    "stayDate VARCHAR, "
    "ratePlan VARCHAR, "
    "roomChargeGross VARCHAR, "
    "roomChargeNet VARCHAR, "
    "incidentalsGross VARCHAR, "
    "incidentalsNet VARCHAR"
    ")"
)
_CLOUD_RESERVATION_STRUCT = (
    "STRUCT("
    "propertyId VARCHAR, "
    "confirmationId VARCHAR, "
    "reservationStatus VARCHAR, "
    "arrival VARCHAR, "
    "departure VARCHAR, "
    "createdAt VARCHAR, "
    "modifiedAt VARCHAR, "
    "ratePlanCode VARCHAR, "
    f"nightlyRates {_CLOUD_RATE_STRUCT}[]"
    ")"
)


def _connect(duckdb_path: str | Path) -> duckdb.DuckDBPyConnection:
    duckdb_path = Path(duckdb_path).resolve()
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(duckdb_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    return con


def _load_native(con: duckdb.DuckDBPyConnection, json_path: Path) -> int:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw.raw_pms_native AS
        SELECT res.*
        FROM (
            SELECT unnest(data) AS res
            FROM read_json(
                ?,
                columns = {{'data': '{_NATIVE_RESERVATION_STRUCT}[]'}},
                maximum_object_size = 1000000000
            )
        );
        """,
        [str(json_path)],
    )
    (n,) = con.execute("SELECT count(*) FROM raw.raw_pms_native;").fetchone()
    return int(n)


def _load_nordic(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    # Flat CSV, every column as VARCHAR so date/number parsing stays downstream.
    con.execute(
        """
        CREATE OR REPLACE TABLE raw.raw_pms_nordic AS
        SELECT * FROM read_csv(?, header = true, all_varchar = true);
        """,
        [str(csv_path)],
    )
    (n,) = con.execute("SELECT count(*) FROM raw.raw_pms_nordic;").fetchone()
    return int(n)


def _load_cloud(con: duckdb.DuckDBPyConnection, json_path: Path) -> int:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw.raw_pms_cloud AS
        SELECT res.*
        FROM (
            SELECT unnest(reservations) AS res
            FROM read_json(
                ?,
                columns = {{'reservations': '{_CLOUD_RESERVATION_STRUCT}[]'}},
                maximum_object_size = 1000000000
            )
        );
        """,
        [str(json_path)],
    )
    (n,) = con.execute("SELECT count(*) FROM raw.raw_pms_cloud;").fetchone()
    return int(n)


def load_all(
    duckdb_path: str | Path,
    native_json: str | Path | None = None,
    nordic_csv: str | Path | None = None,
    cloud_json: str | Path | None = None,
) -> dict[str, int]:
    """Land every available PMS source into its own raw table.

    Missing optional sources are skipped (so a single-source run still works).
    Returns a dict of source name -> rows loaded.
    """
    native_json = Path(native_json or DATA_DIR / "reservations_data.json")
    nordic_csv = Path(nordic_csv or DATA_DIR / "pms_nordic_stays.csv")
    cloud_json = Path(cloud_json or DATA_DIR / "pms_cloud_reservations.json")

    if not native_json.exists():
        raise FileNotFoundError(f"Native PMS JSON not found: {native_json}")

    con = _connect(duckdb_path)
    loaded: dict[str, int] = {}
    try:
        loaded["native"] = _load_native(con, native_json.resolve())
        if nordic_csv.exists():
            loaded["nordic"] = _load_nordic(con, nordic_csv.resolve())
        if cloud_json.exists():
            loaded["cloud"] = _load_cloud(con, cloud_json.resolve())
    finally:
        con.close()
    return loaded


def load_raw(json_path: str | Path, duckdb_path: str | Path) -> int:
    """Backwards-compatible single-source loader.

    Loads only the native PMS JSON into `raw.raw_pms_native` and returns its row
    count. `load_all` is the multi-source entrypoint the pipeline uses.
    """
    return load_all(duckdb_path, native_json=json_path)["native"]
