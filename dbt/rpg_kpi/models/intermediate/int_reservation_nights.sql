-- Intermediate: explode each deduplicated reservation into one row per
-- occupied night, applying LINE-ITEM (stay-date) contract validation and the
-- inventory filter along the way.
--
-- Grain out: one row per (hotel_id, reservation_id, night).
--
-- A reservation object "represents only one room", so each night of a
-- reservation contributes at most ONE occupied room. We therefore reduce to
-- distinct nights per reservation (guarding against the contract violation
-- "each date should appear only once across all stay date objects").
--
-- Night model: a guest occupies the nights [arrival_date, departure_date - 1].
-- departure_date is checkout and is never an occupied night.

with deduped as (

    select * from {{ ref('int_reservations_deduped') }}

),

-- 1 row per stay-date struct, with text fields cast to typed values.
line_items as (

    select
        hotel_id,
        reservation_id,
        status,
        counts_for_occupancy,
        arrival_date,
        departure_date,
        unnest(stay_dates) as sd
    from deduped

),

casted_line_items as (

    select
        hotel_id,
        reservation_id,
        status,
        counts_for_occupancy,
        arrival_date,
        departure_date,
        sd.room_type_id,
        try_cast(sd.start_date as date) as sd_start,
        try_cast(sd.end_date as date) as sd_end,
        try_cast(sd.room_revenue_gross_amount as double) as room_gross,
        try_cast(sd.room_revenue_net_amount as double) as room_net,
        try_cast(nullif(sd.fnb_gross_amount, '') as double) as fnb_gross,
        try_cast(nullif(sd.fnb_net_amount, '') as double) as fnb_net,
        sd.room_revenue_net_amount as room_net_raw,
        sd.room_revenue_gross_amount as room_gross_raw,
        sd.fnb_net_amount as fnb_net_raw,
        sd.fnb_gross_amount as fnb_gross_raw
    from line_items

),

-- LINE-ITEM validation: discard any individual stay-date entry that violates
-- the contract (the rest of the reservation is unaffected).
valid_line_items as (

    select *
    from casted_line_items
    where room_type_id is not null
    -- required revenue fields present and numeric
    and room_net_raw is not null and room_net is not null
    and room_gross_raw is not null and room_gross is not null
    -- optional fnb: if present it must be numeric
    and (fnb_net_raw is null or fnb_net_raw = '' or fnb_net is not null)
    and (fnb_gross_raw is null or fnb_gross_raw = '' or fnb_gross is not null)
    -- valid date range, ordered, and inside the reservation period
    and sd_start is not null and sd_end is not null
    and sd_start <= sd_end
    and sd_start >= arrival_date
    and sd_end <= departure_date

),

-- Keep only room types that count for the hotel (inventory filter).
inventory_filtered as (

    select li.*
    from valid_line_items as li
    inner join {{ ref('stg_hotel_inventory') }} as inv
        on
            li.hotel_id = inv.hotel_id
            and li.room_type_id = inv.room_type_id

),

-- Expand each stay-date range into individual nights. range() is half-open, so
-- stepping to (sd_end + 1 day) makes the expansion inclusive of sd_end.
nights as (

    select
        hotel_id,
        reservation_id,
        status,
        counts_for_occupancy,
        arrival_date,
        departure_date,
        room_type_id,
        coalesce(room_net, 0) + coalesce(fnb_net, 0) as total_net_revenue,
        cast(
            unnest(range(
                cast(sd_start as timestamp),
                cast((sd_end + interval '1 day') as timestamp),
                interval '1 day'
            )) as date
        ) as night
    from inventory_filtered

),

-- Keep only genuinely occupiable nights: [arrival_date, departure_date - 1].
occupiable as (

    select *
    from nights
    where
        night >= arrival_date
        and night < departure_date

),

-- A reservation is one room: collapse to distinct nights. If the same night
-- somehow appears twice (contract violation), keep one deterministically.
distinct_nights as (

    select
        hotel_id,
        reservation_id,
        night,
        status,
        counts_for_occupancy,
        room_type_id,
        total_net_revenue,
        row_number() over (
            partition by hotel_id, reservation_id, night
            order by total_net_revenue desc, room_type_id asc
        ) as rn
    from occupiable

)

select
    hotel_id,
    reservation_id,
    night,
    status,
    counts_for_occupancy,
    room_type_id,
    total_net_revenue
from distinct_nights
where rn = 1
