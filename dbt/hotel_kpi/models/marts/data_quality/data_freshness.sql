-- Mart (data quality): freshness of each source, per source and per property.
--
-- A revenue-management data team needs to know, before trusting a KPI, how old
-- the numbers behind it are. This model turns the load manifest and the event
-- watermarks into first-class freshness metrics measured against a fixed as-of
-- watermark (so the build stays deterministic):
--
--   * load_lag_hours  -> as_of - loaded_at (how long since the last batch loaded)
--   * event_lag_hours -> as_of - max_event_at (how long since the newest event)
--   * is_stale        -> load_lag_hours > freshness_sla_hours (SLA breach)
--
-- Grain: one row per (source_system, hotel_id), where hotel_id = '__all__' is
-- the source-level rollup. `is_stale` is what the freshness SLA test asserts on.

with watermarks as (

    select * from {{ ref('int_source_event_watermarks') }}

),

manifest as (

    select * from {{ ref('stg_source_load_manifest') }}

),

as_of as (

    select cast('{{ var("as_of_watermark") }}' as timestamp) as as_of_ts

),

joined as (

    select
        w.source_system,
        w.hotel_id,
        w.reservations,
        w.max_event_at,
        m.loaded_at,
        m.freshness_sla_hours,
        a.as_of_ts
    from watermarks as w
    inner join manifest as m on w.source_system = m.source_system
    cross join as_of as a

)

select
    source_system,
    hotel_id,
    reservations,
    loaded_at,
    max_event_at,
    as_of_ts as as_of,
    freshness_sla_hours,
    -- Hours between the last load and the as-of watermark: the authoritative
    -- freshness signal the SLA keys off.
    round(date_diff('minute', loaded_at, as_of_ts) / 60.0, 2) as load_lag_hours,
    -- Event-side staleness: hours since the newest event, floored at 0 (a feed
    -- whose newest event is beyond the watermark is not behind on events).
    greatest(round(date_diff('minute', max_event_at, as_of_ts) / 60.0, 2), 0)
        as event_lag_hours,
    -- SLA breach: the load is older than the source's freshness SLA allows.
    (date_diff('minute', loaded_at, as_of_ts) / 60.0 > freshness_sla_hours)
        as is_stale
from joined
