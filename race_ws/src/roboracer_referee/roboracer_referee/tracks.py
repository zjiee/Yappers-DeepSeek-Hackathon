"""Loading track metadata from maps/tracks.yaml.

On Track 2 the circuit lives inside the AutoDRIVE Simulator build, not in this
repository. The simulator owns the start/finish line, the lap counter and the
collision detection, so **nothing in this file is used to score a run**. What
it carries is metadata:

  * the track name that goes into a result file;
  * where an occupancy grid of the circuit lives, if one has been published,
    for teams building a racing line or their own localisation;
  * optional planning geometry (`start_pose`, `finish_line`) used only by
    `scripts/track_tool.py` when it traces a centreline off that grid.

That separation is deliberate. A scored run must work before the map exists,
and must keep working if the organisers re-publish it.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import yaml

from .geometry import signed_side

Point = Tuple[float, float]

# Searched in order; the first hit wins. The in-image copy is what a container
# with no bind mount sees, the repository copy is what teams edit.
DEFAULT_SEARCH_PATHS = (
    "/hackathon/maps/tracks.yaml",
    "/opt/hackathon_maps/tracks.yaml",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "maps", "tracks.yaml"),
)


class TrackError(ValueError):
    """Raised for anything wrong with a track definition, with a fixable message."""


@dataclass
class Track:
    name: str
    description: str
    map_path: str                                   # without the image extension
    map_image_ext: str
    start_pose: Optional[Tuple[float, float, float]]    # x, y, theta (rad)
    finish_line: Optional[Tuple[Point, Point]]
    crossing_direction: int
    simulator_build: str

    @property
    def map_yaml(self) -> str:
        return self.map_path + ".yaml"

    @property
    def map_available(self) -> bool:
        """Whether an occupancy grid for this circuit has actually been published."""
        return bool(self.map_path) and os.path.isfile(self.map_yaml) \
            and os.path.isfile(self.map_path + self.map_image_ext)


def _as_float_list(value, count: int, field: str) -> List[float]:
    try:
        items = [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise TrackError(f"'{field}' must be a list of {count} numbers, got {value!r}") from exc
    if len(items) != count:
        raise TrackError(f"'{field}' must have exactly {count} entries, got {len(items)}")
    if not all(math.isfinite(v) for v in items):
        raise TrackError(f"'{field}' contains a non-finite value: {items}")
    return items


def infer_crossing_direction(start_pose: Tuple[float, float, float],
                             line_a: Point, line_b: Point) -> int:
    """Which way the signed side of the line flips when the car races forwards.

    Planning geometry only - the simulator decides what counts as a lap. It is
    derived from the start heading rather than configured by hand, because
    getting it backwards would make `track_tool.py centerline` trace the
    circuit the wrong way round.
    """
    x, y, theta = start_pose
    ahead = (x + math.cos(theta), y + math.sin(theta))
    delta = signed_side(line_a, line_b, ahead) - signed_side(line_a, line_b, (x, y))
    if abs(delta) < 1e-9:
        raise TrackError(
            "The start heading runs parallel to the finish line, so a crossing "
            "direction cannot be inferred. Set 'crossing_direction' explicitly."
        )
    return 1 if delta > 0 else -1


def parse_track(name: str, spec: dict) -> Track:
    if not isinstance(spec, dict):
        raise TrackError(f"Track '{name}' must be a mapping, got {type(spec).__name__}")

    start_pose = None
    if spec.get("start_pose") is not None:
        values = _as_float_list(spec["start_pose"], 3, f"{name}.start_pose")
        start_pose = (values[0], values[1], values[2])

    finish_line = None
    if spec.get("finish_line") is not None:
        raw = spec["finish_line"]
        # Accept either [[x1,y1],[x2,y2]] or a flat [x1,y1,x2,y2].
        if (isinstance(raw, (list, tuple)) and len(raw) == 2
                and all(isinstance(p, (list, tuple)) for p in raw)):
            a = _as_float_list(raw[0], 2, f"{name}.finish_line[0]")
            b = _as_float_list(raw[1], 2, f"{name}.finish_line[1]")
        else:
            flat = _as_float_list(raw, 4, f"{name}.finish_line")
            a, b = flat[:2], flat[2:]
        if math.dist((a[0], a[1]), (b[0], b[1])) < 1e-3:
            raise TrackError(f"Track '{name}': the finish line has zero length")
        finish_line = ((a[0], a[1]), (b[0], b[1]))

    direction = spec.get("crossing_direction")
    if direction is None:
        if start_pose is not None and finish_line is not None:
            direction = infer_crossing_direction(start_pose, finish_line[0], finish_line[1])
        else:
            direction = 1
    elif int(direction) not in (1, -1):
        raise TrackError(f"Track '{name}': crossing_direction must be 1 or -1")

    return Track(
        name=name,
        description=str(spec.get("description", "")),
        map_path=str(spec.get("map_path", "")),
        map_image_ext=str(spec.get("map_image_ext", ".pgm")),
        start_pose=start_pose,
        finish_line=finish_line,
        crossing_direction=int(direction),
        simulator_build=str(spec.get("simulator_build", "")),
    )


def find_track_config(explicit: Optional[str] = None) -> str:
    candidates = [explicit] if explicit else list(DEFAULT_SEARCH_PATHS)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise TrackError(
        "Could not find tracks.yaml. Looked in: "
        + ", ".join(p for p in candidates if p)
        + ". Pass track_config:=/path/to/tracks.yaml, or check that the repository "
          "is mounted at /hackathon."
    )


def load_tracks(path: Optional[str] = None) -> Tuple[Dict[str, Track], str]:
    """Return every track in the file plus the name of the default one."""
    resolved = find_track_config(path)
    try:
        with open(resolved, "r") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise TrackError(f"{resolved} is not valid YAML: {exc}") from exc
    except OSError as exc:
        raise TrackError(f"Could not read {resolved}: {exc}") from exc

    if not isinstance(data, dict) or "tracks" not in data:
        raise TrackError(f"{resolved} must contain a top-level 'tracks' mapping")

    tracks = {name: parse_track(name, spec) for name, spec in (data["tracks"] or {}).items()}
    if not tracks:
        raise TrackError(f"{resolved} defines no tracks")

    default = data.get("default") or next(iter(tracks))
    if default not in tracks:
        raise TrackError(
            f"{resolved}: default track '{default}' is not defined. "
            f"Available: {', '.join(sorted(tracks))}"
        )
    return tracks, default


def load_track(name: Optional[str] = None, path: Optional[str] = None) -> Track:
    tracks, default = load_tracks(path)
    chosen = name or default
    if chosen not in tracks:
        raise TrackError(
            f"Unknown track '{chosen}'. Available: {', '.join(sorted(tracks))}"
        )
    return tracks[chosen]
