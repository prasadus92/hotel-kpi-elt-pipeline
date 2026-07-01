-- Intermediate: the newest EVENT time per source and per (source, property).
--
-- Freshness has two halves. The load side (when a batch landed) comes from the
-- manifest seed. The event side is here: the maximum updated_at observed in each
-- feed, i.e. how recent the newest reservation event actually is. Data can be
-- loaded promptly yet still be "stale" if the source itself stopped emitting, so
-- both halves matter.
--
-- Grain: one row per (source_system, hotel_id), plus a source-level rollup with
-- hotel_id = '__all__' so freshness can be reported per source and per property.

with deduped as (

    select
        source_system,
        hotel_id,
        updated_at
    from {{ ref('int_reservations_deduped') }}

),

per_property as (

    select
        source_system,
        hotel_id,
        max(updated_at) as max_event_at,
        count(*) as reservations
    from deduped
    group by source_system, hotel_id

),

per_source as (

    select
        source_system,
        '__all__' as hotel_id,
        max(updated_at) as max_event_at,
        count(*) as reservations
    from deduped
    group by source_system

)

select * from per_property
union all by name
select * from per_source
