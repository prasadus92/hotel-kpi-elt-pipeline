-- Staging: cleaned hotel room inventory (from the seed).
--
-- This is the authoritative list of room types that COUNT toward KPIs. Any
-- reservation line item whose room_type_id is not present here for its hotel is
-- ignored (room types that no longer exist or that the owner excludes).

with source as (

    select * from {{ ref('hotel_room_inventory') }}

)

select
    cast(hotel_id     as varchar) as hotel_id,
    cast(room_type_id as varchar) as room_type_id,
    cast(quantity     as integer) as quantity
from source
where hotel_id is not null
  and room_type_id is not null
  and quantity is not null
  and quantity >= 0
