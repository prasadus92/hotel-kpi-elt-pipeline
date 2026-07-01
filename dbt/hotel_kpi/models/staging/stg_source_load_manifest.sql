-- Staging: the source load manifest (freshness, load side).
--
-- One row per PMS source recording when its latest batch was loaded into the
-- warehouse and the freshness SLA it is held to. This is the load-side input to
-- data_freshness; the event-side input (how recent the newest event is) comes
-- from the reservation feeds themselves.

with source as (

    select * from {{ ref('source_load_manifest') }}

)

select
    cast(source_system as varchar) as source_system,
    cast(loaded_at as timestamp) as loaded_at,
    cast(freshness_sla_hours as integer) as freshness_sla_hours
from source
where
    source_system is not null
    and loaded_at is not null
    and freshness_sla_hours is not null
