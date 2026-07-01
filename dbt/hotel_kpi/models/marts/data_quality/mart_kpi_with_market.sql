-- Mart: daily KPIs blended with the external market / comp-set signal.
--
-- Internal reservation data tells you how the property performed; the market
-- index tells you what the surrounding comp set was doing on the same night.
-- Blending them is the everyday revenue-management question: did we win or lose
-- share, and was a soft night the property's fault or the whole market's?
--
-- This model left joins the illustrative market_rate_index onto fct_daily_kpis
-- so the market signal is optional: nights with internal KPIs but no market row
-- still appear (market columns null). rate_vs_market_index expresses the
-- property's own ADR against the comp-set index (100 = at market), giving a
-- simple rate-position read. Grain: one row per (hotel_id, night).

with fct as (

    select * from {{ ref('fct_daily_kpis') }}

),

market as (

    select * from {{ ref('stg_market_rate_index') }}

)

select
    f.hotel_id,
    f.night,
    f.occupancy_percentage,
    f.total_net_revenue,
    f.adr,
    m.comp_rate_index,
    m.local_event,
    coalesce(m.has_local_event, false) as has_local_event,
    -- The property's ADR indexed to the comp set (100 = priced at market). Only
    -- meaningful when both an ADR and a comp index are present.
    case
        when f.adr > 0 and m.comp_rate_index is not null
            then round(f.adr * 100.0 / m.comp_rate_index, 2)
    end as rate_vs_market_index
from fct as f
left join market as m
    on
        f.hotel_id = m.hotel_id
        and f.night = m.night
