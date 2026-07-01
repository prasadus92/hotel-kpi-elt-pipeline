-- Staging: the external market / comp-set rate index (illustrative).
--
-- One row per (hotel_id, night): a generic nightly rate index for the local
-- comp set (100 = the property's own typical rate) plus a local-events flag.
-- This is the external market source blended with internal reservation data in
-- mart_kpi_with_market. It carries no real market data; it exists to show the
-- pattern of joining an outside signal onto the KPI model.

with source as (

    select * from {{ ref('market_rate_index') }}

)

select
    cast(hotel_id as varchar) as hotel_id,
    cast(night as date) as night,
    cast(comp_rate_index as integer) as comp_rate_index,
    -- Empty string in the seed means "no local event"; normalize to null.
    nullif(trim(local_event), '') as local_event,
    (nullif(trim(local_event), '') is not null) as has_local_event
from source
where
    hotel_id is not null
    and night is not null
    and comp_rate_index is not null
