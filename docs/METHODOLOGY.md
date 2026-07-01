# Methodology

This document defines exactly how each KPI is computed, how invalid data is
handled, and the assumptions behind the implementation. It is the reference for
"why is this number what it is".

## Inputs

- Three PMS sources, each in its own shape. Every source is normalized onto one
  shared reservation contract by a per-source adapter before any KPI logic runs,
  so the rules below apply identically regardless of source. The sources, their
  schema differences, and the adapter pattern are documented in
  [`PMS_SOURCES.md`](PMS_SOURCES.md).
  - `data/reservations_data.json` (native PMS): one object per reservation event,
    where a reservation represents a single room. The same `reservation_id` can
    appear many times because the PMS re-sends a full snapshot whenever a
    reservation changes.
  - `data/pms_nordic_stays.csv` (Nordic PMS): a flat, pre-exploded CSV.
  - `data/pms_cloud_reservations.json` (cloud PMS): nested camelCase JSON.
- `data/hotel_room_inventory.csv`: the room types and quantities that count for
  each hotel. This is the authoritative list of room types and the source of each
  hotel's capacity.

## Output contract

One row per night in the requested date range, sorted by `NIGHT_OF_STAY`
descending. Every night in range is present, with zeros where there is no data.

| Column                 | Type    | Definition                                                                     |
| ---------------------- | ------- | ------------------------------------------------------------------------------ |
| `NIGHT_OF_STAY`        | date    | The night the KPIs describe, `YYYY-MM-DD`                                       |
| `OCCUPANCY_PERCENTAGE` | 2 dp    | `occupied_rooms / hotel_capacity * 100`; may exceed 100 due to overbooking      |
| `TOTAL_NET_REVENUE`    | 2 dp    | `room_revenue_net + fnb_net` summed over the night                              |
| `ADR`                  | integer | `total_net_revenue / occupied_rooms`, nearest integer; `0` if no rooms occupied |

## Processing order

The order of operations is the most important part of the methodology. Two of
these steps are where the pipeline is commonly gotten wrong.

1. **Reservation-level validation.** Discard whole reservation events that
   violate the contract (see Validation below).
2. **Deduplication.** For each `reservation_id`, keep only the latest valid
   snapshot (greatest `updated_at`). This is "the last valid one" per the KPI spec.
3. **Explode to nights.** Expand each stay-date range into individual nights.
4. **Line-item validation and inventory filter.** Discard individual stay-date
   entries that violate the contract, and keep only room types present in the
   hotel's inventory.
5. **Reduce to one room-night per reservation per night.** A reservation is a
   single room, so it occupies a given night at most once.
6. **Aggregate per night** into occupancy, revenue, and ADR.
7. **Apply the date spine** for the requested range, filling missing nights with
   zeros, and format and sort.

Deduplicating (step 2) must happen before exploding and aggregating (steps 3 to
6). Summing all snapshots, or deduplicating after the explode, inflates both
occupancy and revenue.

### Why deduplication matters here

For hotel 1035, the raw feed has 7,818 reservation events but only 3,469 distinct
reservation ids, and one reservation appears 17 times. After dropping the single
invalid reservation, 3,468 reservations remain. The latest snapshot also carries
the current status, so a booking that was confirmed and later cancelled correctly
resolves to `cancelled`, which then drives the occupancy and revenue rules below.

## KPI definitions in detail

### Capacity (the occupancy denominator)

Capacity for a hotel is the sum of `quantity` across all of that hotel's room
types in the inventory. For hotel 1035 this is `LD(5) + GS(1) + LS(4) + SG(2) +
SU(2) = 14` rooms.

### Occupied rooms

The count of rooms occupied on a night, including every status **except**
`cancelled`. Because a reservation is one room and is reduced to distinct nights,
this is the number of non-cancelled reservations occupying that night (restricted
to inventory room types).

### Occupancy percentage

`round(occupied_rooms / capacity * 100, 2)`. It can exceed 100 percent when a
hotel is overbooked. For example, on `2026-05-15` hotel 1035 has 16 occupied
rooms against a capacity of 14, giving `114.29`.

### Total net revenue

`round(sum(room_revenue_net + fnb_net), 2)` over the night, including **every**
status, cancelled bookings included. F&B net revenue is optional in the contract;
when absent it is treated as zero.

### ADR (average daily rate)

`round(total_net_revenue / occupied_rooms)` to the nearest integer, or `0` when
no rooms are occupied. The division uses the unrounded revenue sum. ADR therefore
divides revenue-including-cancelled by rooms-excluding-cancelled, which follows
directly from the two rules above.

