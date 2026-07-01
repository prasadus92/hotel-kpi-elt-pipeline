-- Mart (fact): daily performance KPIs at the grain of (hotel_id, night).
--
-- This is the reusable, request-agnostic fact table: it covers every hotel and
-- every night that actually has activity. Slicing to a specific hotel/date
-- range and padding missing nights with zeros is the job of kpi_report.
--
-- KPI rules (per the contract):
--   * occupied_rooms      -> count of rooms occupied, EXCLUDING cancelled.
--   * total_net_revenue   -> room_net + fnb_net, INCLUDING every status
--                            (cancelled bookings still contribute revenue).
--   * occupancy_percentage-> occupied_rooms / hotel capacity * 100, 2 dp.
--   * adr                 -> total_net_revenue / occupied_rooms, to nearest
--                            integer; 0 when there are no occupied rooms.
--
-- Note the deliberate asymmetry: cancelled reservations are EXCLUDED from
-- occupancy/ADR's room count but INCLUDED in revenue. This is taken verbatim
-- from the KPI spec (occupancy = "any status except cancelled"; revenue = "any
-- status"). A consequence: a night with only cancelled bookings shows revenue
-- but ADR = 0 (no occupied rooms to divide by).

with reservation_nights as (

    select * from {{ ref('int_reservation_nights') }}

),

capacity as (

    select * from {{ ref('int_hotel_capacity') }}

),

aggregated as (

    select
        hotel_id,
        night,
        sum(case when counts_for_occupancy then 1 else 0 end) as occupied_rooms,
        sum(total_net_revenue) as total_net_revenue
    from reservation_nights
    group by hotel_id, night

)

select
    a.hotel_id,
    a.night,
    a.occupied_rooms,
    c.total_rooms,
    round(a.occupied_rooms * 100.0 / nullif(c.total_rooms, 0), 2) as occupancy_percentage,
    round(a.total_net_revenue, 2) as total_net_revenue,
    case
        when a.occupied_rooms = 0 then 0
        else cast(round(a.total_net_revenue / a.occupied_rooms) as bigint)
    end as adr
from aggregated as a
left join capacity as c using (hotel_id)
