{#
  Shared reservation-level validity flag for every PMS adapter.

  Each stg_pms_* adapter produces a `casted` CTE with the normalized reservation
  columns (typed reservation fields plus a `stay_dates` LIST(STRUCT(...)) using
  the shared line-item field names). This macro appends the `validated` CTE that
  attaches `is_valid`, so the validation rule is defined once and every source
  is held to the same contract.

  The rule is deliberately source-agnostic: it operates on the already
  normalized columns, so a new PMS only has to map its fields correctly and
  inherits validation for free.
#}
{% macro reservation_validity(cte='casted') %}
,

validated as (

    select
        *,
        (
            hotel_id is not null
            and reservation_id is not null
            -- status must be one of the four contract enum values (adapters map
            -- their native vocabularies onto these before this check)
            and status in ('confirmed', 'cancelled', 'checked_in', 'checked_out')
            -- dates must parse and departure must be strictly after arrival
            and arrival_date is not null
            and departure_date is not null
            and departure_date > arrival_date
            -- timestamps required (updated_at drives dedup ordering)
            and created_at is not null
            and updated_at is not null
            -- a reservation must carry at least one stay-date line item
            and stay_dates is not null
            and len(stay_dates) > 0
        ) as is_valid
    from {{ cte }}

)

select * from validated
{% endmacro %}
