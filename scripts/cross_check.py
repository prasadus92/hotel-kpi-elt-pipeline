#!/usr/bin/env python3
"""Independent reconciliation of the pipeline output.

This is a QA / data-reconciliation aid, not a unit-test suite. It recomputes the
KPIs from the raw JSON using a completely separate, dependency-free pure-Python
implementation of the contract rules, then compares the result row-by-row with
the CSV produced by the dbt/DuckDB pipeline.

The point is confidence: two independent implementations agreeing on every value
is strong evidence the KPI logic is correct. Run it after the pipeline:

    python run_pipeline.py
    python scripts/cross_check.py \
        --csv output/kpi_1035_2026_05_01_to_2026_05_31.csv \
        --hotel-id 1035 --from-date 2026-05-01 --to-date 2026-05-31

Exits 0 on a perfect match, 1 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_STATUS = {"confirmed", "cancelled", "checked_in", "checked_out"}


def parse_date(s):
    try:
        return dt.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def parse_ts(s):
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return dt.datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def to_decimal(s):
    if s is None:
        return None
    try:
        return Decimal(str(s))
    except Exception:
        return None


def q2(x):
    return Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP)


def q0(x):
    return int(Decimal(x).quantize(Decimal("1"), ROUND_HALF_UP))


def _load_inventory(inv_path):
    inventory = defaultdict(set)
    capacity = defaultdict(int)
    with open(inv_path) as inv_file:
        for row in csv.DictReader(inv_file):
            inventory[row["hotel_id"]].add(row["room_type_id"])
            capacity[row["hotel_id"]] += int(row["quantity"])
    return inventory, capacity


def load_native(json_path):
    """Native PMS: reservations are already in the internal shape."""
    with open(json_path) as json_file:
        return json.load(json_file)["data"]


def load_nordic(csv_path):
    """Nordic PMS -> internal reservation shape (mirrors stg_pms_nordic).

    Flat CSV, one row per room-night: parse DD.MM.YYYY, map the status codes,
    back VAT out of the gross prices, and regroup nights into one reservation
    each with a stay_dates list using the internal field names.
    """
    status_map = {
        "ok": "checked_in",
        "out": "checked_out",
        "cxl": "cancelled",
        "noshow": "confirmed",
    }
    by_ref = {}
    with open(csv_path) as fh:
        for row in csv.DictReader(fh):
            ref = row["booking_ref"]
            checkin = dt.datetime.strptime(row["checkin"], "%d.%m.%Y").date()
            checkout = dt.datetime.strptime(row["checkout"], "%d.%m.%Y").date()
            night = dt.datetime.strptime(row["stay_night"], "%d.%m.%Y").date()
            gross = to_decimal(row["room_gross_eur"])
            vat = to_decimal(row["room_vat_eur"])
            board_gross = to_decimal(row["board_gross_eur"])
            net = gross - vat
            board_net = q2(board_gross / Decimal("1.10"))
            rec = by_ref.setdefault(
                ref,
                {
                    "hotel_id": row["property_code"],
                    "reservation_id": ref,
                    "status": status_map.get(
                        row["stay_status"].strip().lower(), row["stay_status"]
                    ),
                    "arrival_date": checkin.isoformat(),
                    "departure_date": checkout.isoformat(),
                    "created_at": checkin.isoformat() + " 00:00:00",
                    "updated_at": checkin.isoformat() + " 00:00:00",
                    "stay_dates": [],
                },
            )
            rec["stay_dates"].append(
                {
                    "start_date": night.isoformat(),
                    "end_date": night.isoformat(),
                    "room_type_id": row["room_code"],
                    "room_revenue_gross_amount": f"{gross:.2f}",
                    "room_revenue_net_amount": f"{net:.2f}",
                    "fnb_gross_amount": f"{board_gross:.2f}",
                    "fnb_net_amount": f"{board_net:.2f}",
                }
            )
    return list(by_ref.values())


def load_cloud(json_path):
    """Cloud PMS -> internal reservation shape (mirrors stg_pms_cloud)."""
    status_map = {
        "checkedout": "checked_out",
        "checkedin": "checked_in",
        "confirmed": "confirmed",
        "cancelled": "cancelled",
    }
    with open(json_path) as fh:
        raw = json.load(fh)["reservations"]
    out = []
    for r in raw:
        out.append(
            {
                "hotel_id": r["propertyId"],
                "reservation_id": r["confirmationId"],
                "status": status_map.get(r["reservationStatus"].lower(), r["reservationStatus"]),
                "arrival_date": r["arrival"],
                "departure_date": r["departure"],
                # Drop the tz offset: only per-reservation ordering matters.
                "created_at": r["createdAt"][:19].replace("T", " "),
                "updated_at": r["modifiedAt"][:19].replace("T", " "),
                "stay_dates": [
                    {
                        "start_date": sd["stayDate"],
                        "end_date": sd["stayDate"],
                        "room_type_id": sd["roomCode"],
                        "room_revenue_gross_amount": sd["roomChargeGross"],
                        "room_revenue_net_amount": sd["roomChargeNet"],
                        "fnb_gross_amount": sd["incidentalsGross"],
                        "fnb_net_amount": sd["incidentalsNet"],
                    }
                    for sd in r["nightlyRates"]
                ],
            }
        )
    return out


def compute(json_path, inv_path, hotel_id, from_date, to_date, reservations=None):
    inventory, capacity = _load_inventory(inv_path)
    cap = capacity[hotel_id]

    if reservations is None:
        reservations = load_native(json_path)
    recs = [r for r in reservations if r.get("hotel_id") == hotel_id]

    # reservation-level validation
    valid = []
    for r in recs:
        status = (r.get("status") or "").strip().lower()
        a, d = parse_date(r.get("arrival_date")), parse_date(r.get("departure_date"))
        c, u = parse_ts(r.get("created_at") or ""), parse_ts(r.get("updated_at") or "")
        stay = r.get("stay_dates") or []
        if (
            r.get("hotel_id")
            and r.get("reservation_id")
            and status in VALID_STATUS
            and a
            and d
            and d > a
            and c
            and u
            and len(stay) > 0
        ):
            rr = dict(r, _a=a, _d=d, _u=u, status=status)
            valid.append(rr)

    # dedup -> latest updated_at per reservation (deterministic tie-break)
    best = {}
    for r in valid:
        k = (r["hotel_id"], r["reservation_id"])
        key = (r["_u"], hashlib.md5(str(r["stay_dates"]).encode()).hexdigest())
        if k not in best or key > best[k][0]:
            best[k] = (key, r)

    occ = defaultdict(set)  # night -> reservation ids occupying (non-cancelled)
    rev = defaultdict(Decimal)  # night -> total net revenue (all statuses)
    for _, r in best.values():
        a, d, cancelled = r["_a"], r["_d"], r["status"] == "cancelled"
        per_night = {}
        for sd in r["stay_dates"]:
            rt = sd.get("room_type_id")
            s, e = parse_date(sd.get("start_date")), parse_date(sd.get("end_date"))
            room_net = to_decimal(sd.get("room_revenue_net_amount"))
            room_gross = to_decimal(sd.get("room_revenue_gross_amount"))
            fnb_net_raw, fnb_gross_raw = sd.get("fnb_net_amount"), sd.get("fnb_gross_amount")
            fnb_net = to_decimal(fnb_net_raw) if fnb_net_raw not in (None, "") else Decimal(0)
            fnb_gross = to_decimal(fnb_gross_raw) if fnb_gross_raw not in (None, "") else Decimal(0)
            # line-item validation + inventory filter
            if rt is None or rt not in inventory[hotel_id]:
                continue
            if sd.get("room_revenue_net_amount") is None or room_net is None:
                continue
            if sd.get("room_revenue_gross_amount") is None or room_gross is None:
                continue
            if fnb_net_raw not in (None, "") and fnb_net is None:
                continue
            if fnb_gross_raw not in (None, "") and fnb_gross is None:
                continue
            if not s or not e or s > e or s < a or e > d:
                continue
            total = room_net + fnb_net
            cur = s
            while cur <= e:
                # occupiable nights only, keeping one row per night deterministically
                if a <= cur < d and (cur not in per_night or (total, rt) > per_night[cur]):
                    per_night[cur] = (total, rt)
                cur += dt.timedelta(days=1)
        for night, (total, _rt) in per_night.items():
            rev[night] += total
            if not cancelled:
                occ[night].add(r["reservation_id"])

    expected = {}
    n = from_date
    while n <= to_date:
        o = len(occ[n])
        revenue = rev[n]
        occ_pct = q2(Decimal(o) * 100 / cap) if cap else Decimal("0.00")
        adr = 0 if o == 0 else q0(revenue / o)
        expected[n.isoformat()] = (f"{occ_pct:.2f}", f"{q2(revenue):.2f}", str(adr))
        n += dt.timedelta(days=1)
    return expected


SOURCE_DEFAULTS = {
    "native": REPO_ROOT / "data" / "reservations_data.json",
    "nordic": REPO_ROOT / "data" / "pms_nordic_stays.csv",
    "cloud": REPO_ROOT / "data" / "pms_cloud_reservations.json",
}
SOURCE_LOADERS = {"native": load_native, "nordic": load_nordic, "cloud": load_cloud}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--hotel-id", default="1035")
    p.add_argument("--from-date", default="2026-05-01")
    p.add_argument("--to-date", default="2026-05-31")
    p.add_argument(
        "--source",
        choices=list(SOURCE_LOADERS),
        default="native",
        help="Which PMS source the CSV was built from (picks the normalizer).",
    )
    p.add_argument(
        "--input",
        default=None,
        help="Path to the raw source file (defaults per --source).",
    )
    p.add_argument("--inventory", default=str(REPO_ROOT / "data" / "hotel_room_inventory.csv"))
    args = p.parse_args(argv)

    input_path = Path(args.input) if args.input else SOURCE_DEFAULTS[args.source]
    reservations = SOURCE_LOADERS[args.source](input_path)

    expected = compute(
        input_path,
        args.inventory,
        args.hotel_id,
        dt.date.fromisoformat(args.from_date),
        dt.date.fromisoformat(args.to_date),
        reservations=reservations,
    )

    produced = {}
    with open(args.csv) as f:
        for row in csv.DictReader(f):
            produced[row["NIGHT_OF_STAY"]] = (
                row["OCCUPANCY_PERCENTAGE"],
                row["TOTAL_NET_REVENUE"],
                row["ADR"],
            )

    mismatches = [
        (d, expected[d], produced.get(d)) for d in expected if expected[d] != produced.get(d)
    ]
    print(f"rows expected: {len(expected)} | rows in CSV: {len(produced)}")
    if mismatches or len(expected) != len(produced):
        print("MISMATCHES:")
        for night, independent, pipeline in mismatches:
            print(f"  date={night} independent={independent} pipeline={pipeline}")
        return 1
    print("OK: independent reimplementation matches the pipeline output on every row.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
