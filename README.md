# Daily Hotel Performance KPIs

A small but production-shaped data pipeline that turns raw PMS
reservation events into trustworthy daily performance KPIs (occupancy, net
revenue, ADR) and exports them as a CSV in the agreed contract format.

It is built as an **ELT pipeline**: a thin Python Extract/Load step lands the
raw feeds in **DuckDB**, **dbt** runs the Transform across layered models, and a
thin Python serve step exports the final CSV.

It ingests **three different PMS sources** that each arrive in their own shape
(nested JSON, flat CSV, camelCase JSON with different dates, currencies, status
codes, and room taxonomies) and normalizes all of them onto one KPI model
through a per-source adapter layer. See
[`docs/PMS_SOURCES.md`](docs/PMS_SOURCES.md).

> **New to this repo?** Start here, then read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
> for the design, [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the exact
> KPI rules and worked examples, [`docs/PMS_SOURCES.md`](docs/PMS_SOURCES.md)
> for the multi-source scenarios and the adapter pattern, and
> [`docs/DATA_QUALITY.md`](docs/DATA_QUALITY.md) for the freshness, availability,
> reconciliation, and market-blend signals.

---

## The deliverable

The required output (hotel `1035`, May 2026) is pre-generated and committed:

```
output/kpi_1035_2026_05_01_to_2026_05_31.csv
```

You do not need to run anything to see it. Everything below is for reproducing
it and understanding the design.

---

## Quickstart

Requirements: Python 3.10 or newer (built and verified on 3.11, 3.12 and 3.13).

```bash
# 1. Create an environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Run the pipeline (defaults to hotel 1035, May 2026)
python run_pipeline.py
# -> writes output/kpi_1035_2026_05_01_to_2026_05_31.csv
```

A `Makefile` wraps the common tasks:

```bash
make install     # create venv and install runtime + dev dependencies
make run         # run the pipeline with defaults
make test        # dbt build (incl. dbt tests) + pytest + reconciliation
make lint        # ruff + sqlfluff
make check       # lint + test (what CI runs)
```

### Running for any hotel or date range

The pipeline accepts `hotel_id`, `from_date`, and `to_date`:

```bash
python run_pipeline.py \
    --hotel-id 1036 \
    --from-date 2026-04-01 \
    --to-date   2026-04-30
# -> output/kpi_1036_2026_04_01_to_2026_04_30.csv
```

The same command works for every PMS source. Each run lands all three sources,
builds the unified model, and exports the requested property:

```bash
python run_pipeline.py --hotel-id 2050 --from-date 2026-05-01 --to-date 2026-05-31  # Nordic PMS
python run_pipeline.py --hotel-id 3120 --from-date 2026-05-01 --to-date 2026-05-31  # cloud PMS
```

| Property | PMS source | Notable traits |
| -------- | ---------- | -------------- |
| `1035`, `1036` | Native (nested JSON) | Snapshot revisions, cancelled-revenue asymmetry |
| `2050` | Nordic (flat CSV) | `DD.MM.YYYY`, gross EUR + VAT, no-shows |
| `3120`, `3121` | Cloud (camelCase JSON) | ISO-8601 tz, USD, rate plans, overbooking |

See [`docs/PMS_SOURCES.md`](docs/PMS_SOURCES.md) for the schema differences and
the adapter/normalization pattern.

| Argument        | Default                       | Meaning                                  |
| --------------- | ----------------------------- | ---------------------------------------- |
| `--hotel-id`    | `1035`                        | Hotel to report on                       |
| `--from-date`   | `2026-05-01`                  | Start of range (inclusive), `YYYY-MM-DD` |
| `--to-date`     | `2026-05-31`                  | End of range (inclusive), `YYYY-MM-DD`   |
| `--input`       | `data/reservations_data.json` | Raw PMS JSON                             |
| `--output-dir`  | `output/`                     | Where to write the CSV                   |

### Verifying correctness

An independent, dependency-free reimplementation recomputes the KPIs from the
raw JSON and compares them row by row with the pipeline's CSV:

```bash
python scripts/cross_check.py --csv output/kpi_1035_2026_05_01_to_2026_05_31.csv
# -> OK: independent reimplementation matches the pipeline output on every row.
```

---

## Architecture at a glance

Three stages, with a clear separation between *moving* data (Python) and
*transforming* data (SQL/dbt). Full detail in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```mermaid
flowchart LR
    A["native JSON"] -->|"EL"| RA[("raw.raw_pms_native")]
    B["Nordic CSV"] -->|"EL"| RB[("raw.raw_pms_nordic")]
    C["cloud JSON"] -->|"EL"| RC[("raw.raw_pms_cloud")]
    S["hotel_room_inventory.csv"] -->|"dbt seed"| SD[("DuckDB: seed")]

    subgraph dbt["Transform: dbt models on DuckDB"]
        RA --> AA["stg_pms_native"]
        RB --> AB["stg_pms_nordic"]
        RC --> AC["stg_pms_cloud"]
        AA --> ST1["stg_reservations (union)"]
        AB --> ST1
        AC --> ST1
        SD --> ST2["stg_hotel_inventory"]
        ST1 --> IN1["int_reservations_deduped"]
        IN1 --> IN2["int_reservation_nights"]
        ST2 --> IN2
        ST2 --> IN3["int_hotel_capacity"]
        IN2 --> M1["fct_daily_kpis"]
        IN3 --> M1
        M1 --> M2["kpi_report"]
    end

    M2 -->|"serve: pipeline/export.py"| OUT["kpi_&lt;hotel&gt;_&lt;from&gt;_to_&lt;to&gt;.csv"]
```

| Stage           | Code                  | Responsibility                                           |
| --------------- | --------------------- | ------------------------------------------------------- |
| Extract / Load  | `pipeline/extract.py` | Land each PMS source as text (schema-on-read) into its own raw table |
| Transform       | `dbt/hotel_kpi/`        | Normalize per source, union, deduplicate, explode, filter, aggregate |
| Serve / Export  | `pipeline/export.py`  | Copy the `kpi_report` mart to a contract-named CSV       |
| Orchestration   | `run_pipeline.py`     | Run the three stages and forward CLI args to dbt        |

---

## KPIs and the rules that matter

Output columns (sorted by `NIGHT_OF_STAY` descending), one row per night in the
requested range:

| Column                 | Definition                                                                 |
| ---------------------- | -------------------------------------------------------------------------- |
| `NIGHT_OF_STAY`        | The date (`YYYY-MM-DD`) the KPIs describe                                   |
| `OCCUPANCY_PERCENTAGE` | `occupied_rooms / hotel_capacity * 100`, 2 dp; can exceed 100 (overbooking)  |
| `TOTAL_NET_REVENUE`    | `room_net + fnb_net`, 2 dp                                                  |
| `ADR`                  | `total_net_revenue / occupied_rooms`, nearest integer; `0` if no rooms occupied |

Two rules decide whether the KPIs come out right or wrong. Both are covered by
[dbt unit tests](dbt/hotel_kpi/models) and the reconciliation script:

1. **Deduplicate before you aggregate.** The PMS re-sends a full snapshot every
   time a reservation changes, so `reservation_id` repeats in the raw feed (up to
   17 times here; 7,818 raw rows for hotel 1035 collapse to 3,468 real
   reservations). Only the latest valid snapshot per reservation is kept, and
   this happens *before* exploding nights or summing money.
2. **Occupancy and revenue use different status rules, by design.** Occupancy
   counts every status except `cancelled`; revenue includes every status,
   including `cancelled`. This asymmetry follows the KPI spec. In the
   May 2026 output, `2026-05-26` shows revenue of `1908.36` at `0.00` occupancy
   with `ADR = 0`: a night whose only bookings were cancelled.

The other rules (a reservation is one room, inventory-only room types, occupiable
nights `[arrival, departure - 1]`, two-grain validation) are documented in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

---

## Data-quality signals

Alongside the KPI fact sit the signals a revenue-management data team checks
before trusting a number: is the data recent, is it all there, and does it add
up. These models read from the KPI fact and never change the published
`kpi_report` output. Full detail (and a flow diagram) is in
[`docs/DATA_QUALITY.md`](docs/DATA_QUALITY.md).

| Model                    | Grain                    | What it answers                                                                  |
| ------------------------ | ------------------------ | -------------------------------------------------------------------------------- |
| `data_freshness`         | `(source_system, hotel_id)` | Load lag and event lag per source vs a freshness SLA; flags stale sources (`is_stale`) |
| `data_availability`      | `(hotel_id, night)`      | Missing days, missing room-nights, and an availability percentage against capacity |
| `reconciliation_report`  | `source_system` (+ total) | Independently recomputed source totals vs the unified fact, with a pass/fail verdict |
| `mart_kpi_with_market`   | `(hotel_id, night)`      | KPIs blended with an illustrative external comp-set rate index and local-events flag |

Freshness is measured against a fixed as-of watermark (not wall-clock `now()`),
so the whole build stays deterministic. Two synthetic reference feeds back these
models: `source_load_manifest.csv` (per-source load times and SLAs, one source
deliberately left stale) and `market_rate_index.csv` (a generic comp-set index).
Both are deterministic outputs of `make gen-data`.

---

## Quality, tests and CI

Tests and CI were optional for the original scope. They are included here, kept
deliberately lean, to show how the work is actually built and kept trustworthy.

- **dbt tests**: schema tests (`not_null`, `accepted_values`, uniqueness on the
  fact grain, relationships to inventory), singular tests for business
  invariants (no negative occupancy, ADR is 0 exactly when no rooms are
  occupied, the freshness SLA flag, availability bounds, and the reconciliation
  gate), and **dbt unit tests** that assert the dedup and KPI logic against
  small mocked inputs.
- **pytest** for the Python layer (validation helpers, rounding, filename
  convention, CLI argument handling) in `tests/`.
- **Reconciliation** (`scripts/cross_check.py`): a second, independent
  implementation that must agree with the pipeline on every row.
- **GitHub Actions** (`.github/workflows/ci.yml`): lint, run the full pipeline,
  `dbt build` (models + tests), pytest, reconciliation, and a regression check
  that the committed CSV still matches a freshly generated one.

Run the same checks locally with `make check`.

---

## Project structure

```
hotel-kpi-elt-pipeline/
├── run_pipeline.py              # CLI: EL -> dbt -> export
├── pipeline/
│   ├── extract.py               # EL: land each PMS source -> DuckDB (schema-on-read)
│   └── export.py                # serve: kpi_report -> contract CSV
├── dbt/hotel_kpi/
│   ├── dbt_project.yml
│   ├── profiles.yml             # local DuckDB profile
│   ├── seeds/                   # inventory, source load manifest, market rate index
│   ├── macros/                  # reservation_validity (shared adapter check)
│   ├── tests/                   # singular (business-invariant) tests
│   └── models/
│       ├── staging/             # stg_pms_* adapters, stg_reservations (union), inventory, manifest, market
│       ├── intermediate/        # dedup, nights, capacity, event watermarks, source control (+ unit tests)
│       └── marts/
│           ├── fct_daily_kpis, kpi_report (+ tests)
│           └── data_quality/    # freshness, availability, reconciliation, market blend
├── scripts/
│   ├── cross_check.py           # independent KPI reconciliation (per source)
│   └── generate_synthetic.py    # deterministic synthetic data generator (PMS feeds, manifest, market)
├── tests/                       # pytest suite for the Python layer
├── data/                        # sample inputs (committed for reproducibility)
├── output/                      # generated CSV deliverables
├── docs/
│   ├── ARCHITECTURE.md          # components, data flow, decisions, production
│   ├── METHODOLOGY.md           # exact KPI rules, validation, worked examples
│   ├── PMS_SOURCES.md           # multi-source scenarios and the adapter pattern
│   └── DATA_QUALITY.md          # freshness, availability, reconciliation, market blend
├── .github/workflows/ci.yml     # continuous integration
├── Makefile
├── pyproject.toml               # ruff + pytest config
├── .sqlfluff                    # SQL lint config (dbt templater)
├── requirements.txt             # runtime dependencies (pinned)
└── requirements-dev.txt         # lint + test dependencies
```

## From local to production

DuckDB and the file-based flow are deliberate development choices. The dbt model
layers, the ELT shape, and the contracts all port directly to a warehouse like
Snowflake with Dagster orchestration. The migration path and scaling notes (for
example handling millions of reservations per day, and the physical data layout:
partitioning, clustering keys, and indexing) are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#from-local-to-production).
