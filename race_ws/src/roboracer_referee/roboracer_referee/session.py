"""Lap timing, penalties and scoring for a single evaluation run.

This module deliberately contains no ROS code. The referee node feeds it the
AutoDRIVE Simulator's race telemetry; everything about *what a lap is worth*
lives here, so the rules can be unit tested without standing up a simulator.

Track 2 does not time laps itself. The AutoDRIVE Simulator owns the
start/finish line and the track boundaries, and reports lap count, lap times
and a collision count over the devkit bridge. Those numbers are the ground
truth a scored run is built from - see docs/05-evaluation.md - which is why
there is no finish-line geometry anywhere in this package.

All times are the simulator's own, never the referee's wall clock.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import List, Optional


class Status(str, Enum):
    """Terminal state of a run. The string values go straight into the result file."""

    PENDING = "PENDING"                # waiting for the green flag
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"              # all timed laps finished
    DISQUALIFIED = "DISQUALIFIED"      # collision limit exceeded
    DNF_TIMEOUT = "DNF_TIMEOUT"        # ran out of session time
    DNF_STUCK = "DNF_STUCK"            # car stopped moving
    ABORTED = "ABORTED"                # operator interrupt or crashed driver


@dataclass
class Rules:
    """The scoring rules. Defaults are the official Track 2 settings."""

    # Unscored laps before timing starts: the out lap and the warm-up lap, as
    # on Track 1. The simulator spawns the car most of a circuit before its own
    # start/finish line, so the run from the grid closes as a lap in its own
    # right - it is the out lap, and the granted warm-up lap follows it.
    warmup_laps: int = 2
    timed_laps: int = 10
    collision_penalty_s: float = 10.0  # added to the lap the collision happened on
    max_collisions: int = 10           # strictly more than this disqualifies
    # A negative value disables the limit entirely, for an organiser who wants
    # a run to finish and be ranked however scruffy it was. Not the default:
    # a car that has hit the boundary eleven times is not racing any more.
    min_lap_time_s: float = 1.0        # a "lap" quicker than this is telemetry noise
    session_timeout_s: float = 900.0
    stuck_speed_mps: float = 0.05
    stuck_timeout_s: float = 15.0

    def validate(self) -> None:
        problems = []
        if self.warmup_laps < 0:
            problems.append("warmup_laps must be >= 0")
        if self.timed_laps < 1:
            problems.append("timed_laps must be >= 1")
        if self.collision_penalty_s < 0:
            problems.append("collision_penalty_s must be >= 0")
        if self.min_lap_time_s < 0:
            problems.append("min_lap_time_s must be >= 0")
        if self.session_timeout_s <= 0:
            problems.append("session_timeout_s must be > 0")
        if self.stuck_timeout_s <= 0:
            problems.append("stuck_timeout_s must be > 0")
        if problems:
            raise ValueError("Invalid referee rules: " + "; ".join(problems))


@dataclass
class Lap:
    number: int                  # 1-based within its own kind
    kind: str                    # "warmup" or "timed"
    raw_time: float              # as reported by the simulator
    collisions: int = 0
    penalty_s: float = 0.0

    @property
    def net_time(self) -> float:
        """Lap time as scored: what was driven, plus the collision penalties."""
        return self.raw_time + self.penalty_s


class RaceSession:
    """Drives one evaluation run from the simulator's race telemetry.

    The counters the simulator publishes are cumulative and are not necessarily
    zero when the green flag drops - a reset may not have landed yet, and a
    practice run may have been driven in the same simulator session. So the
    session takes a baseline at the green flag and scores deltas from it,
    which makes it correct either way.
    """

    def __init__(self, rules: Rules):
        rules.validate()
        self.rules = rules

        self.status = Status.PENDING
        self.laps: List[Lap] = []
        self.collision_events: int = 0

        self._lap_baseline: Optional[int] = None
        self._collision_baseline: Optional[int] = None
        self._laps_closed: int = 0
        self._current_lap_collisions: int = 0
        self._race_time: float = 0.0
        self._below_speed_since: Optional[float] = None
        self._finish_reason: str = ""
        self._warnings: List[str] = []

    # -- lifecycle ---------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.status not in (Status.PENDING, Status.RUNNING)

    @property
    def started(self) -> bool:
        return self._lap_baseline is not None

    @property
    def timed_laps_done(self) -> int:
        return sum(1 for lap in self.laps if lap.kind == "timed")

    @property
    def race_time(self) -> float:
        """Elapsed simulated seconds since the green flag."""
        return self._race_time

    def _finish(self, status: Status, reason: str) -> None:
        if self.finished:
            return
        self.status = status
        self._finish_reason = reason

    def abort(self, reason: str = "operator interrupt") -> None:
        self._finish(Status.ABORTED, reason)

    def start(self, lap_count: int, collision_count: int) -> None:
        """Drop the green flag, baselining the simulator's cumulative counters."""
        if self.started:
            return
        self._lap_baseline = int(lap_count)
        self._collision_baseline = int(collision_count)
        self.status = Status.RUNNING

    # -- inputs ------------------------------------------------------------

    def update(self, current_lap_time: float, lap_count: int, last_lap_time: float,
               collision_count: int, speed_mps: float) -> List[str]:
        """Feed one telemetry sample. Returns human-readable events for logging.

        `current_lap_time` is the simulator's elapsed time for the lap in
        progress. The race clock is rebuilt from the laps already closed plus
        that, rather than accumulated here, so it stays exact across a lap
        boundary - where the simulator resets its lap timer to zero in the same
        frame that it reports the finished lap's duration.
        """
        events: List[str] = []
        if self.finished or not self.started:
            return events

        events.extend(self._check_collisions(collision_count))
        events.extend(self._check_laps(lap_count, last_lap_time))

        closed = sum(lap.raw_time for lap in self.laps)
        if math.isfinite(current_lap_time) and current_lap_time > 0.0:
            closed += current_lap_time
        self._race_time = max(self._race_time, closed)

        self._check_stuck(speed_mps)
        self._check_timeout()
        return events

    # -- internals ---------------------------------------------------------

    def _check_collisions(self, collision_count: int) -> List[str]:
        """Count what the simulator counted, and no more.

        Track 1 had to debounce a raw contact flag that fired on every physics
        step. AutoDRIVE publishes an already-debounced counter, so a collision
        here is one collision as the simulator itself scored it - the same
        number the ICRA leaderboard reports.
        """
        events: List[str] = []
        assert self._collision_baseline is not None

        total = int(collision_count) - self._collision_baseline
        if total <= self.collision_events:
            # Counters only go up. A drop means the simulator was reset under
            # us; re-baseline rather than scoring a negative collision.
            if total < 0:
                self._collision_baseline = int(collision_count) - self.collision_events
            return events

        new = total - self.collision_events
        self.collision_events = total
        self._current_lap_collisions += new
        limit = (f"/{self.rules.max_collisions}" if self.rules.max_collisions >= 0 else "")
        events.append(
            f"COLLISION {self.collision_events}{limit} "
            f"(+{new * self.rules.collision_penalty_s:.0f}s on this lap)"
        )

        if 0 <= self.rules.max_collisions < self.collision_events:
            self._finish(
                Status.DISQUALIFIED,
                f"{self.collision_events} collisions exceeds the limit of "
                f"{self.rules.max_collisions}",
            )
        return events

    def _check_laps(self, lap_count: int, last_lap_time: float) -> List[str]:
        events: List[str] = []
        assert self._lap_baseline is not None

        completed = int(lap_count) - self._lap_baseline
        if completed <= self._laps_closed:
            if completed < 0:
                self._lap_baseline = int(lap_count) - self._laps_closed
            return events

        if completed - self._laps_closed > 1:
            # The simulator only reports the time of the *last* lap, so several
            # laps closing between two samples would lose the earlier ones. At
            # 40 Hz telemetry against multi-second laps this cannot happen
            # honestly; say so rather than inventing times.
            self._warn(
                f"{completed - self._laps_closed} laps closed between two telemetry "
                f"samples; only the most recent lap time is recoverable."
            )

        raw = float(last_lap_time)
        if not math.isfinite(raw) or raw < self.rules.min_lap_time_s:
            self._warn(
                f"The simulator reported a lap time of {last_lap_time} s, which is "
                f"below min_lap_time_s ({self.rules.min_lap_time_s:.1f} s). "
                f"Recorded as-is; treat this run with suspicion."
            )
            raw = max(0.0, raw if math.isfinite(raw) else 0.0)

        self._laps_closed = completed
        collisions = self._current_lap_collisions
        self._current_lap_collisions = 0

        if self._laps_closed <= self.rules.warmup_laps:
            self.laps.append(Lap(number=self._laps_closed, kind="warmup",
                                 raw_time=raw, collisions=collisions, penalty_s=0.0))
            events.append(
                f"Unscored lap {self._laps_closed}/{self.rules.warmup_laps}: "
                f"{raw:.3f}s (not scored)."
            )
            if self._laps_closed == self.rules.warmup_laps:
                events.append("Timing starts now.")
            return events

        number = self.timed_laps_done + 1
        penalty = collisions * self.rules.collision_penalty_s
        lap = Lap(number=number, kind="timed", raw_time=raw,
                  collisions=collisions, penalty_s=penalty)
        self.laps.append(lap)

        suffix = f" (+{penalty:.0f}s from {collisions} collision(s))" if penalty else ""
        events.append(
            f"Lap {number}/{self.rules.timed_laps}: {raw:.3f}s -> {lap.net_time:.3f}s{suffix}"
        )

        if self.timed_laps_done >= self.rules.timed_laps:
            self._finish(Status.COMPLETE, "all timed laps completed")
            events.append("Run complete.")
        return events

    def _check_stuck(self, speed_mps: float) -> None:
        if not math.isfinite(speed_mps) or abs(speed_mps) > self.rules.stuck_speed_mps:
            self._below_speed_since = None
            return
        if self._below_speed_since is None:
            self._below_speed_since = self._race_time
        elif self._race_time - self._below_speed_since >= self.rules.stuck_timeout_s:
            self._finish(
                Status.DNF_STUCK,
                f"car did not move for {self.rules.stuck_timeout_s:.0f}s of simulated time",
            )

    def _check_timeout(self) -> None:
        if self._race_time >= self.rules.session_timeout_s:
            self._finish(
                Status.DNF_TIMEOUT,
                f"session time limit of {self.rules.session_timeout_s:.0f}s reached "
                f"after {self.timed_laps_done}/{self.rules.timed_laps} timed laps",
            )

    def _warn(self, message: str) -> None:
        if message not in self._warnings:
            self._warnings.append(message)

    # -- results -----------------------------------------------------------

    @property
    def scored(self) -> bool:
        """Whether this run produces leaderboard times at all."""
        return self.status is Status.COMPLETE

    def timed(self) -> List[Lap]:
        return [lap for lap in self.laps if lap.kind == "timed"]

    def best_lap(self) -> Optional[Lap]:
        """The best lap *as scored* - net of penalties, which is what counts."""
        timed = self.timed()
        return min(timed, key=lambda lap: lap.net_time) if timed else None

    def fastest_raw_lap(self) -> Optional[Lap]:
        """The quickest lap as driven, ignoring penalties.

        Not scored, but it is the number the simulator itself reports as the
        best lap, so keeping it makes the two independently checkable. A lap
        can be the quickest on the road and not the best lap of the run, if it
        picked up a collision doing it.
        """
        timed = self.timed()
        return min(timed, key=lambda lap: lap.raw_time) if timed else None

    def total_time(self) -> Optional[float]:
        """Net time for the full set of timed laps, or None if not completed."""
        if not self.scored:
            return None
        return sum(lap.net_time for lap in self.timed())

    def result(self) -> dict:
        best = self.best_lap()
        fastest_raw = self.fastest_raw_lap()
        timed = self.timed()
        return {
            "status": self.status.value,
            "reason": self._finish_reason,
            "scored": self.scored,
            "rules": asdict(self.rules),
            "laps_completed": len(timed),
            "laps_required": self.rules.timed_laps,
            "collisions": self.collision_events,
            "collision_limit": (self.rules.max_collisions
                                if self.rules.max_collisions >= 0 else None),
            "best_lap_time": round(best.net_time, 4) if best and self.scored else None,
            "best_lap_time_raw": round(best.raw_time, 4) if best and self.scored else None,
            "best_lap_number": best.number if best and self.scored else None,
            # The quickest lap as driven. Reported always, scored never - it is
            # what the simulator's own best_lap_time should agree with.
            "fastest_raw_lap_time": (round(fastest_raw.raw_time, 4)
                                     if fastest_raw else None),
            "fastest_raw_lap_number": fastest_raw.number if fastest_raw else None,
            "total_time": round(self.total_time(), 4) if self.total_time() is not None else None,
            "total_time_raw": (round(sum(lap.raw_time for lap in timed), 4)
                               if self.scored else None),
            "total_penalty_s": round(sum(lap.penalty_s for lap in timed), 4),
            "race_time_s": round(self._race_time, 4),
            "warnings": list(self._warnings),
            "laps": [
                {
                    "number": lap.number,
                    "raw_time": round(lap.raw_time, 4),
                    "collisions": lap.collisions,
                    "penalty_s": round(lap.penalty_s, 4),
                    "net_time": round(lap.net_time, 4),
                }
                for lap in timed
            ],
            "warmup_laps": [
                {"number": lap.number, "raw_time": round(lap.raw_time, 4),
                 "collisions": lap.collisions}
                for lap in self.laps if lap.kind == "warmup"
            ],
        }
