"""时间线工具。"""
from __future__ import annotations

from datetime import datetime


class Timeline:
    def __init__(self) -> None:
        self._start = datetime.now()
        self._marks: list[tuple[str, datetime]] = []

    def mark(self, name: str) -> None:
        self._marks.append((name, datetime.now()))

    def elapsed(self) -> str:
        delta = datetime.now() - self._start
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        if m < 60:
            return f"{m}m{s}s"
        h, m = divmod(m, 60)
        return f"{h}h{m}m"

    def report(self) -> str:
        lines = ["Timeline:"]
        last = self._start
        for name, ts in self._marks:
            delta = ts - last
            lines.append(f"  +{delta.total_seconds():.1f}s {name}")
            last = ts
        return "\n".join(lines)
