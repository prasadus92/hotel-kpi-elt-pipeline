"""Tests for the data-quality synthetic generators.

These cover the load manifest and market-rate-index generators added for the
freshness / availability / reconciliation / market signals. They assert the
data is deterministic (byte-identical across runs) and that the deliberate
signals it carries are present, so downstream freshness and market models have
something real to work with.
"""

import datetime as dt

import generate_synthetic as gen


def test_load_manifest_is_deterministic():
    assert gen.generate_load_manifest() == gen.generate_load_manifest()


def test_load_manifest_shape_and_stale_source():
    rows = gen.generate_load_manifest()
    by_source = {r["source_system"]: r for r in rows}
    assert set(by_source) == {"native", "nordic", "cloud"}

    watermark = dt.datetime.fromisoformat(gen.AS_OF_WATERMARK)
    for source, (hours_before, sla_hours) in gen.SOURCE_LOAD_MANIFEST.items():
        row = by_source[source]
        loaded_at = dt.datetime.strptime(row["loaded_at"], "%Y-%m-%d %H:%M:%S")
        lag_hours = (watermark - loaded_at).total_seconds() / 3600
        assert lag_hours == hours_before
        assert int(row["freshness_sla_hours"]) == sla_hours

    # The cloud source is deliberately stale so the freshness SLA test has a
    # real breach to catch; the others are within SLA.
    cloud_lag, cloud_sla = gen.SOURCE_LOAD_MANIFEST["cloud"]
    assert cloud_lag > cloud_sla
    for source in ("native", "nordic"):
        lag, sla = gen.SOURCE_LOAD_MANIFEST[source]
        assert lag <= sla


def test_market_index_is_deterministic():
    assert gen.generate_market_index() == gen.generate_market_index()


def test_market_index_covers_every_property_night():
    rows = gen.generate_market_index()
    hotels = {r["hotel_id"] for r in rows}
    # One row per property per night in May 2026 (31 nights).
    assert len(rows) == len(hotels) * 31
    nights = {r["night"] for r in rows if r["hotel_id"] == next(iter(hotels))}
    assert len(nights) == 31

    # Event nights carry a label and a lifted index over a plain weekday.
    event_rows = [r for r in rows if r["local_event"]]
    assert event_rows, "expected some local-event nights"
    for r in event_rows:
        assert int(r["comp_rate_index"]) > 100
