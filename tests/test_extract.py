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
            from raw.raw_reservations
            where reservation_id = '1'
            """
        ).fetchone()
    finally:
        con.close()

    assert room_net == "100"
    assert n_stay == 1
