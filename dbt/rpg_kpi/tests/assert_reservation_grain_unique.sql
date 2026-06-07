-- After deduplication there is at most one row per (hotel_id, reservation_id).
select
    hotel_id,
    reservation_id,
    count(*) as n
from {{ ref('int_reservations_deduped') }}
group by hotel_id, reservation_id
having count(*) > 1
