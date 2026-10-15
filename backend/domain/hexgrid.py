"""Axial hex-grid geometry (Red Blob Games conventions).

We use *axial* coordinates ``(q, r)``. Civ 6 internally uses offset (x, y)
coordinates; converters live in :mod:`backend.io` for the in-game export.
For the manual editor and all internal math, axial is the single source of truth.

Reference: https://www.redblobgames.com/grids/hexagons/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

# The six neighbour directions in axial coordinates. Order is stable so callers
# may rely on it (e.g. river edges are indexed by direction).
AXIAL_DIRECTIONS: tuple[tuple[int, int], ...] = (
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, 0),
    (-1, 1),
    (0, 1),
)


@dataclass(frozen=True, order=True)
class Hex:
    """A hex coordinate. Hashable, usable as a dict key."""

    q: int
    r: int

    @property
    def s(self) -> int:
        # Cube third coordinate (q + r + s == 0).
        return -self.q - self.r

    def neighbor(self, direction: int) -> "Hex":
        dq, dr = AXIAL_DIRECTIONS[direction % 6]
        return Hex(self.q + dq, self.r + dr)

    def neighbors(self) -> list["Hex"]:
        return [Hex(self.q + dq, self.r + dr) for dq, dr in AXIAL_DIRECTIONS]

    def __add__(self, other: "Hex") -> "Hex":
        return Hex(self.q + other.q, self.r + other.r)


def distance(a: Hex, b: Hex) -> int:
    """Hex distance (number of steps between two tiles)."""
    return (abs(a.q - b.q) + abs(a.r - b.r) + abs(a.s - b.s)) // 2


def ring(center: Hex, radius: int) -> list[Hex]:
    """All hexes at exactly ``radius`` steps from ``center``."""
    if radius == 0:
        return [center]
    results: list[Hex] = []
    # Start at the hex `radius` steps in direction 4, then walk the ring.
    dq, dr = AXIAL_DIRECTIONS[4]
    h = Hex(center.q + dq * radius, center.r + dr * radius)
    for i in range(6):
        for _ in range(radius):
            results.append(h)
            h = h.neighbor(i)
    return results


def spiral(center: Hex, radius: int) -> list[Hex]:
    """``center`` plus all hexes within ``radius`` steps (a filled disc)."""
    results = [center]
    for k in range(1, radius + 1):
        results.extend(ring(center, k))
    return results


def within_radius(center: Hex, radius: int) -> Iterator[Hex]:
    """Iterate hexes with ``0 <= distance(center, h) <= radius``."""
    for dq in range(-radius, radius + 1):
        for dr in range(max(-radius, -dq - radius), min(radius, -dq + radius) + 1):
            yield Hex(center.q + dq, center.r + dr)
