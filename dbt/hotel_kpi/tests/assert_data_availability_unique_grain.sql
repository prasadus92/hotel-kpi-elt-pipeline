-- data_availability must have exactly one row per (hotel_id, night).
select
    hotel_id,
    night,
    count(*) as n
from {{ ref('data_availability') }}
group by hotel_id, night
having count(*) > 1
