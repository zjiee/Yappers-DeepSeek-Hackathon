#!/usr/bin/env python3
"""Turn referee result files into the official leaderboard.

    # What a set of runs produced
    ./scripts/leaderboard.py summarise results/*.json

    # The leaderboard: best run per team, normalised, ranked
    ./scripts/leaderboard.py rank results/
    ./scripts/leaderboard.py rank results/ --csv leaderboard.csv --json leaderboard.json

Scoring, per docs/06-rules.md:

    lap score        = 50 * (fastest single lap of any team / this team's fastest lap)
    endurance score  = 50 * (fastest 10-lap total of any team / this team's 10-lap total)
    total            = lap score + endurance score, out of 100

Both halves already include
those penalties, because the referee applies them to the lap times before they
reach this file. A team that was disqualified or did not finish scores zero and
is listed separately.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from typing import Dict, List, Optional

LAP_WEIGHT = 50.0
ENDURANCE_WEIGHT = 50.0


def load_results(paths: List[str]) -> List[dict]:
    """Read every result file named, expanding directories and globs."""
    files: List[str] = []
    for path in paths:
        if os.path.isdir(path):
            files.extend(sorted(glob.glob(os.path.join(path, "*.json"))))
        elif any(ch in path for ch in "*?["):
            files.extend(sorted(glob.glob(path)))
        else:
            files.append(path)

    results = []
    for path in files:
        try:
            with open(path, "r") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warn: skipping {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, dict) or "status" not in data:
            print(f"warn: skipping {path}: not a referee result file", file=sys.stderr)
            continue
        data["_path"] = path
        results.append(data)
    return results


def _min_positive(values) -> Optional[float]:
    """Smallest usable time, ignoring zero, negative and missing ones.

    A single corrupt result file should cost that one entry its score, not
    flatten the normalisers and take the whole leaderboard to zero with it.
    """
    usable = [v for v in values if v is not None and 0.0 < v < float("inf")]
    return min(usable) if usable else None


def _field_bests(results: List[dict]):
    """Normalisers taken across every scored run, not just the ones already picked.

    Choosing a team's best run needs a score, and a score needs normalisers, so
    taking them from the chosen runs would make the choice depend on itself.
    Across all runs they are fixed before any choosing starts.
    """
    scored = [r for r in results if r.get("scored")]
    if not scored:
        return None, None
    return (_min_positive(_best_lap(r) for r in scored),
            _min_positive(_total(r) for r in scored))


def _score(result: dict, fastest_lap: float, fastest_total: float) -> float:
    """Rule 19: both halves, 50 points each, relative to the best of the field."""
    lap, total = _best_lap(result), _total(result)
    if fastest_lap is None or fastest_total is None:
        return 0.0
    if not (lap > 0.0 and total > 0.0):
        return 0.0
    return LAP_WEIGHT * fastest_lap / lap + ENDURANCE_WEIGHT * fastest_total / total


def best_run_per_team(results: List[dict]) -> Dict[str, dict]:
    """Keep each team's best scored run; fall back to any run so DQs still show.

    "Best" is the run that scores highest under rule 19 - both halves of it.
    Judging races each entry three times (rule 23), and a team can easily set
    its quickest lap in one run and its best 10-lap total in another; picking
    on the 10-lap total alone would throw away the lap half of their score and
    can cost a place on the leaderboard.
    """
    fastest_lap, fastest_total = _field_bests(results)

    by_team: Dict[str, List[dict]] = {}
    for result in results:
        by_team.setdefault(str(result.get("team", "unknown")), []).append(result)

    def preference(result: dict):
        score = (_score(result, fastest_lap, fastest_total)
                 if result.get("scored") else 0.0)
        # Scored beats unscored, then the score, then the 10-lap total as the
        # tie-break, then run_id so the answer never depends on file order.
        return (1 if result.get("scored") else 0,
                score,
                -_total(result),
                str(result.get("run_id", "")))

    return {team: max(runs, key=preference) for team, runs in by_team.items()}


def _total(result: dict) -> float:
    value = result.get("total_time")
    return float(value) if value is not None else float("inf")


def _best_lap(result: dict) -> float:
    value = result.get("best_lap_time")
    return float(value) if value is not None else float("inf")


def rank(results: List[dict]) -> dict:
    best = best_run_per_team(results)
    scored = {team: r for team, r in best.items() if r.get("scored")}
    unscored = {team: r for team, r in best.items() if not r.get("scored")}

    tracks = {str(r.get("track")) for r in best.values()}
    warnings = []
    if len(tracks) > 1:
        warnings.append(
            "Runs span more than one track (" + ", ".join(sorted(tracks))
            + "). Times from different tracks are not comparable."
        )

    rows = []
    if scored:
        fastest_lap = _min_positive(_best_lap(r) for r in scored.values())
        fastest_total = _min_positive(_total(r) for r in scored.values())
        for team, result in scored.items():
            lap = _best_lap(result)
            total = _total(result)
            lap_score = (LAP_WEIGHT * fastest_lap / lap
                         if fastest_lap is not None and lap > 0.0 else 0.0)
            endurance_score = (ENDURANCE_WEIGHT * fastest_total / total
                               if fastest_total is not None and total > 0.0 else 0.0)
            rows.append({
                "team": team,
                "status": result["status"],
                "best_lap_time": round(_best_lap(result), 3),
                "total_time": round(_total(result), 3),
                "collisions": result.get("collisions", 0),
                "penalty_s": result.get("total_penalty_s", 0.0),
                "lap_score": round(lap_score, 3),
                "endurance_score": round(endurance_score, 3),
                "total_score": round(lap_score + endurance_score, 3),
                "run_id": result.get("run_id", ""),
                "track": result.get("track", ""),
                "source": os.path.basename(result.get("_path", "")),
            })
        # Ties break on the 10-lap total, then on the team name, so the order
        # is the same however the result files happened to be listed.
        rows.sort(key=lambda row: (-row["total_score"], row["total_time"], row["team"]))

    for team, result in sorted(unscored.items()):
        rows.append({
            "team": team,
            "status": result["status"],
            "best_lap_time": None,
            "total_time": None,
            "collisions": result.get("collisions", 0),
            "penalty_s": result.get("total_penalty_s", 0.0),
            "lap_score": 0.0,
            "endurance_score": 0.0,
            "total_score": 0.0,
            "run_id": result.get("run_id", ""),
            "track": result.get("track", ""),
            "source": os.path.basename(result.get("_path", "")),
        })

    for position, row in enumerate(rows, start=1):
        row["rank"] = position if row["total_score"] > 0 else None

    return {
        "rows": rows,
        "teams": len(best),
        "scored_teams": len(scored),
        "runs_considered": len(results),
        "tracks": sorted(tracks),
        "warnings": warnings,
    }


def _fmt(value, spec="{:.3f}", dash="-"):
    return dash if value is None else spec.format(value)


def _status_icon(status: str) -> str:
    return {"COMPLETE": "\u2705"}.get(status, "\u274c")


def render_markdown(table: dict, title: str = "Leaderboard") -> str:
    """GitHub-flavoured Markdown, for a workflow job summary."""
    out = [f"## {title}", ""]
    for warning in table["warnings"]:
        out += ["> [!WARNING]", f"> {warning}", ""]

    if not table["rows"]:
        out += ["No runs were scored.", ""]
        return "\n".join(out)

    out += ["| # | Team | Best lap | 10 laps | Collisions | Lap pts | Endurance pts | **Total** | Status |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in table["rows"]:
        position = str(row["rank"]) if row["rank"] else "-"
        out.append(
            f"| {position} | {row['team']} "
            f"| {_fmt(row['best_lap_time'])} | {_fmt(row['total_time'])} "
            f"| {row['collisions']} "
            f"| {row['lap_score']:.2f} | {row['endurance_score']:.2f} "
            f"| **{row['total_score']:.2f}** "
            f"| {_status_icon(row['status'])} {row['status']} |"
        )
    out += ["",
            f"{table['scored_teams']} of {table['teams']} scored, from "
            f"{table['runs_considered']} run(s) on {', '.join(table['tracks'])}.",
            ""]
    return "\n".join(out)


def render_runs_markdown(results: List[dict], title: str = "Runs") -> str:
    """Per-run detail, including the lap-by-lap breakdown of the best run."""
    out = [f"## {title}", "",
           "| Run | Status | Laps | Collisions | Penalty | Best lap | Total |",
           "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for result in sorted(results, key=lambda r: str(r.get("run_id", ""))):
        out.append(
            f"| `{result.get('run_id', '')}` "
            f"| {_status_icon(result['status'])} {result['status']} "
            f"| {result.get('laps_completed', 0)}/{result.get('laps_required', 0)} "
            f"| {result.get('collisions', 0)} "
            f"| {result.get('total_penalty_s', 0):.0f}s "
            f"| {_fmt(result.get('best_lap_time'))} "
            f"| {_fmt(result.get('total_time'))} |"
        )
    out.append("")

    scored = [r for r in results if r.get("scored")]
    if scored:
        best = min(scored, key=_total)
        laps = best.get("laps") or []
        if laps:
            out += [f"<details><summary>Lap times for the best run "
                    f"(<code>{best.get('run_id', '')}</code>)</summary>", "",
                    "| Lap | Raw | Penalty | Net |", "| ---: | ---: | ---: | ---: |"]
            out += [f"| {lap['number']} | {lap['raw_time']:.3f} "
                    f"| {lap['penalty_s']:.0f} | {lap['net_time']:.3f} |" for lap in laps]
            out += ["", "</details>", ""]

    rtfs = [r["environment"]["real_time_factor"] for r in results
            if r.get("environment", {}).get("real_time_factor") is not None]
    if rtfs:
        out += [f"Real-time factor: {min(rtfs):.2f}x to {max(rtfs):.2f}x. "
                "Lap times are in simulated seconds, so this does not affect scores.",
                ""]
    return "\n".join(out)


def cmd_rank(args) -> int:
    results = load_results(args.paths)
    if not results:
        print("No result files found.", file=sys.stderr)
        return 1

    table = rank(results)
    if args.markdown:
        print(render_markdown(table, args.title or "Leaderboard"))
        return 0

    for warning in table["warnings"]:
        print(f"warning: {warning}\n", file=sys.stderr)

    header = (f"{'#':>3}  {'team':<22} {'best lap':>9} {'10 laps':>10} "
              f"{'coll':>5} {'lap':>7} {'end':>7} {'TOTAL':>8}  status")
    print(header)
    print("-" * len(header))
    for row in table["rows"]:
        position = f"{row['rank']:>3}" if row["rank"] else "  -"
        print(f"{position}  {row['team'][:22]:<22} "
              f"{_fmt(row['best_lap_time']):>9} {_fmt(row['total_time']):>10} "
              f"{row['collisions']:>5} "
              f"{row['lap_score']:>7.2f} {row['endurance_score']:>7.2f} "
              f"{row['total_score']:>8.2f}  {row['status']}")
    print("-" * len(header))
    print(f"{table['scored_teams']} of {table['teams']} team(s) scored, "
          f"from {table['runs_considered']} run(s) on {', '.join(table['tracks'])}.")

    if args.json:
        with open(args.json, "w") as handle:
            json.dump(table, handle, indent=2)
            handle.write("\n")
        print(f"Wrote {args.json}")

    if args.csv:
        fields = ["rank", "team", "status", "best_lap_time", "total_time", "collisions",
                  "penalty_s", "lap_score", "endurance_score", "total_score",
                  "track", "run_id", "source"]
        with open(args.csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in table["rows"]:
                writer.writerow({key: row.get(key) for key in fields})
        print(f"Wrote {args.csv}")
    return 0


def cmd_summarise(args) -> int:
    results = load_results(args.paths)
    if not results:
        print("No result files found.", file=sys.stderr)
        return 1

    if args.markdown:
        print(render_runs_markdown(results, args.title or "Runs"))
        return 0

    header = (f"{'run':<28} {'status':<14} {'laps':>6} {'coll':>5} "
              f"{'best lap':>9} {'total':>10}")
    print(header)
    print("-" * len(header))
    for result in sorted(results, key=lambda r: str(r.get("run_id", ""))):
        print(f"{str(result.get('run_id', ''))[:28]:<28} "
              f"{result['status']:<14} "
              f"{result.get('laps_completed', 0):>3}/{result.get('laps_required', 0):<2} "
              f"{result.get('collisions', 0):>5} "
              f"{_fmt(result.get('best_lap_time')):>9} "
              f"{_fmt(result.get('total_time')):>10}")
    print("-" * len(header))

    scored = [r for r in results if r.get("scored")]
    if scored:
        fastest = min(scored, key=_total)
        print(f"Best run: {fastest.get('run_id')} - "
              f"fastest lap {_fmt(fastest.get('best_lap_time'))}s, "
              f"{fastest.get('laps_required')}-lap total {_fmt(fastest.get('total_time'))}s")
        print(f"          {fastest.get('_path', '')}")
    else:
        print("No run was scored. Check the referee output for the reason "
              "(disqualified, did not finish, or the driver never started).")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    ranker = sub.add_parser("rank", help="build the leaderboard from result files")
    ranker.add_argument("paths", nargs="+", help="result files, globs, or directories")
    ranker.add_argument("--csv", help="also write the table as CSV")
    ranker.add_argument("--json", help="also write the table as JSON")
    ranker.add_argument("--markdown", action="store_true",
                        help="emit GitHub-flavoured Markdown instead of a text table")
    ranker.add_argument("--title", help="heading for the Markdown output")
    ranker.set_defaults(func=cmd_rank)

    summary = sub.add_parser("summarise", help="list individual runs")
    summary.add_argument("paths", nargs="+", help="result files, globs, or directories")
    summary.add_argument("--markdown", action="store_true",
                         help="emit GitHub-flavoured Markdown instead of a text table")
    summary.add_argument("--title", help="heading for the Markdown output")
    summary.set_defaults(func=cmd_summarise)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
