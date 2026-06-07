-- ADR must be 0 exactly when there are no occupied rooms, regardless of revenue.
select *
from {{ ref('fct_daily_kpis') }}
where
    occupied_rooms = 0
    and adr <> 0
