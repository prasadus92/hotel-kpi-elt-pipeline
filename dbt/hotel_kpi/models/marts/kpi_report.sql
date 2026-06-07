-- Mart (serving): the exact CSV contract for one hotel and one date range.
--
-- Parametrised by dbt vars (hotel_id, from_date, to_date), which run_pipeline.py
-- forwards from the CLI. A date spine guarantees one row PER night in the
-- requested range, with zeros where the fact has no data. Output columns and
-- ordering match the contract exactly; the export step copies this verbatim.

with bounds as (

    select
        cast('{{ var("from_date") }}' as date) as from_date,
        cast('{{ var("to_date") }}' as date) as to_date,
        '{{ var("hotel_id") }}' as hotel_id

),

-- One row per night in [from_date, to_date] (inclusive). range() is half-open,
-- so we step to (to_date + 1 day) to include the final day.
spine as (

    select
        b.hotel_id,
        cast(
            unnest(range(
                cast(b.from_date as timestamp),
                cast((b.to_date + interval '1 day') as timestamp),
                interval '1 day'
            )) as date
        ) as night
    from bounds as b

),

fct as (

    select * from {{ ref('fct_daily_kpis') }}

)

-- Column names are quoted to preserve the exact uppercase contract headers.
select
    strftime(s.night, '%Y-%m-%d') as "NIGHT_OF_STAY",
    cast(coalesce(f.occupancy_percentage, 0) as decimal(9, 2)) as "OCCUPANCY_PERCENTAGE",
    cast(coalesce(f.total_net_revenue, 0) as decimal(14, 2)) as "TOTAL_NET_REVENUE",
    cast(coalesce(f.adr, 0) as bigint) as "ADR"
from spine as s
left join fct as f
    on
        s.hotel_id = f.hotel_id
        and s.night = f.night
order by s.night desc
