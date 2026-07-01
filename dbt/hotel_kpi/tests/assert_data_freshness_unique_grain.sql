-- data_freshness must have exactly one row per (source_system, hotel_id),
-- including the '__all__' source rollup rows.
select
    source_system,
    hotel_id,
    count(*) as n
from {{ ref('data_freshness') }}
group by source_system, hotel_id
having count(*) > 1
