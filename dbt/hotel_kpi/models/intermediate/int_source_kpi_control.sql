-- Intermediate: an INDEPENDENT per-source recomputation of the KPI totals.
--
-- This is the control side of reconciliation. It re-derives occupied
-- room-nights and net revenue straight from int_reservations_deduped by its own
-- night explosion, deliberately NOT reusing int_reservation_nights, so that
-- agreeing with the published fact is real evidence rather than a tautology.
-- Because it starts from the deduped, source-tagged reservations it can report
-- per source_system, which fct_daily_kpis (source-agnostic) cannot.
--
-- The KPI rules it mirrors: occupancy counts every status except cancelled;
-- revenue counts every status; a reservation is one room, so each night
-- contributes at most one occupied room; only in-inventory room types count.
-- Grain out: one row per source_system.

with deduped as (

    select * from {{ ref('int_reservations_deduped') }}

),

inventory as (

    select * from {{ ref('stg_hotel_inventory') }}

),

line_items as (

    select
        source_system,
        hotel_id,
        reservation_id,
        counts_for_occupancy,
        arrival_date,
        departure_date,
        unnest(stay_dates) as sd
    from deduped

),

casted as (

    select
        source_system,
        hotel_id,
        reservation_id,
        counts_for_occupancy,
        arrival_date,
        departure_date,
        sd.room_type_id,
        try_cast(sd.start_date as date) as sd_start,
        try_cast(sd.end_date as date) as sd_end,
        try_cast(sd.room_net as double) as room_net,
        try_cast(sd.room_gross as double) as room_gross,
        try_cast(nullif(sd.fnb_net, '') as double) as fnb_net,
        try_cast(nullif(sd.fnb_gross, '') as double) as fnb_gross,
        sd.room_net as room_net_raw,
        sd.room_gross as room_gross_raw,
        sd.fnb_net as fnb_net_raw,
        sd.fnb_gross as fnb_gross_raw
    from line_items

),

-- Same line-item validation the KPI path applies, restated independently.
valid as (

    select *
    from casted
    where
        room_type_id is not null
        and room_net_raw is not null and room_net is not null
        and room_gross_raw is not null and room_gross is not null
        and (fnb_net_raw is null or fnb_net_raw = '' or fnb_net is not null)
        and (fnb_gross_raw is null or fnb_gross_raw = '' or fnb_gross is not null)
        and sd_start is not null and sd_end is not null
        and sd_start <= sd_end
        and sd_start >= arrival_date
        and sd_end <= departure_date

),

in_inventory as (

    select v.*
    from valid as v
    inner join inventory as inv
        on v.hotel_id = inv.hotel_id and v.room_type_id = inv.room_type_id

),

nights as (

    select
        source_system,
        hotel_id,
        reservation_id,
        room_type_id,
        counts_for_occupancy,
        arrival_date,
        departure_date,
        coalesce(room_net, 0) + coalesce(fnb_net, 0) as total_net_revenue,
        cast(
            unnest(range(
                cast(sd_start as timestamp),
                cast((sd_end + interval '1 day') as timestamp),
                interval '1 day'
            )) as date
        ) as night
    from in_inventory

),

occupiable as (

    select *
    from nights
    where night >= arrival_date and night < departure_date

),

-- One room per reservation-night, deterministic tie-break, same as the KPI path.
distinct_nights as (

    select
        source_system,
        hotel_id,
        reservation_id,
        night,
        counts_for_occupancy,
        total_net_revenue,
        row_number() over (
            partition by hotel_id, reservation_id, night
            order by total_net_revenue desc, room_type_id asc
        ) as rn
    from occupiable

)

select
    source_system,
    sum(case when counts_for_occupancy then 1 else 0 end) as occupied_room_nights,
    round(sum(total_net_revenue), 2) as total_net_revenue,
    count(*) as room_nights
from distinct_nights
where rn = 1
group by source_system
