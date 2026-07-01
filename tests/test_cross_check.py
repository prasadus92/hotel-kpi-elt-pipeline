"""Tests for the reconciliation helpers and its KPI computation.

The compute() test doubles as a focused, fast check of the core business rules
(deduplication, the cancelled-status asymmetry, the inventory filter, night
explosion, and the date spine) on a tiny hand-built dataset.
"""

import csv
import datetime as dt
import json
from decimal import Decimal

import cross_check

# --- small helpers -----------------------------------------------------------


def test_parse_date():
    assert cross_check.parse_date("2026-05-01") == dt.date(2026, 5, 1)
    assert cross_check.parse_date("not-a-date") is None
    assert cross_check.parse_date(None) is None


def test_parse_ts_accepts_known_formats():
    assert cross_check.parse_ts("2026-05-01 10:00:00.500") is not None
    assert cross_check.parse_ts("2026-05-01T10:00:00") is not None
    assert cross_check.parse_ts("garbage") is None


def test_to_decimal():
    assert cross_check.to_decimal("1.50") == Decimal("1.50")
    assert cross_check.to_decimal(None) is None
    assert cross_check.to_decimal("abc") is None


def test_round_half_up():
    assert cross_check.q2(Decimal("2.345")) == Decimal("2.35")
    assert cross_check.q2(Decimal("2.344")) == Decimal("2.34")
    assert cross_check.q0(Decimal("0.5")) == 1
    assert cross_check.q0(Decimal("1.5")) == 2
    assert cross_check.q0(Decimal("2.4")) == 2


# --- compute() on a tiny synthetic dataset -----------------------------------


def _stay(start, end, room_type, net, gross, fnb_net="", fnb_gross=""):
    return {
        "start_date": start,
        "end_date": end,
        "room_type_id": room_type,
        "room_type_name": "Test Room",
        "room_revenue_gross_amount": gross,
        "room_revenue_net_amount": net,
        "fnb_gross_amount": fnb_gross,
        "fnb_net_amount": fnb_net,
    }


def _reservation(res_id, status, arrival, departure, updated_at, stay_dates):
    return {
        "hotel_id": "H",
        "reservation_id": res_id,
        "status": status,
        "arrival_date": arrival,
        "departure_date": departure,
        "created_at": "2026-03-01 09:00:00.000",
        "updated_at": updated_at,
        "stay_dates": stay_dates,
    }


