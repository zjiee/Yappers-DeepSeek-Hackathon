#!/usr/bin/env python3
"""Scoring tests for leaderboard.py.

These guard the arithmetic in docs/06-rules.md and, above all, the choice of
which of a team's judged runs is scored. Judging races every entry three times
and keeps the best attempt; "best" has to mean best *score*, both halves of it.
Deciding it on the 10-lap total alone silently discards the lap half and can
cost a team a place.

    ./scripts/test_leaderboard.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import leaderboard                                          # noqa: E402


def run(team, best_lap, total, run_id="r1", status="COMPLETE", scored=True):
    return {
        "team": team, "run_id": f"{team}-{run_id}", "track": "icra26_compete",
        "status": status, "scored": scored,
        "laps_completed": 10, "laps_required": 10, "collisions": 0,
        "best_lap_time": best_lap, "total_time": total,
        "total_penalty_s": 0.0, "laps": [],
    }


def scores(results):
    return {row["team"]: row for row in leaderboard.rank(results)["rows"]}


def test_worked_example_from_the_rules():
    """The table in docs/06-rules.md 6.5, to the hundredth."""
    table = scores([run("Alpha", 21.80, 228.90),
                    run("Bravo", 20.50, 245.00),
                    run("Charlie", 25.00, 260.00)])
    for team, lap, end, total in (("Alpha", 47.02, 50.00, 97.02),
                                  ("Bravo", 50.00, 46.71, 96.71),
                                  ("Charlie", 41.00, 44.02, 85.02)):
        assert round(table[team]["lap_score"], 2) == lap, (team, table[team])
        assert round(table[team]["endurance_score"], 2) == end, (team, table[team])
        assert round(table[team]["total_score"], 2) == total, (team, table[team])


def test_best_attempt_uses_both_halves_of_the_score():
    """Rule 23 with rule 19: the kept run is the one that scores highest.

    Delta's run1 is a tenth of a second slower over ten laps but five seconds
    quicker on its best lap. Choosing on the 10-lap total would field run3 and
    drop Delta below Rival.
    """
    results = [
        run("Pacesetter", 20.00, 225.00),          # sets both normalisers
        run("Rival", 21.00, 232.00),
        run("Delta", 20.00, 230.00, "run1"),
        run("Delta", 20.00, 230.50, "run2"),
        run("Delta", 25.00, 229.00, "run3"),
    ]
    table = scores(results)
    assert table["Delta"]["run_id"] == "Delta-run1", table["Delta"]["run_id"]
    assert round(table["Delta"]["total_score"], 2) == 98.91, table["Delta"]
    assert table["Delta"]["rank"] < table["Rival"]["rank"]


def test_a_scored_run_beats_an_unscored_one():
    table = scores([run("Echo", None, None, "dq", status="DISQUALIFIED", scored=False),
                    run("Echo", 22.0, 240.0, "ok")])
    assert table["Echo"]["status"] == "COMPLETE"
    assert table["Echo"]["run_id"] == "Echo-ok"


def test_a_team_with_no_scored_run_scores_zero():
    table = scores([run("Foxtrot", None, None, status="DNF_STUCK", scored=False)])
    assert table["Foxtrot"]["total_score"] == 0.0
    assert table["Foxtrot"]["rank"] is None


def test_ties_break_on_the_ten_lap_total():
    """Equal totals must not be settled by whichever file was read first."""
    table = scores([run("Alpha", 10.0, 200.0), run("Zulu", 20.0, 100.0)])
    assert round(table["Alpha"]["total_score"], 2) == round(table["Zulu"]["total_score"], 2)
    assert table["Zulu"]["rank"] < table["Alpha"]["rank"], table


def test_selection_does_not_depend_on_file_order():
    results = [
        run("Pacesetter", 20.00, 225.00),
        run("Delta", 20.00, 230.00, "run1"),
        run("Delta", 25.00, 229.00, "run3"),
    ]
    first = scores(results)["Delta"]["run_id"]
    second = scores(list(reversed(results)))["Delta"]["run_id"]
    assert first == second == "Delta-run1", (first, second)


def test_a_zero_lap_time_does_not_crash_the_leaderboard():
    table = scores([run("Glitch", 0.0, 0.0), run("Normal", 20.0, 210.0)])
    assert table["Glitch"]["total_score"] == 0.0
    assert table["Normal"]["rank"] == 1


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:                        # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
