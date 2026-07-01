-- Mart (data quality): availability / completeness of the KPI data per night.
--
-- Freshness answers "how recent is the data"; availability answers "is it all
-- there". For each property we expect a continuous run of nights (no calendar
-- holes) and, on each night, room-night coverage against the property's
-- capacity. This model detects both classes of gap:
--
--   * missing DAY   -> a night inside the property's active window with no row
--                      at all in fct_daily_kpis (the feed skipped that date).
--   * missing ROOMS -> capacity minus occupied_rooms (room-nights we hold no
--                      occupied reservation for; expected on a normal night, but
--                      the size of the gap is the signal).
--
-- availability_pct is night-level coverage: occupied_rooms / capacity * 100,
-- capped at 100 so an oversold night still reads as fully covered. Grain: one
-- row per (hotel_id, night) across each property's active window.

with fct as (

    select * from {{ ref('fct_daily_kpis') }}

),

capacity as (

    select * from {{ ref('int_hotel_capacity') }}

),

-- Each property's active window: the first and last night it has any activity.
-- The expected calendar is every night in between (inclusive), so any interior
-- night without a fact row is a genuine hole rather than an out-of-season date.
windows as (

    select
        hotel_id,
        min(night) as first_night,
        max(night) as last_night
    from fct
    group by hotel_id

),

-- One row per (hotel_id, night) across each property's active window. range()
-- is half-open, so step to (last_night + 1 day) to include the final night.
spine as (

    select
        w.hotel_id,
        cast(
            unnest(range(
                cast(w.first_night as timestamp),
                cast((w.last_night + interval '1 day') as timestamp),
                interval '1 day'
            )) as date
        ) as night
    from windows as w

)

select
    s.hotel_id,
    s.night,
    c.total_rooms as expected_room_nights,
    coalesce(f.occupied_rooms, 0) as occupied_rooms,
    -- The night has no fact row at all: a missing day in the feed.
    (f.night is null) as is_missing_day,
    -- Room-nights with no occupied reservation on a covered night.
    greatest(c.total_rooms - coalesce(f.occupied_rooms, 0), 0) as missing_room_nights,
    -- Coverage of capacity, capped at 100 so oversell does not read as >100%.
    least(
        round(coalesce(f.occupied_rooms, 0) * 100.0 / nullif(c.total_rooms, 0), 2),
        100.0
    ) as availability_pct
from spine as s
left join capacity as c on s.hotel_id = c.hotel_id
left join fct as f
    on
        s.hotel_id = f.hotel_id
        and s.night = f.night
