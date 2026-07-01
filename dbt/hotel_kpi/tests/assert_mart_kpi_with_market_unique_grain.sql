-- mart_kpi_with_market must have exactly one row per (hotel_id, night); the
-- market join must not fan out.
select
    hotel_id,
    night,
    count(*) as n
from {{ ref('mart_kpi_with_market') }}
group by hotel_id, night
having count(*) > 1
