-- Net revenue should never be negative in this dataset.
select *
from {{ ref('fct_daily_kpis') }}
where total_net_revenue < 0
