-- Staging: the unified reservation feed across every PMS source.
--
-- Each source is normalized by its own adapter (stg_pms_native, stg_pms_nordic,
-- stg_pms_cloud) onto one shared contract: typed reservation-level columns, a
-- `stay_dates` LIST(STRUCT(...)) of text line items using shared field names,
-- and a reservation-level `is_valid` flag. This model simply unions them, so
-- every downstream model (dedup, night explosion, KPIs) is source-agnostic.
--
-- Adding a PMS is therefore a tidy, local change: write one stg_pms_<name>
-- adapter that emits these columns, then add it to the union below. Nothing
-- downstream changes.

with unioned as (

    select * from {{ ref('stg_pms_native') }}
    union all by name
    select * from {{ ref('stg_pms_nordic') }}
    union all by name
    select * from {{ ref('stg_pms_cloud') }}

)

select
    source_system,
    hotel_id,
    reservation_id,
    status,
    arrival_date,
    departure_date,
    created_at,
    updated_at,
    stay_dates,
    is_valid
from unioned
