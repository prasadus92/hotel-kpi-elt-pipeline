-- Availability coverage must be a clean percentage in [0, 100]. Oversold nights
-- are capped at 100 by the model, so anything outside the range signals a bug in
-- the coverage calculation (bad capacity join, negative occupied rooms, etc.).

select
    hotel_id,
    night,
    expected_room_nights,
    occupied_rooms,
    availability_pct
from {{ ref('data_availability') }}
where
    availability_pct < 0
    or availability_pct > 100
    or expected_room_nights <= 0
