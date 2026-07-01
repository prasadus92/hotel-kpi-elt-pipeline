-- Adapter: source C (cloud PMS) -> the shared reservation contract.
--
-- The cloud feed is nested JSON with camelCase keys, ISO-8601 timestamps
-- carrying a timezone offset, USD amounts, and rate plans with discounts (so
-- gross and net differ by more than tax). Like the native source it re-emits
-- the whole reservation on every change (revision snapshots), so dedup
-- downstream does real work here.
--
-- Normalization: rename camelCase to the shared fields, map the status
-- vocabulary, parse the tz-aware timestamps to plain timestamps, and rebuild
-- nightlyRates into the shared line-item struct.

with source as (

    select * from {{ source('raw', 'raw_pms_cloud') }}

),

casted as (

    -- The cloud source uses camelCase column names, so they are quoted to
    -- preserve case (and satisfy the lower-case identifier lint rule).
    select
        'cloud' as source_system,
        "propertyId" as hotel_id,
        "confirmationId" as reservation_id,
        -- Cloud statuses are camelCase variants of the contract statuses.
        case "reservationStatus"
            when 'checkedOut' then 'checked_out'
            when 'checkedIn' then 'checked_in'
            when 'confirmed' then 'confirmed'
            when 'cancelled' then 'cancelled'
            else lower(trim("reservationStatus"))
        end as status,
        try_cast(arrival as date) as arrival_date,
        try_cast(departure as date) as departure_date,
        -- Timestamps carry a tz offset (e.g. 2026-05-01T09:00:00-05:00). We keep
        -- the wall-clock value; only relative ordering per reservation matters
        -- for dedup, and all cloud events share one offset.
        cast(try_strptime("createdAt", '%Y-%m-%dT%H:%M:%S%z') as timestamp) as created_at,
        cast(try_strptime("modifiedAt", '%Y-%m-%dT%H:%M:%S%z') as timestamp) as updated_at,
        list_transform(
            "nightlyRates",
            sd -> {
                'room_type_id': sd."roomCode",
                'start_date': sd."stayDate",
                'end_date': sd."stayDate",
                'room_gross': sd."roomChargeGross",
                'room_net': sd."roomChargeNet",
                'fnb_gross': sd."incidentalsGross",
                'fnb_net': sd."incidentalsNet"
            }
        ) as stay_dates
    from source

)

{{ reservation_validity() }}
