"""Finish-line crossing detection.

Kept free of ROS imports so the judging maths can be unit tested on its own.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

Point = Tuple[float, float]


def signed_side(line_a: Point, line_b: Point, point: Point) -> float:
    """Which side of the directed line A->B the point lies on.

    Positive is left of the direction of travel A->B, negative is right, and
    zero is exactly on the line. The magnitude is proportional to the distance,
    which is why it is also usable as a "how far past the line" measure.
    """
    return ((line_b[0] - line_a[0]) * (point[1] - line_a[1])
            - (line_b[1] - line_a[1]) * (point[0] - line_a[0]))


def segment_crossing_fraction(prev: Point, curr: Point,
                              line_a: Point, line_b: Point) -> Optional[float]:
    """Where along prev->curr the car cuts the finish line segment.

    Returns the fraction t in [0, 1] such that prev + t * (curr - prev) is the
    intersection point, or None when the two segments do not intersect.

    The fraction matters: odometry arrives at a finite rate, so the car is
    already some centimetres past the line by the time we see it. Interpolating
    the exact moment of the cut removes that sampling bias from lap times,
    which at racing speed is worth several hundredths of a second per lap.
    """
    r_x, r_y = curr[0] - prev[0], curr[1] - prev[1]
    s_x, s_y = line_b[0] - line_a[0], line_b[1] - line_a[1]

    denom = r_x * s_y - r_y * s_x
    if abs(denom) < 1e-12:
        # Parallel or degenerate: treat as no crossing. A car travelling exactly
        # along the finish line is not completing a lap.
        return None

    q_p_x, q_p_y = line_a[0] - prev[0], line_a[1] - prev[1]
    t = (q_p_x * s_y - q_p_y * s_x) / denom
    u = (q_p_x * r_y - q_p_y * r_x) / denom

    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t
    return None


def line_from_pose_and_width(x: float, y: float, theta: float,
                             width: float) -> Tuple[Point, Point]:
    """Build a finish line of the given width, centred on and perpendicular to a pose.

    Lets a track be described by nothing more than its start pose, which is how
    tracks.yaml defines them when no explicit line is given.
    """
    half = width / 2.0
    # Perpendicular to the heading, so the car crosses it head-on.
    nx, ny = -math.sin(theta), math.cos(theta)
    return ((x - half * nx, y - half * ny),
            (x + half * nx, y + half * ny))
