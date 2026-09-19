"""Jurisdiction rules: what an OSM extract does not say. Speeds in m/s."""

import re
from dataclasses import dataclass

MPH = 0.44704
KMH = 1 / 3.6

# Highway classes we import, most important first.
CLASSES = [
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
]


def class_rank(kind: str) -> float:
    """Higher is more important. Link roads rank just below their parent class."""
    base = kind.removesuffix("_link")
    rank = len(CLASSES) - CLASSES.index(base) if base in CLASSES else 0
    return rank - 0.5 if kind.endswith("_link") else rank


@dataclass(frozen=True)
class Rules:
    name: str
    speed_unit: str  # unit of a bare maxspeed number: "mph" or "km/h"
    default_speeds: dict[str, float]  # highway class -> m/s
    default_lanes: dict[str, int]  # highway class -> lanes per direction
    right_on_red: bool
    signal_min_green: float = 8.0
    signal_max_green: float = 35.0
    # OSM often lacks traffic_signals nodes; assume a signal where a road of at least
    # `infer_signals_major_class` crosses one of at least `infer_signals_minor_class`.
    # None disables the guess.
    infer_signals_major_class: str | None = "secondary"
    infer_signals_minor_class: str = "tertiary"

    def speed_for(self, kind: str) -> float:
        base = kind.removesuffix("_link")
        return self.default_speeds.get(kind, self.default_speeds.get(base, 30 * MPH))

    def lanes_for(self, kind: str) -> int:
        base = kind.removesuffix("_link")
        return self.default_lanes.get(kind, self.default_lanes.get(base, 1))

    def parse_maxspeed(self, text: str | None) -> float | None:
        if not text:
            return None
        m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh)?", text)
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2) or self.speed_unit
        return value * (MPH if unit == "mph" else KMH)


def _mph(**kw):
    return {k: v * MPH for k, v in kw.items()}


def _kmh(**kw):
    return {k: v * KMH for k, v in kw.items()}


_LANES_US = {
    "motorway": 3,
    "trunk": 2,
    "primary": 2,
    "secondary": 2,
    "tertiary": 1,
    "unclassified": 1,
    "residential": 1,
    "living_street": 1,
}

DALLAS = Rules(
    name="dallas",
    speed_unit="mph",
    default_speeds=_mph(
        motorway=65,
        trunk=55,
        primary=40,
        secondary=35,
        tertiary=35,
        unclassified=30,
        residential=30,
        living_street=15,
        motorway_link=45,
        trunk_link=40,
        primary_link=30,
        secondary_link=30,
        tertiary_link=30,
    ),
    default_lanes=_LANES_US,
    right_on_red=True,
)

NEW_YORK = Rules(
    name="new_york",
    speed_unit="mph",
    default_speeds=_mph(
        motorway=50,
        trunk=40,
        primary=25,
        secondary=25,
        tertiary=25,
        unclassified=25,
        residential=25,
        living_street=10,
        motorway_link=35,
        trunk_link=30,
        primary_link=25,
        secondary_link=25,
        tertiary_link=25,
    ),
    default_lanes=_LANES_US,
    right_on_red=False,  # prohibited in New York City unless signed
)

NETHERLANDS = Rules(
    name="netherlands",
    speed_unit="km/h",
    default_speeds=_kmh(
        motorway=100,
        trunk=100,
        primary=80,
        secondary=50,
        tertiary=50,
        unclassified=50,
        residential=30,
        living_street=15,
        motorway_link=70,
        trunk_link=70,
        primary_link=50,
        secondary_link=50,
        tertiary_link=50,
    ),
    default_lanes={**_LANES_US, "primary": 1, "secondary": 1},
    right_on_red=False,
)

RULES = {r.name: r for r in (DALLAS, NEW_YORK, NETHERLANDS)}
