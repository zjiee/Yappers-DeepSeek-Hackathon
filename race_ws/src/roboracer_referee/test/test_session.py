"""Rule tests for the referee's scoring logic.

Run inside the container with:  colcon test --packages-select roboracer_referee
or directly with:               python3 race_ws/src/roboracer_referee/test/test_session.py

No ROS and no simulator: the session is fed the same telemetry the AutoDRIVE
bridge publishes, as plain numbers.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from roboracer_referee.session import (           # noqa: E402
    RaceSession, Rules, Status,
)


class Simulator:
    """A stand-in for the AutoDRIVE Simulator's race telemetry.

    It publishes exactly what the real one does: cumulative lap and collision
    counters, the elapsed time of the current lap, and the time of the last one
    that closed. The counters deliberately do not start at zero, because in a
    real run they do not either - the referee baselines them at the green flag.
    """

    def __init__(self, lap_count=7, collision_count=3, speed=4.0):
        self.lap_count = lap_count
        self.collision_count = collision_count
        self.lap_time = 0.0
        self.last_lap_time = 0.0
        self.speed = speed
        self.race_time = 0.0

    def tick(self, dt=0.025):
        self.lap_time += dt
        self.race_time += dt

    def close_lap(self, lap_time):
        self.last_lap_time = lap_time
        self.lap_count += 1
        self.lap_time = 0.0

    def collide(self, count=1):
        self.collision_count += count

    def feed(self, session):
        return session.update(self.lap_time, self.lap_count, self.last_lap_time,
                              self.collision_count, self.speed)


def start(session, sim):
    session.start(sim.lap_count, sim.collision_count)
    sim.feed(session)


def run_laps(session, sim, times, collisions_per_lap=()):
    """Drive a sequence of laps, colliding the given number of times on each."""
    collisions_per_lap = list(collisions_per_lap) + [0] * len(times)
    for lap_time, hits in zip(times, collisions_per_lap):
        for _ in range(hits):
            sim.collide()
            sim.feed(session)
        # Advance the simulator's clock through the lap, then close it.
        sim.lap_time = lap_time
        sim.race_time += lap_time
        sim.feed(session)
        sim.close_lap(lap_time)
        sim.feed(session)
        if session.finished:
            break


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_ten_clean_laps_score():
    session = RaceSession(Rules(timed_laps=10, warmup_laps=0))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [6.5] * 10)

    assert session.status is Status.COMPLETE, session.status
    assert session.scored
    assert session.timed_laps_done == 10
    assert session.collision_events == 0
    assert abs(session.total_time() - 65.0) < 1e-6, session.total_time()
    assert abs(session.best_lap().net_time - 6.5) < 1e-6


def test_cumulative_counters_are_baselined_not_assumed_zero():
    """A simulator that has already been driven must not hand the team free laps."""
    session = RaceSession(Rules(timed_laps=3, warmup_laps=0))
    sim = Simulator(lap_count=41, collision_count=9)
    start(session, sim)
    run_laps(session, sim, [5.0, 5.0, 5.0])

    assert session.timed_laps_done == 3
    assert session.collision_events == 0, "pre-existing collisions must not be scored"
    assert session.status is Status.COMPLETE


def test_best_lap_is_the_best_after_penalties():
    """The quickest lap as driven is not the quickest lap as scored."""
    session = RaceSession(Rules(timed_laps=3, warmup_laps=0, collision_penalty_s=10.0))
    sim = Simulator()
    start(session, sim)
    # Lap 2 is quickest on the road but picks up a collision doing it.
    run_laps(session, sim, [7.0, 6.0, 7.5], collisions_per_lap=[0, 1, 0])

    best = session.best_lap()
    assert best.number == 1, f"expected lap 1, got {best.number}"
    assert abs(best.net_time - 7.0) < 1e-6
    assert abs(session.total_time() - (7.0 + 16.0 + 7.5)) < 1e-6


# ---------------------------------------------------------------------------
# Collisions
# ---------------------------------------------------------------------------

def test_collision_adds_penalty_to_the_lap_it_happened_on():
    session = RaceSession(Rules(timed_laps=2, warmup_laps=0, collision_penalty_s=10.0))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [10.0, 10.0], collisions_per_lap=[2, 0])

    laps = session.timed()
    assert laps[0].collisions == 2 and abs(laps[0].penalty_s - 20.0) < 1e-6
    assert laps[1].collisions == 0 and laps[1].penalty_s == 0.0
    assert abs(session.total_time() - 40.0) < 1e-6


def test_exceeding_the_collision_limit_disqualifies():
    session = RaceSession(Rules(timed_laps=10, warmup_laps=0, max_collisions=3))
    sim = Simulator()
    start(session, sim)
    for _ in range(4):
        sim.collide()
        sim.feed(session)

    assert session.status is Status.DISQUALIFIED
    assert not session.scored
    assert session.total_time() is None
    assert session.result()["best_lap_time"] is None


def test_the_limit_itself_is_not_a_disqualification():
    session = RaceSession(Rules(timed_laps=1, warmup_laps=0, max_collisions=3))
    sim = Simulator()
    start(session, sim)
    for _ in range(3):
        sim.collide()
        sim.feed(session)
    assert session.status is Status.RUNNING
    run_laps(session, sim, [5.0])
    assert session.status is Status.COMPLETE


def test_several_collisions_between_two_samples_all_count():
    """The bridge publishes a counter, not an event, so a jump is real."""
    session = RaceSession(Rules(timed_laps=1, warmup_laps=0, max_collisions=10))
    sim = Simulator()
    start(session, sim)
    sim.collide(4)
    sim.feed(session)
    assert session.collision_events == 4


def test_a_counter_going_backwards_is_a_reset_not_a_credit():
    session = RaceSession(Rules(timed_laps=2, warmup_laps=0))
    sim = Simulator(collision_count=5)
    start(session, sim)
    sim.collide(2)
    sim.feed(session)
    assert session.collision_events == 2

    # The simulator was reset underneath the referee.
    sim.collision_count = 0
    sim.feed(session)
    assert session.collision_events == 2, "a reset must not refund collisions"
    sim.collide()
    sim.feed(session)
    assert session.collision_events == 3


# ---------------------------------------------------------------------------
# Warm-up laps
# ---------------------------------------------------------------------------

def test_warmup_laps_are_not_scored():
    session = RaceSession(Rules(timed_laps=2, warmup_laps=1))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [99.0, 5.0, 6.0])

    assert session.timed_laps_done == 2
    assert abs(session.total_time() - 11.0) < 1e-6, "the warm-up lap must not be in the total"
    assert session.best_lap().number == 1


def test_the_official_format_scores_laps_three_to_twelve():
    """Out lap and warm-up lap are driven and thrown away; ten laps are scored."""
    session = RaceSession(Rules())                      # official defaults
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [30.0, 25.0] + [20.0] * 10)  # 12 laps driven

    assert session.status is Status.COMPLETE
    assert session.timed_laps_done == 10
    assert abs(session.total_time() - 200.0) < 1e-6, "only the ten timed laps count"
    assert len(session.result()["warmup_laps"]) == 2


def test_collisions_on_a_warmup_lap_count_but_carry_no_penalty():
    session = RaceSession(Rules(timed_laps=1, warmup_laps=1, max_collisions=10))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [8.0, 5.0], collisions_per_lap=[2, 0])

    assert session.collision_events == 2, "they still count towards disqualification"
    assert session.result()["total_penalty_s"] == 0.0, "no scored lap to penalise"
    assert abs(session.total_time() - 5.0) < 1e-6


# ---------------------------------------------------------------------------
# Ending early
# ---------------------------------------------------------------------------

def test_a_stopped_car_is_a_dnf():
    session = RaceSession(Rules(timed_laps=10, warmup_laps=0, stuck_timeout_s=15.0))
    sim = Simulator(speed=0.0)
    start(session, sim)
    for _ in range(int(20.0 / 0.025)):
        sim.tick()
        sim.feed(session)
        if session.finished:
            break

    assert session.status is Status.DNF_STUCK
    assert not session.scored


def test_running_out_of_session_time_is_a_dnf():
    """Three 10 s laps fit inside a 35 s session; the fourth runs out of road."""
    session = RaceSession(Rules(timed_laps=10, warmup_laps=0, session_timeout_s=35.0))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [10.0, 10.0, 10.0, 10.0])

    assert session.status is Status.DNF_TIMEOUT
    assert not session.scored
    assert session.result()["laps_completed"] == 3, "the completed laps are still reported"
    assert session.race_time >= 35.0


def test_an_unfinished_run_scores_nothing():
    session = RaceSession(Rules(timed_laps=10, warmup_laps=0))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [5.0] * 9)
    session.abort("test")

    result = session.result()
    assert result["status"] == "ABORTED"
    assert result["scored"] is False
    assert result["best_lap_time"] is None and result["total_time"] is None
    assert result["laps_completed"] == 9, "the laps are still reported, just not scored"


# ---------------------------------------------------------------------------
# Telemetry the simulator should never send
# ---------------------------------------------------------------------------

def test_an_impossibly_short_lap_is_recorded_with_a_warning():
    session = RaceSession(Rules(timed_laps=1, warmup_laps=0, min_lap_time_s=1.0))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [0.01])

    assert session.status is Status.COMPLETE
    assert session.result()["warnings"], "a sub-minimum lap must be flagged"


def test_two_laps_closing_between_samples_is_flagged():
    session = RaceSession(Rules(timed_laps=5, warmup_laps=0))
    sim = Simulator()
    start(session, sim)
    sim.lap_count += 2
    sim.last_lap_time = 5.0
    sim.feed(session)

    assert session.result()["warnings"], "a skipped lap must be flagged, not invented"


def test_nothing_happens_before_the_green_flag():
    session = RaceSession(Rules())
    sim = Simulator()
    sim.collide(5)
    sim.close_lap(4.0)
    assert sim.feed(session) == []
    assert session.collision_events == 0
    assert session.timed_laps_done == 0
    assert session.status is Status.PENDING


# ---------------------------------------------------------------------------
# Rule validation
# ---------------------------------------------------------------------------

def test_invalid_rules_are_rejected():
    for bad in (Rules(timed_laps=0), Rules(collision_penalty_s=-1.0),
                Rules(session_timeout_s=0.0), Rules(warmup_laps=-1),
                Rules(min_lap_time_s=-1.0), Rules(stuck_timeout_s=0.0)):
        try:
            RaceSession(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} should have been rejected")


def test_the_official_defaults_match_track_1():
    rules = Rules()
    assert rules.timed_laps == 10
    assert rules.collision_penalty_s == 10.0
    assert rules.max_collisions == 10, "more than ten contacts is a disqualification"
    assert rules.warmup_laps == 2, "an out lap and a warm-up lap, neither scored"
    assert rules.session_timeout_s == 900.0


def test_the_default_limit_stops_a_scruffy_run():
    """Eleven collisions ends the run there and then, mid-lap."""
    session = RaceSession(Rules(timed_laps=10, warmup_laps=0))   # official defaults
    sim = Simulator()
    start(session, sim)
    for i in range(1, 12):
        sim.collide()
        sim.feed(session)
        if i <= 10:
            assert session.status is Status.RUNNING, f"DQ fired early at {i}"
    assert session.status is Status.DISQUALIFIED
    assert session.collision_events == 11
    assert session.timed_laps_done == 0, "the run ended before the lap closed"
    assert not session.scored
    assert session.result()["collision_limit"] == 10


def test_a_negative_limit_disables_disqualification():
    """The escape hatch: a scruffy run finishes and is ranked."""
    session = RaceSession(Rules(timed_laps=2, warmup_laps=0, max_collisions=-1))
    sim = Simulator()
    start(session, sim)
    run_laps(session, sim, [20.0, 20.0], collisions_per_lap=[40, 40])

    assert session.status is Status.COMPLETE
    assert session.collision_events == 80
    assert session.result()["collision_limit"] is None
    assert abs(session.total_time() - (40.0 + 80 * 10.0)) < 1e-6


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:                      # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