### The cancelled-status asymmetry

The KPI spec draws a deliberate distinction: occupancy uses "any status except
cancelled", while revenue uses "any status". This is implemented literally.

The asymmetry is material, not a corner case. For hotel 1035 in May 2026,
cancelled reservations account for about 14.3 percent of total net revenue
(roughly 4,871 of 33,978). It is implemented as written rather than tidied up,
and the consequence is visible in the output: see the worked example for
`2026-05-26` below.

## Validation rules

Validation happens at two grains so that a single bad line item does not discard
a whole reservation, and a single bad reservation does not discard the feed.

### Reservation level (`stg_reservations`, drops the whole event)

- `hotel_id` and `reservation_id` are present.
- `status` is one of `confirmed`, `cancelled`, `checked_in`, `checked_out`.
- `arrival_date` and `departure_date` parse as dates and `departure > arrival`.
- `created_at` and `updated_at` parse as timestamps (`updated_at` drives dedup).
- There is at least one stay-date entry.

### Line-item level (`int_reservation_nights`, drops just that entry)

- `room_type_id` is present.
- Required revenue amounts (`room_revenue_gross_amount`,
  `room_revenue_net_amount`) are present and parse as numbers.
- Optional F&B amounts, if present and non-empty, parse as numbers.
- `start_date` and `end_date` parse, with `start_date <= end_date`, and the range
  lies inside the reservation period (`start_date >= arrival_date` and
  `end_date <= departure_date`).

### Inventory filter

Only reservations for room types present in `hotel_room_inventory.csv` for the
hotel count toward any KPI. Room types that no longer exist, or that the owner
excludes, are ignored.

### What the rules catch in the sample data (hotel 1035)

| Issue                                       | Count            | Action                  |
| ------------------------------------------- | ---------------- | ----------------------- |
| Typo'd status `chcked_outs`                 | 1                | reservation discarded   |
| `departure_date <= arrival_date`            | 1                | reservation discarded   |
| Room type not in inventory (`AD`, `null`)   | 241 line items   | line items dropped      |
| Stay-date outside the reservation period    | 1                | line item dropped       |
| Duplicate reservation snapshots             | 4,350 events     | collapsed to the latest |

## Night model

A guest occupies the nights `[arrival_date, departure_date - 1]`. The
`departure_date` is the checkout day and is never an occupied night. Stay-date
ranges (`start_date` to `end_date`) are expanded into individual nights and
clamped to this window. When the PMS groups consecutive identical nights into one
entry, the revenue figures are per night and are applied to each expanded night,
not divided across the range, as stated in the contract's grouping note.

## Rounding

All rounding uses round-half-up (round half away from zero, since all values are
non-negative). Occupancy and revenue are rounded to two decimal places. ADR is
rounded to the nearest integer. The independent reconciliation script uses Python
`Decimal` with `ROUND_HALF_UP` and matches the pipeline exactly.

## Worked examples (hotel 1035, May 2026)

| Night        | Occupied | Capacity | Occupancy | Revenue  | ADR | Note                                        |
| ------------ | -------- | -------- | --------- | -------- | --- | ------------------------------------------- |
| `2026-05-02` | 14       | 14       | `100.00`  | `3317.93`| 237 | Fully occupied                              |
| `2026-05-15` | 16       | 14       | `114.29`  | `3286.36`| 205 | Overbooked, occupancy above 100             |
| `2026-05-26` | 0        | 14       | `0.00`    | `1908.36`| 0   | Only cancelled bookings: revenue but no ADR |
| `2026-05-05` | 0        | 14       | `0.00`    | `0.00`   | 0   | No activity, zero-filled by the date spine  |

The `2026-05-26` row is the clearest demonstration of the cancelled-status
asymmetry: revenue is recorded because revenue includes all statuses, but
occupancy is zero because cancelled bookings do not occupy rooms, and ADR is zero
because there are no occupied rooms to divide by.

## Assumptions

- The cancelled-revenue asymmetry is intentional and implemented literally.
- "The last valid one" means the greatest `updated_at` among valid snapshots.
  Identical snapshots that share an `updated_at` are tie-broken deterministically;
  their data is identical, so the choice does not affect output.
- `departure_date` is the checkout day, so the last occupied night is
  `departure_date - 1`.
- Grouped stay-date ranges carry per-night revenue amounts.
- Capacity is the sum of inventory quantities for the hotel.
- All reservations for all hotels arrive in a single request, per the API
  stated simplification.
