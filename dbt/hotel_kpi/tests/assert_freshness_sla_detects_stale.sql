-- Freshness SLA logic check: is_stale must agree with the raw comparison of
-- load lag against the source's SLA, for every freshness row. This proves the
-- SLA flag is computed correctly (rather than asserting a specific source is
-- stale, which would be brittle). A source is stale iff its load lag exceeds
-- its SLA.

select
    source_system,
    hotel_id,
    load_lag_hours,
    freshness_sla_hours,
    is_stale
from {{ ref('data_freshness') }}
where is_stale <> (load_lag_hours > freshness_sla_hours)
