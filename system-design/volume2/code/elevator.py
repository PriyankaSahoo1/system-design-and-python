"""One elevator. LOOK: finish this direction, then reverse."""

from __future__ import annotations


class Elevator:
    def __init__(self, floor: int = 0) -> None:
        self.floor = floor
        self.direction = "IDLE"
        self.up: set[int] = set()
        self.down: set[int] = set()
        self.doors_open = False

    def call(self, floor: int, direction: str) -> None:
        if direction == "UP":
            self.up.add(floor)
        elif direction == "DOWN":
            self.down.add(floor)
        else:
            raise ValueError(direction)
        self._wake()

    def choose(self, floor: int) -> None:
        if floor > self.floor:
            self.up.add(floor)
        elif floor < self.floor:
            self.down.add(floor)
        else:
            self.doors_open = True
        self._wake()

    def step(self) -> None:
        self.doors_open = False
        if self.direction == "IDLE":
            self._wake()
            if self.direction == "IDLE":
                return
        if self.direction == "UP":
            if self.floor in self.up:
                self.up.discard(self.floor)
                self.doors_open = True
                if not self.up:
                    self.direction = "DOWN" if self.down else "IDLE"
                return
            if self.up and self.floor < max(self.up):
                self.floor += 1
                return
            self.direction = "DOWN" if self.down else "IDLE"
            return
        if self.floor in self.down:
            self.down.discard(self.floor)
            self.doors_open = True
            if not self.down:
                self.direction = "UP" if self.up else "IDLE"
            return
        if self.down and self.floor > min(self.down):
            self.floor -= 1
            return
        self.direction = "UP" if self.up else "IDLE"

    def _wake(self) -> None:
        if self.direction != "IDLE":
            return
        if any(floor > self.floor for floor in self.up | self.down):
            self.direction = "UP"
        elif any(floor < self.floor for floor in self.up | self.down):
            self.direction = "DOWN"
        elif self.floor in self.up or self.floor in self.down:
            self.direction = "UP" if self.floor in self.up else "DOWN"
