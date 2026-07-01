-- Mart (data quality): reconciliation of source totals against the unified KPI.
--
-- The published fact (fct_daily_kpis) is source-agnostic. This report proves the
-- sources add up to it. int_source_kpi_control independently recomputes occupied
-- room-nights and net revenue per source; this model lays those side by side
-- with the unified fact totals and, for the grand total, asserts they agree
-- within a small tolerance.
--
-- Layout: one row per source_system with that source's contribution, then a
-- final RECONCILIATION row (source_system = '__total__') carrying the unified
-- fact totals, the summed-source totals, the absolute differences, and the
-- pass/fail verdict. The revenue tolerance absorbs floating-point rounding only;
-- a real discrepancy (dropped rows, double counting) breaks the check.

{% set revenue_tolerance = 0.01 %}

with control as (

    select * from {{ ref('int_source_kpi_control') }}

),

fct as (

    select
        sum(occupied_rooms) as occupied_room_nights,
        round(sum(total_net_revenue), 2) as total_net_revenue
    from {{ ref('fct_daily_kpis') }}

),

source_totals as (

    select
        sum(occupied_room_nights) as occupied_room_nights,
        round(sum(total_net_revenue), 2) as total_net_revenue
    from control

),

-- Per-source contribution rows.
per_source as (

    select
        source_system,
        occupied_room_nights,
        total_net_revenue,
        cast(null as bigint) as fct_occupied_room_nights,
        cast(null as double) as fct_total_net_revenue,
        cast(null as double) as occupied_room_nights_diff,
        cast(null as double) as total_net_revenue_diff,
        cast(null as boolean) as reconciled
    from control

),

-- The reconciliation total row: sources vs the unified fact.
total_row as (

    select
        '__total__' as source_system,
        s.occupied_room_nights,
        s.total_net_revenue,
        f.occupied_room_nights as fct_occupied_room_nights,
        f.total_net_revenue as fct_total_net_revenue,
        abs(s.occupied_room_nights - f.occupied_room_nights)
            as occupied_room_nights_diff,
        abs(s.total_net_revenue - f.total_net_revenue) as total_net_revenue_diff,
        (
            s.occupied_room_nights = f.occupied_room_nights
            and abs(s.total_net_revenue - f.total_net_revenue) <= {{ revenue_tolerance }}
        ) as reconciled
    from source_totals as s
    cross join fct as f

)

select * from per_source
union all by name
select * from total_row
