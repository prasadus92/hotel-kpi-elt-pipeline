-- The reconciliation gate: the summed per-source totals MUST equal the unified
-- fct_daily_kpis totals (within the revenue tolerance). This is the pass/fail
-- check a data team would block on. Returns the total row only if it did NOT
-- reconcile, so any drift (dropped rows, double counting) fails the build.

select
    source_system,
    occupied_room_nights_diff,
    total_net_revenue_diff,
    reconciled
from {{ ref('reconciliation_report') }}
where
    source_system = '__total__'
    and reconciled = false
