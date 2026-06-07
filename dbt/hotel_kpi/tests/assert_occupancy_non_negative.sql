-- Occupancy percentage can exceed 100 (overbooking) but is never negative.
select *
from {{ ref('fct_daily_kpis') }}
where occupancy_percentage < 0
