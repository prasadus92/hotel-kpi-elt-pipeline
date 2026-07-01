-- Adapter: source A (native PMS) -> the shared reservation contract.
--
-- The native feed already matches the internal shape closely, so this adapter
-- mostly casts text to typed columns and rebuilds `stay_dates` as the shared
-- line-item struct. It emits the SAME columns every stg_pms_* adapter emits, so
-- stg_reservations can union the sources without knowing which PMS they came
-- from. Reservation-level validity is flagged here; line-item validity is
-- applied downstream (after dedup) in int_reservation_nights.

with source as (

    select * from {{ source('raw', 'raw_pms_native') }}

),

casted as (

    select
        'native' as source_system,
        hotel_id,
        reservation_id,
        lower(trim(status)) as status,
        try_cast(arrival_date as date) as arrival_date,
        try_cast(departure_date as date) as departure_date,
        try_cast(created_at as timestamp) as created_at,
        try_cast(updated_at as timestamp) as updated_at,
        -- Rebuild stay_dates into the shared line-item struct. The native shape
        -- already uses these field names, so this is a straight carry-forward.
        list_transform(
            stay_dates,
            sd -> {
                'room_type_id': sd.room_type_id,
                'start_date': sd.start_date,
                'end_date': sd.end_date,
                'room_gross': sd.room_revenue_gross_amount,
                'room_net': sd.room_revenue_net_amount,
                'fnb_gross': sd.fnb_gross_amount,
                'fnb_net': sd.fnb_net_amount
            }
        ) as stay_dates
    from source

)

{{ reservation_validity() }}
