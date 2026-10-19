"""Seat holds. The conditional update is what makes two buyers safe."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


class Unavailable(Exception):
    pass


class BadState(Exception):
    pass


@dataclass
class Seat:
    seat_id: str
    state: str = "free"  # free, held, sold
    booking_id: str | None = None


@dataclass
class Booking:
    booking_id: str
    seat_ids: list[str]
    user_id: str
    state: str  # HELD, CONFIRMED, EXPIRED
    hold_expires_at: float


class Show:
    def __init__(self, seat_ids: list[str]) -> None:
        self.seats = {seat_id: Seat(seat_id) for seat_id in seat_ids}
        self.bookings: dict[str, Booking] = {}
        self._seq = 0
        self._lock = threading.Lock()

    def hold(self, seat_ids: list[str], user_id: str, now: float, ttl: float = 300.0) -> Booking:
        """Same shape as:

        UPDATE seats SET booking_id = ? WHERE seat_id IN (...) AND state = 'free'
        Commit only when every requested row changed.
        """
        with self._lock:
            for seat_id in seat_ids:
                seat = self.seats[seat_id]
                if seat.state != "free":
                    raise Unavailable(seat_id)
            self._seq += 1
            booking_id = f"B{self._seq}"
            for seat_id in seat_ids:
                seat = self.seats[seat_id]
                seat.state = "held"
                seat.booking_id = booking_id
            booking = Booking(booking_id, list(seat_ids), user_id, "HELD", now + ttl)
            self.bookings[booking_id] = booking
            return booking

    def confirm(self, booking_id: str, now: float) -> Booking:
        with self._lock:
            booking = self.bookings[booking_id]
            if booking.state == "CONFIRMED":
                return booking
            if booking.state != "HELD" or booking.hold_expires_at <= now:
                raise BadState(booking.state)
            for seat_id in booking.seat_ids:
                seat = self.seats[seat_id]
                if seat.booking_id != booking_id or seat.state != "held":
                    raise BadState(seat_id)
            for seat_id in booking.seat_ids:
                self.seats[seat_id].state = "sold"
            booking.state = "CONFIRMED"
            return booking

    def expire(self, now: float) -> int:
        with self._lock:
            expired = 0
            for booking in self.bookings.values():
                if booking.state == "HELD" and booking.hold_expires_at <= now:
                    for seat_id in booking.seat_ids:
                        seat = self.seats[seat_id]
                        if seat.booking_id == booking.booking_id and seat.state == "held":
                            seat.state = "free"
                            seat.booking_id = None
                    booking.state = "EXPIRED"
                    expired += 1
            return expired