def _write_inputs(tmp_path):
    reservations = {
        "data": [
            # Reservation 1: two snapshots; the later (checked_out) must win.
            _reservation(
                "1",
                "confirmed",
                "2026-05-01",
                "2026-05-03",
                "2026-04-01 09:00:00.000",
                [_stay("2026-05-01", "2026-05-02", "LD", "100", "120", "10", "12")],
            ),
            _reservation(
                "1",
                "checked_out",
                "2026-05-01",
                "2026-05-03",
                "2026-04-02 09:00:00.000",
                [_stay("2026-05-01", "2026-05-02", "LD", "100", "120", "10", "12")],
            ),
            # Reservation 2: cancelled -> revenue counts, occupancy does not.
            _reservation(
                "2",
                "cancelled",
                "2026-05-01",
                "2026-05-02",
                "2026-04-01 09:00:00.000",
                [_stay("2026-05-01", "2026-05-01", "LD", "50", "60")],
            ),
            # Reservation 3: room type not in inventory -> ignored entirely.
            _reservation(
                "3",
                "confirmed",
                "2026-05-01",
                "2026-05-02",
                "2026-04-01 09:00:00.000",
                [_stay("2026-05-01", "2026-05-01", "XX", "999", "999")],
            ),
            # Reservation 4: invalid status -> discarded.
            _reservation(
                "4",
                "bogus",
                "2026-05-01",
                "2026-05-02",
                "2026-04-01 09:00:00.000",
                [_stay("2026-05-01", "2026-05-01", "LD", "70", "80")],
            ),
        ]
    }
    json_path = tmp_path / "reservations.json"
    json_path.write_text(json.dumps(reservations))

    inv_path = tmp_path / "inventory.csv"
    with open(inv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hotel_id", "room_type_id", "quantity"])
        w.writerow(["H", "LD", "4"])
    return json_path, inv_path


def test_compute_applies_all_core_rules(tmp_path):
    json_path, inv_path = _write_inputs(tmp_path)
    result = cross_check.compute(json_path, inv_path, "H", dt.date(2026, 5, 1), dt.date(2026, 5, 3))

    # 2026-05-01: occupied = reservation 1 only (2 cancelled, 3 filtered, 4 invalid).
    # revenue = 110 (res 1: 100 + 10 fnb) + 50 (cancelled res 2) = 160. occ = 1/4.
    assert result["2026-05-01"] == ("25.00", "160.00", "160")
    # 2026-05-02: only reservation 1 (range explosion to the second night).
    assert result["2026-05-02"] == ("25.00", "110.00", "110")
    # 2026-05-03: checkout day, no occupied night -> zero-filled by the spine.
    assert result["2026-05-03"] == ("0.00", "0.00", "0")


# --- per-source normalizers (mirror the stg_pms_* adapters) -------------------


def test_load_nordic_normalizes_to_internal_shape(tmp_path):
    csv_path = tmp_path / "nordic.csv"
    csv_path.write_text(
        "property_code,booking_ref,stay_status,checkin,checkout,stay_night,"
        "room_code,currency,room_gross_eur,room_vat_eur,board_gross_eur\n"
        # two nights of one booking -> one reservation, two stay_dates
        "2050,NB1,OUT,01.05.2026,03.05.2026,01.05.2026,STD,EUR,110.00,10.00,11.00\n"
        "2050,NB1,OUT,01.05.2026,03.05.2026,02.05.2026,STD,EUR,110.00,10.00,11.00\n"
        # a cancellation, its own reservation
        "2050,NB2,CXL,05.05.2026,06.05.2026,05.05.2026,SUP,EUR,190.00,17.27,22.80\n"
    )
    recs = cross_check.load_nordic(csv_path)
    by_id = {r["reservation_id"]: r for r in recs}

    nb1 = by_id["NB1"]
    assert nb1["hotel_id"] == "2050"
    assert nb1["status"] == "checked_out"  # OUT -> checked_out
    assert nb1["arrival_date"] == "2026-05-01"
    assert nb1["departure_date"] == "2026-05-03"
    assert len(nb1["stay_dates"]) == 2
    # net = gross - vat = 110 - 10 = 100
    assert nb1["stay_dates"][0]["room_revenue_net_amount"] == "100.00"

    assert by_id["NB2"]["status"] == "cancelled"  # CXL -> cancelled


def test_load_cloud_normalizes_camelcase_and_status(tmp_path):
    json_path = tmp_path / "cloud.json"
    json_path.write_text(
        json.dumps(
            {
                "reservations": [
                    {
                        "propertyId": "3120",
                        "confirmationId": "9",
                        "reservationStatus": "checkedOut",
                        "arrival": "2026-05-01",
                        "departure": "2026-05-02",
                        "createdAt": "2026-04-01T09:00:00-05:00",
                        "modifiedAt": "2026-04-02T09:00:00-05:00",
                        "ratePlanCode": "ADV",
                        "nightlyRates": [
                            {
                                "roomCode": "K1",
                                "stayDate": "2026-05-01",
                                "ratePlan": "ADV",
                                "roomChargeGross": "200.00",
                                "roomChargeNet": "178.50",
                                "incidentalsGross": "20.00",
                                "incidentalsNet": "17.85",
                            }
                        ],
                    }
                ]
            }
        )
    )
    recs = cross_check.load_cloud(json_path)
    assert len(recs) == 1
    r = recs[0]
    assert r["hotel_id"] == "3120"
    assert r["reservation_id"] == "9"
    assert r["status"] == "checked_out"  # checkedOut -> checked_out
    assert r["updated_at"] == "2026-04-02 09:00:00"  # tz offset dropped
    assert r["stay_dates"][0]["room_type_id"] == "K1"
    assert r["stay_dates"][0]["room_revenue_net_amount"] == "178.50"
