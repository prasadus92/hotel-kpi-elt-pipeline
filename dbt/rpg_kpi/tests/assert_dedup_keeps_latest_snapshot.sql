-- The kept snapshot must carry the greatest updated_at among valid snapshots
-- for that reservation. Guards the core "last valid one" rule on real data.
with raw_max as (
    select
        hotel_id,
        reservation_id,
        max(updated_at) as max_updated_at
    from {{ ref('stg_reservations') }}
    where is_valid
    group by hotel_id, reservation_id
)

select
    kept.hotel_id,
    kept.reservation_id
from {{ ref('int_reservations_deduped') }} as kept
inner join raw_max
    on
        kept.hotel_id = raw_max.hotel_id
        and kept.reservation_id = raw_max.reservation_id
where kept.updated_at <> raw_max.max_updated_at
