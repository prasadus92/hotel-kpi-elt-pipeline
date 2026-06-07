-- Staging: one row per RAW reservation event.
--
-- Responsibilities:
--   * Cast the text landing fields to typed columns (schema-on-read -> typed).
--   * Apply RESERVATION-LEVEL contract validation and expose `is_valid` so the
--     intermediate layer can keep only "valid" events before deduplicating.
--
-- We do NOT touch stay_dates here beyond carrying the list forward; stay-date
-- (line-item) validation happens in int_reservation_nights after dedup, so that
-- "the last valid one" is decided on the reservation grain first.

with source as (

    select * from {{ source('raw', 'raw_reservations') }}

),

casted as (

    select
        hotel_id,
        reservation_id,
        lower(trim(status))                      as status,
        try_cast(arrival_date   as date)         as arrival_date,
        try_cast(departure_date as date)         as departure_date,
        try_cast(created_at     as timestamp)    as created_at,
        try_cast(updated_at     as timestamp)    as updated_at,
        stay_dates,
        -- raw values retained for validation / debugging
        status                                   as status_raw,
        arrival_date                             as arrival_date_raw,
        departure_date                           as departure_date_raw,
        updated_at                               as updated_at_raw
    from source

),

validated as (

    select
        *,
        (
            hotel_id       is not null
            and reservation_id is not null
            -- status must be one of the four contract enum values
            and status in ('confirmed', 'cancelled', 'checked_in', 'checked_out')
            -- dates must parse and departure must be strictly after arrival
            and arrival_date   is not null
            and departure_date is not null
            and departure_date > arrival_date
            -- timestamps required (updated_at drives dedup ordering)
            and created_at is not null
            and updated_at is not null
            -- a reservation must carry at least one stay-date line item
            and stay_dates is not null
            and len(stay_dates) > 0
        ) as is_valid
    from casted

)

select * from validated
