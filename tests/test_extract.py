"""Test the Extract/Load step lands the raw JSON faithfully into DuckDB."""

import json

import duckdb

from pipeline import extract


def test_load_raw_lands_rows_and_preserves_nesting(tmp_path):
    reservations = {
        "data": [
            {
                "hotel_id": "H",
                "reservation_id": "1",
                "status": "confirmed",
                "arrival_date": "2026-05-01",
                "departure_date": "2026-05-02",
                "created_at": "2026-03-01 09:00:00.000",
                "updated_at": "2026-04-01 09:00:00.000",
                "stay_dates": [
                    {
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-01",
                        "room_type_id": "LD",
                        "room_type_name": "Luxury Double",
                        "room_revenue_gross_amount": "120",
                        "room_revenue_net_amount": "100",
                        "fnb_gross_amount": "12",
                        "fnb_net_amount": "10",
                    }
                ],
            },
            {
                "hotel_id": "H",
                "reservation_id": "2",
                "status": "cancelled",
                "arrival_date": "2026-05-01",
                "departure_date": "2026-05-02",
                "created_at": "2026-03-01 09:00:00.000",
                "updated_at": "2026-04-01 09:00:00.000",
                "stay_dates": [],
            },
        ]
    }
    json_path = tmp_path / "reservations.json"
    json_path.write_text(json.dumps(reservations))
    duckdb_path = tmp_path / "test.duckdb"

    count = extract.load_raw(json_path, duckdb_path)
    assert count == 2

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        # Amounts must remain text (schema-on-read); nesting must be preserved.
        room_net, n_stay = con.execute(
            """
            select
                stay_dates[1].room_revenue_net_amount,
                len(stay_dates)
            from raw.raw_pms_native
            where reservation_id = '1'
            """
        ).fetchone()
    finally:
        con.close()

    assert room_net == "100"
    assert n_stay == 1


def test_load_all_lands_each_available_source(tmp_path):
    # Native JSON (minimal).
    native = tmp_path / "native.json"
    native.write_text(json.dumps({"data": []}))
    # Nordic CSV (flat, one room-night row).
    nordic = tmp_path / "nordic.csv"
    nordic.write_text(
        "property_code,booking_ref,stay_status,checkin,checkout,stay_night,"
        "room_code,currency,room_gross_eur,room_vat_eur,board_gross_eur\n"
        "2050,NB1,OUT,01.05.2026,02.05.2026,01.05.2026,STD,EUR,140.00,12.73,16.80\n"
    )
    # Cloud JSON (nested, camelCase).
    cloud = tmp_path / "cloud.json"
    cloud.write_text(
        json.dumps(
            {
                "reservations": [
                    {
                        "propertyId": "3120",
                        "confirmationId": "1",
                        "reservationStatus": "checkedOut",
                        "arrival": "2026-05-01",
                        "departure": "2026-05-02",
                        "createdAt": "2026-04-01T09:00:00-05:00",
                        "modifiedAt": "2026-04-02T09:00:00-05:00",
                        "ratePlanCode": "BAR",
                        "nightlyRates": [
                            {
                                "roomCode": "K1",
                                "stayDate": "2026-05-01",
                                "ratePlan": "BAR",
                                "roomChargeGross": "235.20",
                                "roomChargeNet": "210.00",
                                "incidentalsGross": "0.00",
                                "incidentalsNet": "0.00",
                            }
                        ],
                    }
                ]
            }
        )
    )
    duckdb_path = tmp_path / "test.duckdb"

    loaded = extract.load_all(duckdb_path, native_json=native, nordic_csv=nordic, cloud_json=cloud)
    assert loaded == {"native": 0, "nordic": 1, "cloud": 1}

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        # Every value must still be text (schema-on-read) in each raw table.
        (nordic_gross,) = con.execute("select room_gross_eur from raw.raw_pms_nordic").fetchone()
        (cloud_code,) = con.execute(
            "select nightlyRates[1].roomCode from raw.raw_pms_cloud"
        ).fetchone()
    finally:
        con.close()

    assert nordic_gross == "140.00"
    assert cloud_code == "K1"


def test_load_all_skips_missing_optional_sources(tmp_path):
    native = tmp_path / "native.json"
    native.write_text(json.dumps({"data": []}))
    loaded = extract.load_all(
        tmp_path / "db.duckdb",
        native_json=native,
        nordic_csv=tmp_path / "does_not_exist.csv",
        cloud_json=tmp_path / "missing.json",
    )
    assert loaded == {"native": 0}
