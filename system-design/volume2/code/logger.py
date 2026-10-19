"""Logger. Levels filter. A failing appender does not sink the others."""

from __future__ import annotations

from dataclasses import dataclass, field


LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}


@dataclass
class LogEvent:
    level: str
    logger_name: str
    message: str
    context: dict[str, str] = field(default_factory=dict)


class ListAppender:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []
        self.fail = False

    def append(self, event: LogEvent) -> None:
        if self.fail:
            raise RuntimeError("disk full")
        self.events.append(event)


class Logger:
    def __init__(self, name: str, min_level: str, appenders: list[ListAppender]) -> None:
        self.name = name
        self.min_level = min_level
        self.appenders = appenders
        self.dropped_errors = 0

    def log(self, level: str, message: str, **context: str) -> None:
        if LEVELS[level] < LEVELS[self.min_level]:
            return
        event = LogEvent(level, self.name, message, dict(context))
        for appender in self.appenders:
            try:
                appender.append(event)
            except Exception:
                self.dropped_errors += 1
