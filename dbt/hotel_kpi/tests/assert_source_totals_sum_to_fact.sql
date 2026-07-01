-- Belt-and-braces reconciliation: independently re-sum the per-source rows of
-- the reconciliation report and confirm they match the unified fact totals
-- carried on the __total__ row. Fails if the per-source breakdown and the
-- reconciled grand total ever disagree.

with per_source as (

    select
        sum(occupied_room_nights) as occupied_room_nights,
        sum(total_net_revenue) as total_net_revenue
    from {{ ref('reconciliation_report') }}
    where source_system <> '__total__'

),

fact_totals as (

    select
        fct_occupied_room_nights,
        fct_total_net_revenue
    from {{ ref('reconciliation_report') }}
    where source_system = '__total__'

)

select *
from per_source as p
cross join fact_totals as f
where
    p.occupied_room_nights <> f.fct_occupied_room_nights
    or abs(p.total_net_revenue - f.fct_total_net_revenue) > 0.01
