-- Intermediate: collapse reservation event history to ONE current row per
-- reservation.  ***This is the step most commonly gotten wrong.***
--
-- The PMS re-sends a full snapshot of a reservation every time it changes, so
-- the raw feed contains many rows per reservation_id (up to 17 in this dataset).
-- The contract says: "When multiple entries exist for the same reservation ...
-- the reservation that counts is the last valid one." We therefore:
--
--   1. keep only events that pass reservation-level validation (is_valid), then
--   2. pick the event with the greatest updated_at per (hotel_id, reservation_id).
--
-- Doing this BEFORE exploding nights / summing revenue is what prevents the
-- double-counting that inflates occupancy and revenue. The latest snapshot also
-- carries the current status (e.g. a confirmed booking later cancelled resolves
-- to `cancelled`), which is what the occupancy vs revenue rules key off.

with valid_events as (

    select *
    from {{ ref('stg_reservations') }}
    where is_valid

),

ranked as (

    select
        *,
        row_number() over (
            partition by hotel_id, reservation_id
            order by
                updated_at desc,
                -- deterministic tie-break when identical snapshots share an
                -- updated_at, so the build is reproducible run-to-run.
                md5(cast(stay_dates as varchar)) desc
        ) as rn
    from valid_events

)

select
    source_system,
    hotel_id,
    reservation_id,
    status,
    arrival_date,
    departure_date,
    created_at,
    updated_at,
    stay_dates,
    (status <> 'cancelled') as counts_for_occupancy
from ranked
where rn = 1
