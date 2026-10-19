"""Parking lot. A bus takes five consecutive car spots. Leave is idempotent."""

from __future__ import annotations

from dataclasses import dataclass, field


class Full(Exception):
    pass


class UnknownTicket(Exception):
    pass


@dataclass
class Spot:
    spot_id: str
    size: str  # "M" motorcycle, "C" car
    free: bool = True
    ticket_id: str | None = None


@dataclass
class Vehicle:
    plate: str
    kind: str  # motorcycle, car, bus

    def spots_needed(self) -> int:
        return 5 if self.kind == "bus" else 1


@dataclass
class Ticket:
    ticket_id: str
    plate: str
    kind: str
    spot_ids: list[str]
    entry: float
    exit: float | None = None
    fee: int | None = None


@dataclass
class Row:
    spots: list[Spot]

    def allocate(self, vehicle: Vehicle, ticket_id: str) -> list[Spot] | None:
        if vehicle.kind == "bus":
            run: list[Spot] = []
            for spot in self.spots:
                if spot.free and spot.size == "C":
                    run.append(spot)
                    if len(run) == 5:
                        break
                else:
                    run = []
            if len(run) < 5:
                return None
            chosen = run
        else:
            preferred = ["M", "C"] if vehicle.kind == "motorcycle" else ["C"]
            chosen_one = None
            for size in preferred:
                for spot in self.spots:
                    if spot.free and spot.size == size:
                        chosen_one = spot
                        break
                if chosen_one is not None:
                    break
            if chosen_one is None:
                return None
            chosen = [chosen_one]
        for spot in chosen:
            spot.free = False
            spot.ticket_id = ticket_id
        return chosen


class HourlyFee:
    def __init__(self, rate: int) -> None:
        self.rate = rate

    def fee(self, entry: float, exit_time: float) -> int:
        hours = max(1, int((exit_time - entry + 3599) // 3600))
        return hours * self.rate


@dataclass
class ParkingLot:
    rows: list[Row]
    fees: HourlyFee
    tickets: dict[str, Ticket] = field(default_factory=dict)
    _seq: int = 0

    def park(self, vehicle: Vehicle, now: float) -> Ticket:
        self._seq += 1
        ticket_id = f"T{self._seq}"
        taken: list[Spot] = []
        for row in self.rows:
            got = row.allocate(vehicle, ticket_id)
            if got is not None:
                taken = got
                break
        if not taken:
            raise Full()
        ticket = Ticket(ticket_id, vehicle.plate, vehicle.kind, [s.spot_id for s in taken], now)
        self.tickets[ticket_id] = ticket
        return ticket

    def leave(self, ticket_id: str, now: float) -> int:
        ticket = self.tickets.get(ticket_id)
        if ticket is None:
            raise UnknownTicket(ticket_id)
        if ticket.exit is not None and ticket.fee is not None:
            return ticket.fee
        for row in self.rows:
            for spot in row.spots:
                if spot.spot_id in ticket.spot_ids:
                    spot.free = True
                    spot.ticket_id = None
        ticket.exit = now
        ticket.fee = self.fees.fee(ticket.entry, now)
        return ticket.fee
