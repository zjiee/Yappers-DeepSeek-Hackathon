# RoboRacer Sim Racing — Track 2

**NTU DeepSpeed Recruitment Hackathon 26/27**

Write the software that drives a 1/10-scale racing car around a circuit it has
never seen, as fast as it can, without hitting anything. This track runs the
**compete** phase of the [RoboRacer Sim Racing League @ ICRA 2026](https://autodrive-ecosystem.github.io/competitions/roboracer-sim-racing-icra-2026/)
on the AutoDRIVE Simulator — the same vehicle, the same sensors, the same
circuit and the same devkit the ICRA teams raced.

> **Submission deadline: 18 October 2026, 23:59 (SGT)**

---

## Quick start

```sh
git clone https://github.com/NTUDeepSpeed/Recruitment_Hackathon_2627.git
cd Recruitment_Hackathon_2627
git checkout track2

./scripts/fetch_simulator.sh      # 140 MB, once
./install/linux/setup.sh          # or install/macos, or install/windows from WSL
./install/linux/run.sh            # builds if needed, then drops you into the container
```

Then, inside the container:

```sh
cd /hackathon/race_ws && colcon build --symlink-install
source install/local_setup.bash

# Terminal 1 — the simulator and the devkit bridge
ros2 launch roboracer_referee simulator.launch.py

# Terminal 2 — your car
ros2 run team_driver driver
```

The car will crawl forward and hit the first barrier: the template is wiring,
not a driver, and writing one is the hackathon. Once yours does something,
score it:

```sh
./scripts/evaluate.sh --team your_team_name
```

Pushing also races your entry on GitHub Actions and writes the result to the
workflow summary. That workflow is for reference only — it runs on GitHub's
hardware and nothing it prints is scored. **Your result is the organisers' run
on the judging machine.**

Full walkthrough: **[docs/01-setup.md](docs/01-setup.md)**.

> No submodules on this branch — a plain `git clone` is enough, and even a ZIP
> download works. The AutoDRIVE Devkit is committed to this repository; the
> simulator is a separate download that `./scripts/fetch_simulator.sh` handles.

---

## The challenge

You get a LiDAR scan, an IMU, wheel encoders, a camera and the car's exact
position. You publish a throttle and a steering command. That is the whole
interface.

| | |
| --- | --- |
| **Simulator** | AutoDRIVE Simulator, `2026-icra` **compete** build |
| **Car** | RoboRacer digital twin. Ackermann steering, 0.324 m wheelbase, 0.27 × 0.50 m, 3.9 kg, steering limited to ±0.5236 rad |
| **Sensor** | 1080-beam LiDAR, 270° field of view, 10 m range, 40 Hz — plus IMU, encoders and a front camera |
| **Control** | **Normalised throttle and steering, both in [−1, 1].** Not a speed request — closing that loop is your problem |
| **Localisation** | Ground-truth pose on `.../ips` and `.../odom` — **allowed and recommended** |
| **Track** | The ICRA 2026 compete circuit, inside the simulator. A long, narrow loop about 6.3 × 18.2 m with a 54 m lap, bounded by 33 cm air ducts, roughly 2 m wide and under 1 m at its tightest. |
| **Scored on** | Your single fastest lap, and your time for 10 consecutive laps |
| **Penalties** | +10 s on the lap for each collision; more than 10 collisions is a disqualification |
| **Judged on** | One machine: i9-14900HX, 32 GB, RTX 5060 Laptop. Times come from the simulator's own clock, so your hardware does not affect your score. |

**No driver ships with this repository.** `team_driver` is wiring — it talks to
the simulator and crawls in a straight line into the first barrier. Writing
something that laps is the hackathon. Reactive algorithms like follow-the-gap
will get you round; planning — against the map, and against your own position —
is where the lap time is; and **replacing the approach outright is encouraged**:
reinforcement learning, MPC, imitation learning, a learned end-to-end policy,
anything you can defend. [docs/04-algorithms.md](docs/04-algorithms.md) is the
menu, with what each approach needs and where each breaks.

### What is different from Track 1

Both tracks are RoboRacer, and the racing problem is the same. The environment
is not, and four differences will bite you if you skim:

| | Track 1 | Track 2 |
| --- | --- | --- |
| Simulator | `f1tenth_gym` + ROS bridge | **AutoDRIVE**, a Unity binary you download |
| Control | `AckermannDriveStamped` — ask for a speed | **`Float32` throttle in [−1, 1]** — ask for torque |
| Lap timing | Our referee, against a finish line in `maps/` | **The simulator's**, over the devkit bridge |
| The map | Shipped with the simulator | **Traced off the simulator** — it is in `maps/`, and a scored run ignores it |

The throttle one is the big one. There is no speed controller between your node
and the motor any more, so "take this corner at 3 m/s" is a control problem you
now own — and nothing here solves it for you. See
[§4.1](docs/04-algorithms.md#41-first-the-thing-that-is-not-an-algorithm).

---

## Where things are

```
Recruitment_Hackathon_2627/
├── install/                    Setup scripts, one folder per platform
│   ├── linux/  macos/  windows/    setup.sh, run.sh, shell.sh, stop.sh
│   └── common.sh
├── race_ws/src/                The ROS 2 workspace, mounted into the container
│   ├── team_driver/            ★ YOUR CODE GOES HERE — the template does not drive
│   └── roboracer_referee/        The judging environment — do not modify
├── external/autodrive_devkit/  The AutoDRIVE Devkit — do not modify
├── simulator/                  The AutoDRIVE Simulator, fetched by script
├── scripts/                    evaluate.sh, fetch_simulator.sh, leaderboard.py, …
├── maps/                       Occupancy grid of the circuit, its centreline and metadata
├── docker/                     Image definition (ROS 2 Humble) and compose files
├── results/                    Where your run results land
├── .github/workflows/          Automated judging on every push
├── docs/                       This guide
└── workshop/                   ROS 2 teaching material from the workshop
```

The one file you are meant to open first:
**[`race_ws/src/team_driver/team_driver/driver.py`](race_ws/src/team_driver/team_driver/driver.py)**

---

## The guide

| Chapter | What is in it |
| --- | --- |
| **[1. Setup](docs/01-setup.md)** | Installing Docker, fetching the simulator, building the image, first run, troubleshooting |
| **[2. The simulator](docs/02-simulator.md)** | AutoDRIVE, the bridge, every topic, the vehicle and sensor specifications |
| **[3. ROS 2 primer](docs/03-workshop.md)** | Nodes, topics and the workshop slides, if ROS is new to you |
| **[4. Algorithms](docs/04-algorithms.md)** | The menu: reactive, planned, model-based and learned — what each needs and where each breaks |
| **[5. Evaluation](docs/05-evaluation.md)** | Scoring yourself, reading result files, how judging day runs |
| **[6. Rules](docs/06-rules.md)** | The rules, the scoring formula, and what gets you disqualified |
| **[7. Submission](docs/07-submission.md)** | What to hand in, how, and what the interview covers |

---

## Rules at a glance

The full rules are in **[docs/06-rules.md](docs/06-rules.md)** and they are what
counts. The short version:

- **Teams of 3 to 5.**
- **Deadline: 18 October 2026, 23:59 SGT.** Late entries are not scored.
- **AI assistants are allowed.** You will be asked to explain your code at the
  interview — generally, not line by line — so do not submit anything you
  cannot defend. A learned policy is held to the same standard, and meets it
  the same way: explain how you trained it and why, not what each weight
  means.
- **Do not modify the judging environment, and do not modify the AutoDRIVE
  Devkit.** Check yourself with `./scripts/verify_judging_env.sh`.
- **Every sensor topic is open to you, including ground-truth pose.** The
  AutoDRIVE competition marks some of those "restricted at race time"; this
  hackathon does not. The one thing you may not publish is
  `/autodrive/reset_command` — that is the referee's.
- **Score (out of 100):**

  | | Weight | Formula |
  | --- | --- | --- |
  | Fastest single lap | 50 | `50 × (fastest lap of any team ÷ your fastest lap)` |
  | 10-lap total | 50 | `50 × (fastest 10-lap total of any team ÷ your 10-lap total)` |

  An out lap and one warm-up lap are granted before timing starts. Each
  collision adds 10 s to the lap it happened on — about half a lap here — and
  more than 10 collisions in a run is a disqualification. At three collisions a
  lap you are out before the flag, so contact is the first problem to solve,
  not the last.

- **Bonus marks** at the interview, for work you can explain properly:
  replacing the ground-truth pose with your own localisation; building a map of
  the circuit and generating a racing line from it; a speed controller that
  knows about the corner it is entering; or an ambitious driving algorithm —
  reinforcement learning, MPC, imitation learning.

---

## Getting help

- Check the troubleshooting section at the end of
  [docs/01-setup.md](docs/01-setup.md) first — most problems are there, and the
  two most common ones (a bridge that connects and then publishes nothing, and
  a simulator that cannot find the bridge) both look like something else.
- Bring the exact error text and what you ran to the team channel.
- `./scripts/verify_judging_env.sh` will tell you if your environment has
  drifted from the official one.
- You may email `ntu-deepspeed@e.ntu.edu.sg` for further inquiries if you cannot
  solve the issues after troubleshooting.

Good luck. Go fast.
