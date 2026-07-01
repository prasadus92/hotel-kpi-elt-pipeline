-- Adapter: source B (Nordic PMS) -> the shared reservation contract.
--
-- The Nordic feed is a flat, pre-exploded CSV: one row per room-night, with
-- DD.MM.YYYY dates, gross-inclusive EUR prices and a VAT column, and its own
-- short status vocabulary. This adapter does the real normalization work:
--
--   * parse DD.MM.YYYY into DATE,
--   * map the status codes onto the four contract statuses,
--   * derive net from gross (net = gross - VAT; board net = board / (1 + VAT)),
--   * regroup the per-night rows back into one reservation with a stay_dates
--     list, so the downstream models see the same shape as every other source.
--
-- Nordic has no snapshot revisions, so dedup downstream is a no-op for it, but
-- it flows through the identical path.

with source as (

    select * from {{ source('raw', 'raw_pms_nordic') }}

),

nights as (

    select
        property_code as hotel_id,
        booking_ref as reservation_id,
        -- Map the Nordic vocabulary onto the contract statuses. NOSHOW is a
        -- guest who never arrived but is still charged, so it behaves like a
        -- confirmed (non-cancelled) booking: counts for occupancy and revenue.
        case lower(trim(stay_status))
            when 'ok' then 'checked_in'
            when 'out' then 'checked_out'
            when 'cxl' then 'cancelled'
            when 'noshow' then 'confirmed'
            else lower(trim(stay_status))
        end as status,
        cast(try_strptime(checkin, '%d.%m.%Y') as date) as arrival_date,
        cast(try_strptime(checkout, '%d.%m.%Y') as date) as departure_date,
        cast(try_strptime(stay_night, '%d.%m.%Y') as date) as stay_night,
        room_code as room_type_id,
        -- Gross is VAT-inclusive; net backs the VAT out. Board (F&B) is quoted
        -- gross-inclusive at the same VAT rate, so divide it out for net.
        try_cast(room_gross_eur as double) as room_gross,
        try_cast(room_gross_eur as double) - try_cast(room_vat_eur as double) as room_net,
        try_cast(board_gross_eur as double) as fnb_gross,
        round(try_cast(board_gross_eur as double) / 1.10, 2) as fnb_net
    from source

),

-- Regroup the flat night rows back into one reservation each. Synthesize the
-- timestamps the contract needs: created_at from arrival, updated_at fixed
-- (Nordic sends no revision history, so any stable value satisfies the dedup).
reservations as (

    select
        'nordic' as source_system,
        hotel_id,
        reservation_id,
        any_value(status) as status,
        min(arrival_date) as arrival_date,
        max(departure_date) as departure_date,
        cast(min(arrival_date) as timestamp) as created_at,
        cast(min(arrival_date) as timestamp) as updated_at,
        list_transform(
            list_sort(
                list(
                    {
                        'room_type_id': room_type_id,
                        'start_date': strftime(stay_night, '%Y-%m-%d'),
                        'end_date': strftime(stay_night, '%Y-%m-%d'),
                        'room_gross': cast(room_gross as varchar),
                        'room_net': cast(room_net as varchar),
                        'fnb_gross': cast(fnb_gross as varchar),
                        'fnb_net': cast(fnb_net as varchar)
                    }
                )
            ),
            sd -> sd
        ) as stay_dates
    from nights
    group by hotel_id, reservation_id

),

casted as (

    select
        source_system,
        hotel_id,
        reservation_id,
        status,
        arrival_date,
        departure_date,
        created_at,
        updated_at,
        stay_dates
    from reservations

)

{{ reservation_validity() }}
