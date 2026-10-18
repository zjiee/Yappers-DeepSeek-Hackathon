# 5. Evaluation

The judging environment is in this repository. The script that scores you on
judging day is the same one you can run right now, against the same referee
with the same settings. There are no surprises on the day.

---

## 5.1 Score yourself

```sh
# From the host, with the container running
./scripts/evaluate.sh --team your_team_name
```

That builds the workspace, starts the simulator and the devkit bridge, starts
your driver, runs the full race format and writes a result file to `results/`.

Keep the result files from your final runs. Committing them is part of a
submission — see [§7.1](07-submission.md#71-what-to-submit).

Useful variations:

```sh
# Three runs, keep the best — this is what the judges do
./scripts/evaluate.sh --team your_team --runs 3

# A short run while you are iterating
./scripts/evaluate.sh --team your_team --laps 3

# Watch it: renders the simulator and opens RViz
./scripts/evaluate.sh --team your_team --laps 3 --graphics

# Against a simulator you started yourself (macOS, Windows, another machine)
./scripts/evaluate.sh --team your_team --no-simulator

# Score an alternative executable of your own, side by side with `driver`
./scripts/evaluate.sh --team my_experiment --driver-exec my_other_node
```

Runs are **headless by default** — no window, no graphics device — because that
is what judging uses and it is much faster. `--graphics` is for watching.
`./scripts/evaluate.sh --help` lists every option.

The script works from your host (it hops into the container for you) or from
inside the container directly.

---

## 5.2 The race format

| | |
| --- | --- |
| Out lap | From the grid slot to the start/finish line. Not timed. |
| Warm-up lap | One full lap, granted, not scored. |
| Timed laps | 10 consecutive laps. |
| Collision | +10 s added to the lap it happened on. |
| Disqualification | More than 10 collisions in a run. |

Two numbers come out:

- **Best lap** — your fastest single timed lap, including its penalties.
- **10-lap total** — the sum of all ten timed laps, including penalties.

The scoring formula that turns those into leaderboard points is in
[chapter 6](06-rules.md).

Twelve laps are driven and ten are scored. The out lap is a full circuit here
rather than the short run-up it is on Track 1, because the simulator spawns the
car most of a lap before its own start/finish line — so the standing start is
absorbed by a lap nobody scores.

A run can also end early:

| Status | Means |
| --- | --- |
| `COMPLETE` | All 10 laps finished. This is the only status that scores. |
| `DISQUALIFIED` | More than 10 collisions. |
| `DNF_TIMEOUT` | Ran out of session time (900 simulated seconds) before 10 laps. |
| `DNF_STUCK` | The car did not move for 15 simulated seconds. |
| `ABORTED` | Interrupted, or the referee never got as far as racing. |

---

## 5.3 The simulator does the timing, not us

**This is the most important thing in this chapter, and it is the biggest
difference from Track 1.**

Track 1's referee watched the car's position and timed laps itself against a
finish line whose coordinates were in `maps/`. This one does not. The AutoDRIVE
Simulator owns the circuit, the start/finish line and the collision detection,
and publishes what happened over the devkit bridge:

| Topic | What the referee does with it |
| --- | --- |
| `…/lap_count` | A lap closed |
| `…/last_lap_time` | How long that lap took |
| `…/collision_count` | How many contacts, cumulatively |
| `…/lap_time` | The race clock, for the session and stuck timeouts |
| `…/odom` | Speed, for the stuck timeout |

The referee applies the hackathon's rules to those numbers — which laps count,
what a collision costs, when a run is over — and writes the result. It never
opens a map.

Three consequences:

- **A scored run does not depend on the map, so it works before the map
  exists.** That is not a convenience; it is why the compete circuit can be
  released as a simulator build.
- **Lap times are the simulator's own**, measured on its internal clock at a
  fixed physics timestep. A machine that cannot keep up runs slower against the
  wall clock rather than producing different lap times. The result file records
  `real_time_factor` so you can see how hard your machine was working; around
  1.0 is healthy, because AutoDRIVE advances in real time when it can.
- **You can check our arithmetic.** The result file carries
  `simulator_best_lap_time` — the simulator's own best-lap figure, straight off
  `…/best_lap_time`, untouched. It should equal `fastest_raw_lap_time`, which
  is the quickest of the per-lap times the referee recorded. If it ever does
  not, tell us; that is a bug worth reporting (rule 49).

  Note that this is *not* the same as `best_lap_time`. The simulator reports
  the quickest lap **as driven**; you are scored on the best lap **after
  penalties**, and those are often different laps. A quick lap that picked up a
  collision is not your best lap.

What none of this protects you from: a control loop so slow that your node
misses scans. That is your code's problem, and it is a real one — the LiDAR
arrives at 40 Hz, so keep the per-scan work bounded.

---

## 5.4 How collisions are counted

The simulator detects contact with the track boundary and publishes a running
count on `…/collision_count`. The referee counts what the simulator counted and
nothing more — the same number the ICRA leaderboard reports.

The counter is cumulative and already debounced, so unlike Track 1 there is no
"once per second" rule here and nothing to tune. What the simulator calls one
collision is one collision.

Each one adds **10 seconds** to the lap it happened on. Against a lap in the
low twenties that is half a lap thrown away per contact, and a driver that
touches the boundary a few times a lap will spend longer in penalties than it
does driving. **Not hitting things is worth more than any amount of speed on
this track.**

**More than 10 collisions in a run is a disqualification**, and the referee
ends the run the moment the eleventh lands rather than letting the car limp to
the flag. A car that has hit the boundary eleven times is not racing any more,
and the remaining laps tell nobody anything.

That threshold is not far away. Three collisions a lap — which is an ordinary
result for a first attempt at a reactive driver here, given the pinch points in
[§2.1](02-simulator.md#21-how-the-pieces-fit-together) — puts you out on lap
four. **Expect your first working driver to be disqualified well before the
flag**, and read that as the plainest possible statement of what this track is
about rather than as a reason to worry.

The counters do not necessarily read zero when a run starts — the simulator may
have been driven already in the same session. The referee takes a baseline at
the green flag and scores the difference, so a practice lap before a scored run
cannot cost you anything.

---

## 5.5 Reading a result file

```jsonc
{
  "schema_version": 3,
  "referee_version": "2.0.0",
  "simulator": "autodrive",
  "team": "your_team_name",
  "run_id": "20261018T143000Z",
  "track": "icra26_compete",
  "status": "COMPLETE",
  "scored": true,
  "laps_completed": 10,
  "laps_required": 10,
  "collisions": 1,
  "collision_limit": 10,
  "best_lap_time": 21.804,        // best lap AFTER penalties - what you are scored on
  "best_lap_time_raw": 21.804,    // that same lap, before its penalties
  "best_lap_number": 7,
  "fastest_raw_lap_time": 21.235, // the quickest lap as driven - a different lap here
  "fastest_raw_lap_number": 8,
  "total_time": 238.912,          // 10-lap total - what you are scored on
  "total_time_raw": 228.912,      // before penalties
  "total_penalty_s": 10.0,
  "race_time_s": 228.9,
  "simulator_best_lap_time": 21.235,   // the simulator's own figure; matches fastest_raw_lap_time
  "warnings": [],
  "laps": [
    { "number": 1, "raw_time": 23.441, "collisions": 0, "penalty_s": 0.0, "net_time": 23.441 },
    { "number": 2, "raw_time": 22.108, "collisions": 1, "penalty_s": 10.0, "net_time": 32.108 }
  ],
  "environment": { "real_time_factor": 0.97, "wall_duration_s": 262.1 }
}
```

`best_lap_time` and `total_time` are `null` unless `scored` is `true`.

`warnings` is normally empty. Anything in it means the referee saw telemetry it
did not expect — a lap the simulator reported as impossibly short, or two laps
closing between samples — and it is recorded rather than quietly patched up.
A warning does not invalidate a run, but do mention it if you report a problem.

```sh
# Summarise your recent runs
./scripts/leaderboard.py summarise results/

# Full leaderboard across teams
./scripts/leaderboard.py rank results/ --csv leaderboard.csv
```

---

## 5.6 Automated judging on every push

[`.github/workflows/judge.yml`](../.github/workflows/judge.yml) races your
entry on GitHub Actions whenever you push, and writes the result to the
workflow summary. It is the same referee with the same settings, so a green run
means your entry will at least start on judging day.

> **The workflow is for reference only. It never decides your result.**
> Your score comes from the organisers' run on the judging machine
> ([§5.8](#58-judging-day)) — three runs, best attempt, rule 23. A green
> Judge run tells you the entry builds, starts and finishes; the times it
> prints are an indication and nothing more. Nothing it reports is scored,
> and a quick time here wins nothing.

It runs in two stages:

| Stage | What it does |
| --- | --- |
| **Checks** | Referee rule tests, track metadata validation, and `verify_judging_env.sh`. About a minute. |
| **Race** | Fetches the simulator, builds the image and races, headless. |

**Checks failing blocks the race.** That is deliberate: the one most likely to
trip is the judging-environment check, and an entry that modifies it is not
scored (rule 30), so there is no point racing it.

The simulator download is cached against its release tag, so only the first run
on a branch pays for it.

### Entry or template?

Before racing, the workflow asks whether there is anything to score:

```sh
./scripts/detect_submission.sh --explain
```

It compares `race_ws/src/team_driver/` against the recorded template. Edit any
file, or add one, and it reports `submission` and your driver is raced. Leave
it untouched — as on the template repository — and it reports `template`, and
the workflow skips the race and says so. There is nothing to score: the
template does not drive, and racing it would fill the summary with a car
parked against the first barrier.

> [!NOTE]
> **Organisers:** the reference is `scripts/template_manifest.sha256`. If you
> change anything under `race_ws/src/team_driver/` — even a comment — re-record
> it with `./scripts/detect_submission.sh --update`, or the template repository
> starts reporting itself as a submission and CI races the stub driver.

### Running it by hand

Use **Actions — Judge — Run workflow** to set the number of laps and runs:

| Input | Default | |
| --- | --- | --- |
| `laps` | 10 | Scored laps per run. Drop it to 3 for a quick check. |
| `runs` | 1 | Runs per driver; the best counts. |

Result JSONs are attached to the run as an artifact, so you can feed them to
`leaderboard.py` locally.

### What it is not

CI runs on a shared two-core runner with no GPU. The simulator is happy enough
headless — it needs no graphics device at all — but it will run below real time,
so a run takes a while in wall-clock terms. That does **not** change your lap
times (§5.3). It does mean a driver that only just fits its control loop here
may behave differently on the judging machine. Nothing CI reports is scored:
the result that counts is the organisers' run on the machine in
[§5.8](#58-judging-day).

---

## 5.7 Watching a run

```sh
./scripts/evaluate.sh --team my_team --laps 3 --graphics
```

With the simulator rendering you get its own HUD — speed, throttle, steering,
the LiDAR preview and the live lap and collision counters — and with RViz open
you get the LiDAR, the vehicle frames, a referee status line and
`/driver/markers` for whatever your own node draws.

The referee log prints each lap as it closes, with any penalty applied:

```
[referee]: Lap 1/10: 22.087s -> 52.087s (+30s from 3 collision(s))
```

---

## 5.8 Judging day

### The judging machine

Every submission is scored on one machine, so nobody is advantaged by hardware:

| | |
| --- | --- |
| CPU | Intel Core i9-14900HX, 16 cores / 32 threads |
| RAM | 32 GB, of which about 16 GB is visible inside WSL by default |
| GPU | NVIDIA GeForce RTX 5060 Laptop, 8 GB |
| OS | Windows 11 with WSL 2 (Ubuntu 24.04) |
| Docker | Docker Engine inside WSL 2 |

(The AutoDRIVE organisers used an i9-14900K with an RTX 4090 for ICRA. Ours is
a laptop equivalent; since a scored run is headless and the times are the
simulator's, the difference does not affect results.)

**The GPU is usable for your code.** The container is ROS 2 Humble on Ubuntu
22.04, so Python 3.10, and CUDA builds of PyTorch and friends install and run.
Declare what you need in `requirements.txt` (rule 37) and it is installed into
the image.

The simulator itself runs `-batchmode -nographics` for a scored run, so it
creates no graphics device and uses no GPU at all. That is a deliberate choice:
it is faster, it is reproducible, and it means a headless run on a CI runner
exercises the same code path as judging day.

Two practical notes. The card has 8 GB, shared with the desktop, so a model
needing more will not fit. And your node still has to keep up with a 40 Hz
control loop; a heavyweight network that misses scans costs more time than it
gains.

For each submission the judges:

1. Check out the entry, verify the judging environment is intact
   (`./scripts/verify_judging_env.sh`), and confirm it builds from clean.
2. Fetch the pinned simulator build with `./scripts/fetch_simulator.sh`.
3. Build the image from this repository, which installs whatever the team
   declared in `requirements.txt` and `apt-packages.txt`. That step is the last
   layer in the Dockerfile, so it is quick per submission.
4. Run three scored attempts, headless:
   ```sh
   ./scripts/evaluate.sh --team <team> --runs 3
   ```
5. Take the **best** of the three. Anything that never completes is a DNF.
6. Feed every team's best run into `leaderboard.py rank`, which produces the
   final ranking.

No internet access during a run — anything a team needs must be declared so it
lands in the image at build time. No manual intervention once a run starts.
Identical referee settings for every team.

A run that fails to build, fails to start, or never publishes a command scores
zero for the timing component. Test from a clean clone before you submit — see
[chapter 7](07-submission.md).

---

## 5.9 Verifying your environment

```sh
./scripts/verify_judging_env.sh
```

It hashes every file a scored run depends on — the referee package, the
vendored AutoDRIVE Devkit, the Dockerfile and its dependency pins, the compose
files, `maps/tracks.yaml`, the evaluation scripts — compares against a
manifest, and checks for files added into those directories.

A clean report means your entry will be judged. If it flags something you
changed by accident:

```sh
git checkout -- race_ws/src/roboracer_referee external/autodrive_devkit \
                docker maps/tracks.yaml scripts install
```

`race_ws/src/team_driver/` is deliberately not protected. That is yours. So is
the rest of `maps/` — a racing line or an occupancy grid you built belongs
there and is not checked.

---

Next: **[6. Rules](06-rules.md)**
