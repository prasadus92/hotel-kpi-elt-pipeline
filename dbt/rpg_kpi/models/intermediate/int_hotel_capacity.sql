-- Intermediate: total sellable rooms per hotel = the occupancy denominator.
-- Sum of room quantities across all room types that count for the hotel.

select
    hotel_id,
    sum(quantity) as total_rooms
from {{ ref('stg_hotel_inventory') }}
group by hotel_id
