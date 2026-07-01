#!/usr/bin/env python3
"""Generate the synthetic PMS datasets for the extra source scenarios.

The repo ships three PMS sources that each land in their own shape (see
`docs/PMS_SOURCES.md`). Source A (the "native" PMS) is the original
`data/reservations_data.json` and is not generated here. This script generates
the other two so the multi-source pipeline has plausible, messy, realistic data
to normalize:

  * Nordic PMS  -> data/pms_nordic_stays.csv   (flat, one row per room-night,
                   DD.MM.YYYY dates, gross-inclusive EUR, VAT column, short
                   status codes, no-shows, cancellations, a group rate).
  * Cloud PMS   -> data/pms_cloud_reservations.json (camelCase JSON, ISO-8601
                   timestamps with timezone offsets, USD, rate plans and
                   discounts, partial refunds, late check-outs, overbooking,
                   snapshot revisions).

Everything is seeded so re-running produces byte-identical files. The generator
owns the "truth" (the actual stays); the messiness (revisions, cancellations,
refunds) is layered on top deterministically so the normalized output is
predictable and the KPIs are reproducible.

Run:  python scripts/generate_synthetic.py
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# One fixed seed for the whole run keeps both files deterministic.
SEED = 20260501

# --- Nordic PMS (property 2050) -------------------------------------------
# A European PMS. Rooms are priced gross (VAT included) in EUR. The feed is a
# flat export: one row per room per night, already exploded, with local
# DD.MM.YYYY dates and its own short status vocabulary.
NORDIC_HOTEL = "2050"
NORDIC_VAT_RATE = Decimal("0.10")  # 10% VAT baked into the gross price
# Nordic room codes -> the shared room_type_id the inventory uses.
NORDIC_ROOMS = {
    # code: (shared_room_type_id, rooms_in_inventory, nightly_gross_eur)
    "STD": ("STD", 8, Decimal("140")),
    "SUP": ("SUP", 5, Decimal("190")),
    "STE": ("STE", 2, Decimal("320")),
}
# A retired room code that must be filtered out by the inventory join.
NORDIC_RETIRED_ROOM = "OLD"

# --- Cloud PMS (properties 3120, 3121) ------------------------------------
# A US cloud PMS serving a two-property group. Nested JSON, camelCase, USD,
# rate plans with discounts (so gross != net by more than tax), ISO-8601
# timestamps with timezone offsets, and revision snapshots.
CLOUD_HOTELS = ["3120", "3121"]
CLOUD_TZ = "-05:00"  # US Eastern-ish offset, kept fixed for determinism
CLOUD_ROOMS = {
    # code: (shared_room_type_id, rooms_in_inventory, nightly_rack_usd)
    "K1": ("KING", 10, Decimal("210")),
    "Q2": ("QUEEN", 12, Decimal("180")),
    "STE": ("SUITE", 3, Decimal("360")),
}
CLOUD_RATE_PLANS = {
    # plan_code: discount off the rack rate
    "BAR": Decimal("0.00"),  # best available rate, no discount
    "ADV": Decimal("0.15"),  # advance purchase, 15% off
    "CORP": Decimal("0.20"),  # negotiated corporate rate
}


def q2(x: Decimal) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _daterange(start: dt.date, nights: int) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range(nights)]


# ---------------------------------------------------------------------------
# Nordic PMS generator
# ---------------------------------------------------------------------------
def generate_nordic(rng: random.Random) -> list[dict]:
    """One row per room-night. Dates are DD.MM.YYYY, money is gross EUR + VAT.

    Status vocabulary: OK (in house / confirmed), OUT (checked out),
    CXL (cancelled), NOSHOW (guest never arrived). No-shows and cancellations
    still carry revenue (the property keeps the charge), which exercises the
    revenue-includes-everything / occupancy-excludes-cancelled rules.
    """
    rows: list[dict] = []
    booking_seq = 40000
    # Spread bookings across April-June 2026 so the May report is well covered.
    season_start = dt.date(2026, 4, 1)
    for _ in range(420):
        booking_seq += rng.randint(1, 3)
        booking_ref = f"NB{booking_seq}"
        code = rng.choice([*NORDIC_ROOMS.keys(), NORDIC_RETIRED_ROOM])
        arrival = season_start + dt.timedelta(days=rng.randint(0, 88))
        nights = rng.choice([1, 1, 2, 2, 3, 4, 7])
        # Status distribution: mostly OK/OUT, some cancellations and no-shows.
        status = rng.choices(
            ["OUT", "OK", "CXL", "NOSHOW"],
            weights=[55, 25, 12, 8],
            k=1,
        )[0]
        if code == NORDIC_RETIRED_ROOM:
            gross = Decimal("150")
        else:
            _, _, base_gross = NORDIC_ROOMS[code]
            # +/- 20% seasonal wobble, rounded to whole euros.
            factor = Decimal(rng.randint(80, 120)) / Decimal(100)
            gross = (base_gross * factor).quantize(Decimal("1"), ROUND_HALF_UP)
        # Group booking: a block of the same reference over consecutive nights
        # at a flat negotiated rate. Modelled implicitly by the per-night rows.
        for night in _daterange(arrival, nights):
            net = q2(gross / (Decimal("1") + NORDIC_VAT_RATE))
            vat = q2(gross - net)
            rows.append(
                {
                    "property_code": NORDIC_HOTEL,
                    "booking_ref": booking_ref,
                    "stay_status": status,
                    "checkin": arrival.strftime("%d.%m.%Y"),
                    "checkout": (arrival + dt.timedelta(days=nights)).strftime("%d.%m.%Y"),
                    "stay_night": night.strftime("%d.%m.%Y"),
                    "room_code": code,
                    "currency": "EUR",
                    "room_gross_eur": f"{gross:.2f}",
                    "room_vat_eur": f"{vat:.2f}",
                    "board_gross_eur": f"{q2(gross * Decimal('0.12')):.2f}",  # breakfast/board
                }
            )
    # Deterministic order: by booking then night.
    rows.sort(key=lambda r: (r["booking_ref"], r["stay_night"]))
    return rows


def write_nordic(rows: list[dict], path: Path) -> None:
    fields = [
        "property_code",
        "booking_ref",
        "stay_status",
        "checkin",
        "checkout",
        "stay_night",
        "room_code",
        "currency",
        "room_gross_eur",
        "room_vat_eur",
        "board_gross_eur",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Cloud PMS generator
# ---------------------------------------------------------------------------
def _iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S") + CLOUD_TZ


def _cloud_snapshot(res, rng, revision, eff_nights, refunded):
    """Build one cloud revision snapshot from a reservation context dict.

    Kept module-level (rather than a closure over the generation loop) so each
    snapshot binds its own values and the generator stays easy to reason about.
    """
    tax_rate = Decimal("0.12")
    line_items = []
    for i, night in enumerate(_daterange(res["arrival"], eff_nights)):
        net = res["net_nightly"]
        if refunded and i == eff_nights - 1:
            # last night partially refunded (half back)
            net = q2(res["net_nightly"] / Decimal("2"))
        gross = q2(net * (Decimal("1") + tax_rate))
        fnb_net = q2(net * Decimal("0.10"))
        fnb_gross = q2(fnb_net * (Decimal("1") + tax_rate))
        line_items.append(
            {
                "roomCode": res["code"],
                "stayDate": night.isoformat(),
                "ratePlan": res["plan"],
                "roomChargeGross": f"{gross:.2f}",
                "roomChargeNet": f"{net:.2f}",
                "incidentalsGross": f"{fnb_gross:.2f}",
                "incidentalsNet": f"{fnb_net:.2f}",
            }
        )
    updated = res["created"] + dt.timedelta(days=revision, hours=rng.randint(1, 20))
    return {
        "propertyId": res["hotel"],
        "confirmationId": str(res["res_seq"]),
        "reservationStatus": res["status"],
        "arrival": res["arrival"].isoformat(),
        "departure": (res["arrival"] + dt.timedelta(days=eff_nights)).isoformat(),
        "createdAt": _iso(res["created"]),
        "modifiedAt": _iso(updated),
        "ratePlanCode": res["plan"],
        "nightlyRates": line_items,
    }


def generate_cloud(rng: random.Random) -> list[dict]:
    """Nested reservations with rate plans, discounts, refunds and revisions.

    Each reservation carries `nights` (already net of tax, quoted per night),
    a rate plan discount, and 1..N revision snapshots (the PMS re-emits the
    whole object on every change, exactly like the native source). Some
    reservations are partially refunded (revenue reduced), some are late
    check-outs (an extra night added on revision), and the group is deliberately
    oversold on a few nights to produce occupancy above 100 percent.
    """
    reservations: list[dict] = []
    res_seq = 700000
    season_start = dt.date(2026, 4, 1)
    for _ in range(360):
        res_seq += rng.randint(1, 4)
        hotel = rng.choice(CLOUD_HOTELS)
        code = rng.choice(list(CLOUD_ROOMS.keys()))
        _, _, rack = CLOUD_ROOMS[code]
        plan = rng.choice(list(CLOUD_RATE_PLANS.keys()))
        discount = CLOUD_RATE_PLANS[plan]
        arrival = season_start + dt.timedelta(days=rng.randint(0, 88))
        nights = rng.choice([1, 1, 2, 2, 3, 5])
        status = rng.choices(
            ["checkedOut", "confirmed", "cancelled", "checkedIn"],
            weights=[52, 28, 12, 8],
            k=1,
        )[0]
        created = dt.datetime.combine(
            arrival - dt.timedelta(days=rng.randint(3, 40)),
            dt.time(rng.randint(8, 20), rng.randint(0, 59), rng.randint(0, 59)),
        )

        # Base per-night net (rack minus discount), gross is net * (1 + tax).
        net_nightly = q2(rack * (Decimal("1") - discount))
        late_checkout = rng.random() < 0.12  # adds a night on a later revision
        partial_refund = status == "checkedOut" and rng.random() < 0.10

        res_ctx = {
            "hotel": hotel,
            "res_seq": res_seq,
            "status": status,
            "arrival": arrival,
            "created": created,
            "code": code,
            "plan": plan,
            "net_nightly": net_nightly,
        }

        # Revision history: at least one snapshot; late check-outs and refunds
        # add a later, higher-updated_at snapshot that must win the dedup.
        snapshots = [_cloud_snapshot(res_ctx, rng, 0, nights, refunded=False)]
        eff_nights = nights
        if late_checkout:
            eff_nights = nights + 1
            snapshots.append(_cloud_snapshot(res_ctx, rng, 2, eff_nights, refunded=False))
        if partial_refund:
            snapshots.append(_cloud_snapshot(res_ctx, rng, 4, eff_nights, refunded=True))
        # A few plain duplicate re-sends with no change, to exercise dedup.
        if rng.random() < 0.4:
            snapshots.insert(1, _cloud_snapshot(res_ctx, rng, 1, eff_nights, refunded=False))
        reservations.extend(snapshots)

    # Deliberate oversell: clone a handful of confirmed reservations onto one
    # shared peak night at property 3120 so occupancy exceeds 100 percent.
    peak = dt.date(2026, 5, 14)
    for k in range(30):
        res_seq += 1
        net = q2(CLOUD_ROOMS["Q2"][2])
        gross = q2(net * Decimal("1.12"))
        reservations.append(
            {
                "propertyId": "3120",
                "confirmationId": str(res_seq),
                "reservationStatus": "confirmed",
                "arrival": peak.isoformat(),
                "departure": (peak + dt.timedelta(days=1)).isoformat(),
                "createdAt": _iso(dt.datetime(2026, 4, 20, 9, k, 0)),
                "modifiedAt": _iso(dt.datetime(2026, 4, 25, 9, k, 0)),
                "ratePlanCode": "BAR",
                "nightlyRates": [
                    {
                        "roomCode": "Q2",
                        "stayDate": peak.isoformat(),
                        "ratePlan": "BAR",
                        "roomChargeGross": f"{gross:.2f}",
                        "roomChargeNet": f"{net:.2f}",
                        "incidentalsGross": "0.00",
                        "incidentalsNet": "0.00",
                    }
                ],
            }
        )

    reservations.sort(key=lambda r: (r["propertyId"], r["confirmationId"], r["modifiedAt"]))
    return reservations


def write_cloud(reservations: list[dict], path: Path) -> None:
    with path.open("w") as fh:
        json.dump({"reservations": reservations}, fh, indent=2)
        fh.write("\n")


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    nordic_rows = generate_nordic(random.Random(SEED))
    write_nordic(nordic_rows, DATA_DIR / "pms_nordic_stays.csv")
    print(f"wrote data/pms_nordic_stays.csv ({len(nordic_rows)} room-night rows)")

    cloud_res = generate_cloud(random.Random(SEED + 1))
    write_cloud(cloud_res, DATA_DIR / "pms_cloud_reservations.json")
    print(f"wrote data/pms_cloud_reservations.json ({len(cloud_res)} reservation snapshots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
