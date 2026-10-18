# 6. Rules

These rules govern Track 2 of the NTU DeepSpeed Recruitment Hackathon 26/27.
Where this page and any other document disagree, this page wins.

Track 2 runs the **compete** phase of the
[RoboRacer Sim Racing League @ ICRA 2026](https://autodrive-ecosystem.github.io/competitions/roboracer-sim-racing-icra-2026/)
on the AutoDRIVE Simulator. Where the AutoDRIVE competition's own rules and
these disagree, **these apply** — the differences are called out explicitly in
rules 33 and 34, because they matter.

---

## 6.1 Teams

1. A team has **3 to 5 members**.
2. Each person may be on **one team only**.
3. The roster is fixed at submission. Name every member in your `SUBMISSION.md`
   (see [chapter 7](07-submission.md)).
4. One entry per team.

---

## 6.2 Deadline

5. **Submissions close 18 October 2026, 23:59 (SGT).**
6. The commit timestamp on your submitted branch is what counts. Anything
   pushed after the deadline is not scored.
7. Late entries are not accepted. Submit early and push again if you improve —
   the last commit before the deadline is the one judged.

---

## 6.3 The race

8. Every run is driven on the official circuit — the **compete** track inside
   the AutoDRIVE Simulator `2026-icra` build — in the official Docker image
   built from this repository, on a single judging machine whose specification
   is published in [§5.8](05-evaluation.md#58-judging-day).
9. A run consists of:
   - an **out lap** from the grid slot to the start/finish line — not timed;
   - **one warm-up lap** — granted, not scored;
   - **10 timed laps**, run consecutively.

   The simulator spawns the car most of a circuit before its own start/finish
   line, so the out lap closes as a lap in the simulator's count rather than
   being a short run-up as it is on Track 1. Twelve laps are driven; ten are
   scored.
10. Laps are counted, and timed, by the simulator. The referee records what the
    simulator reports — see [§5.3](05-evaluation.md#53-the-simulator-does-the-timing-not-us).
11. **The track boundary is a line of air ducts, and the gaps between them are
    not a route.** A duct marks the edge of the course exactly as a wall does;
    the gaps are a consequence of the ducts being separate objects. Go around
    the end of a row, never through it. The simulator scores contact with a
    duct as a collision, so this rule mostly enforces itself — but a car that
    threads a gap cleanly has still left the course, and a run that does it is
    not scored.
12. The car is placed on the grid by the referee at the start of every run.
    Once a run starts there is no manual intervention.
13. A run that does not complete all 10 timed laps within **900 seconds of
    simulated time** is recorded as DNF and scores zero for both components.
14. A car that does not move for **15 seconds of simulated time** is recorded as
    DNF.

---

## 6.4 Collisions

15. Every collision adds a **10-second penalty** to the lap on which it
    happened. Penalties are included in both your fastest lap and your adjusted
    race time.
16. **More than 10 collisions in a run is a disqualification** for that run,
    as on Track 1. The referee ends the run at the eleventh collision rather
    than letting it continue. A disqualified run scores zero for both
    components (rule 22).
17. A collision is what the simulator counts as a collision. The referee reads
    `…/collision_count` and applies the penalty; it does not do its own contact
    detection and there is nothing to tune. See
    [§5.4](05-evaluation.md#54-how-collisions-are-counted).
18. Collisions during the out lap or the warm-up lap count towards the limit in
    rule 16, but carry no time penalty, because there is no scored lap to apply
    it to.

---

## 6.5 Scoring

19. Two components, 50 points each, scored **relative to the best team**:

    | Component | Points | Formula |
    | --- | --- | --- |
    | **Fastest single lap** | 50 | `50 × (fastest lap of any team ÷ your fastest lap)` |
    | **10-lap total** | 50 | `50 × (fastest 10-lap total of any team ÷ your 10-lap total)` |

    The fastest team in each component gets the full 50. Everyone else is scaled
    by the ratio of times.

20. **Leaderboard score = fastest-lap points + 10-lap points**, out of 100,
    ranked highest first.

21. Both components use times **after** collision penalties.

22. Only a run with status `COMPLETE` scores. A disqualified or DNF run scores
    **zero for both components**.

23. The judges run each submission **three times** and take the best attempt.
    The simulator is not perfectly deterministic, and nobody should lose on a
    single unlucky run.

    **That run, on the judging machine, is the only one that scores.** The
    GitHub Actions **Judge** workflow races your entry too, but it is for
    reference — it tells you the entry builds and runs, on hardware that is
    neither yours nor ours. Nothing it reports counts towards the leaderboard.
    See [§5.6](05-evaluation.md#56-automated-judging-on-every-push).

24. Results are computed by
    [`scripts/leaderboard.py`](../scripts/leaderboard.py), which is in this
    repository. You can run it yourself.

25. Where a tie-break is needed, the 10-lap total decides it.

### Worked example

Three teams finish. The fastest single lap of anyone is 20.50 s; the fastest
10-lap total is 228.90 s.

| Team | Best lap | 10 laps | Lap points | Endurance points | **Total** |
| --- | --- | --- | --- | --- | --- |
| Alpha | 21.80 | 228.90 | 50 × 20.50/21.80 = **47.02** | 50 × 228.90/228.90 = **50.00** | **97.02** |
| Bravo | 20.50 | 245.00 | 50 × 20.50/20.50 = **50.00** | 50 × 228.90/245.00 = **46.71** | **96.71** |
| Charlie | 25.00 | 260.00 | **41.00** | **44.02** | **85.02** |

Bravo has the fastest single lap and still finishes second. Consistency over
ten laps is worth exactly as much as one quick one — and since a single
collision costs 10 s of race time, consistency here mostly means not crashing.

---

## 6.6 The judging environment

26. The official simulator is the **`2026-icra` compete build**, fetched by
    `./scripts/fetch_simulator.sh`. Do not substitute the `explore` or
    `practice` build, or a build from another event, for a scored run. You are
    welcome to practise against any of them — training on `practice` and racing
    on `compete` is exactly the generalisation problem ICRA set.

27. The official image is the one built from `docker/Dockerfile` in this
    repository. Entries are judged in that image and nothing else.

28. **Do not modify the judging environment.** That means:
    - `race_ws/src/roboracer_referee/`
    - `docker/` and `.dockerignore` — everything that defines the image
    - `maps/tracks.yaml`
    - `scripts/` and `install/`
    - `.github/workflows/`

    Adding a file to one of those directories counts as modifying it.

    The rest of `maps/` is yours: a racing line or an occupancy grid you built
    belongs there and is not checked.

29. **Do not modify the AutoDRIVE Devkit** at `external/autodrive_devkit/`.
    This is the AutoDRIVE competition's own rule and the hackathon keeps it.
    Write your code as separate packages that talk to the devkit's topics —
    which is what `team_driver` already is.

30. An entry that modifies either is **not scored**. If you genuinely believe
    something in it is broken, raise it with the organisers before the deadline
    rather than patching around it — see rule 49.

31. Your code must not publish to **`/autodrive/reset_command`**, or otherwise
    interfere with the referee's topics under `/referee/*`. The reset command
    teleports the car and zeroes the counters the referee scores from;
    publishing it during a run is not a penalty, it is a disqualification.

32. Verify before you submit:
    ```sh
    ./scripts/verify_judging_env.sh
    ```
    It checks file hashes across the referee and the devkit and looks for files
    added into protected directories. The **Judge** workflow runs the same
    check on every push and, when it fails, reports it in the run summary with
    the list of files that differ — a disqualification is a ruling, so it is
    shown as one rather than left as a failed build.

---

## 6.7 What your code may use

33. **Inputs you may read — all of them.**

    | Topic | |
    | --- | --- |
    | `…/lidar` | LiDAR, 1080 beams over 270°, 10 m |
    | `…/front_camera` | RGB camera (empty in a headless run) |
    | `…/imu` | Orientation, angular velocity, linear acceleration |
    | `…/left_encoder`, `…/right_encoder` | Wheel encoders |
    | `…/throttle`, `…/steering` | Actuator feedback |
    | `…/ips` | **Ground-truth position — allowed** |
    | `…/odom` | **Ground-truth pose and velocity — allowed and recommended** |
    | `…/lap_count`, `…/lap_time`, `…/last_lap_time`, `…/best_lap_time` | Race telemetry — **allowed** |
    | `…/collision_count` | Collision count — **allowed** |
    | `/tf`, `/tf_static` | Transforms — **allowed** |

    > **This differs deliberately from the AutoDRIVE competition rules.** Those
    > mark `…/ips`, `…/odom`, `/tf` and the race-telemetry topics *restricted*:
    > available for development, but not "while autonomously racing at run-time".
    > **Track 2 does not adopt that restriction.** Every input above is yours to
    > use during a scored run.
    >
    > The reason is that this is a recruitment hackathon, not a robotics
    > competition. Recovering a pose the simulator is already publishing is a
    > good exercise and a genuinely hard one — and it is worth bonus marks under
    > rule 45 — but making it compulsory would mean most teams spend the whole
    > hackathon on localisation and never write a planner.
    >
    > **The restriction on *publishing* is kept in full.** See rule 34.

34. **Outputs.** You may publish exactly two things to the car:

    | Topic | |
    | --- | --- |
    | `…/throttle_command` | Normalised throttle, [−1, 1] |
    | `…/steering_command` | Normalised steering, [−1, 1] |

    plus any topics of your own under `/driver/...` for visualisation and
    debugging.

    **`/autodrive/reset_command` remains restricted** — rule 31. It is the only
    output the AutoDRIVE rules restrict and the hackathon restricts it too.

35. **Ground-truth pose is explicitly permitted.** Building your own
    localisation is not required and is genuinely difficult — harder here than
    on Track 1, since there is no shipped map to localise against. If you do
    build one, and can explain it thoroughly at the interview, it earns **bonus
    marks** — see rule 45.

36. **Offline precomputation is allowed.** Optimising a racing line before the
    run is real racing practice. But it must be produced by code you submit,
    and it must be reproducible — from a map you built, from a recorded lap,
    from something. Hand-tuned waypoints typed in from watching the car are not
    in the spirit of this and will not survive the interview.

37. **Extra packages are allowed, but you must declare them.** Anything you
    declare is installed into the image when it is built, so it is there during
    judging. Anything you do not declare will not be:

    | What you need | Where to declare it |
    | --- | --- |
    | Python packages | `race_ws/src/team_driver/requirements.txt` |
    | System packages | `race_ws/src/team_driver/apt-packages.txt` |

    List them in your `SUBMISSION.md` as well, with a line on what each is for.
    An undeclared dependency means your entry does not start, and **there is no
    network access during a judged run** to rescue it.

    Already installed, so nothing to declare: `rclpy`, `numpy`, `scipy`,
    `Pillow`, `opencv-python`, `PyYAML`, `transforms3d`, and the devkit's
    websocket stack.

    > Do **not** pin a different version of `python-socketio`, `python-engineio`
    > or `gevent` in `requirements.txt`. Those pins are load-bearing: the
    > simulator's client speaks Engine.IO v3 framing despite advertising v4, and
    > a newer version gives a bridge that connects and then publishes nothing at
    > all, silently, for the whole run. The build checks this, but a clash is
    > still the fastest way to score zero.

    The image is ROS 2 Humble on Python 3.10, and the judging machine has an
    8 GB NVIDIA GPU, so CUDA builds of PyTorch and friends are usable — see
    [§5.8](05-evaluation.md#58-judging-day). Rebuild from clean after adding
    anything, and check a run still starts.

38. Your driver must remain a ROS 2 node launched as
    `ros2 run team_driver driver`. You may add files, modules and extra
    executables inside `team_driver`, but keep that entry point working.

39. Keep your control loop real-time capable. The simulator publishes scans at
    40 Hz; a callback that takes longer than that will miss data. Note also
    that the bridge runs a strict request/response loop with the simulator, so
    a node that blocks the bridge slows the whole simulation down.

---

## 6.8 AI assistance

40. **Using AI assistants is permitted.** ChatGPT, Claude, Copilot, Cursor —
    all fine.

41. You are responsible for everything you submit. At the interview, any member
    may be asked to explain any part of the code: why it is written that way,
    what happens if a parameter changes, why the alternative approach was
    rejected.

42. Code you cannot explain will not count in your favour, however fast it is.
    This is a recruitment hackathon; we are hiring for understanding, not for
    prompt output. "Explain" means generally, not line by line: what it does,
    why it is built that way, what you rejected, where it breaks.

    This applies to learned components exactly as it does to hand-written ones,
    and it is satisfied the same way. Nobody is asked to account for an
    individual weight. If you can explain the method that produced them — what
    the model takes in and puts out, how it was trained, on what data or in
    what environment, under what reward or loss, how you validated it, and
    where it fails — then the model is explained, and it counts in full.

43. Third-party code and open-source algorithms are fine, with attribution in
    your `SUBMISSION.md`. Copying another team's entry is not.

---

## 6.9 Interview and bonus marks

44. Every team is interviewed after the race. The leaderboard decides the
    ranking; the interview decides recruitment.

45. Bonus marks, awarded at the interview and separate from the leaderboard:
    - **An ambitious algorithm.** Reinforcement learning, MPC, imitation
      learning, or anything else beyond a solid implementation of a standard
      reactive or path-following method
      ([chapter 4](04-algorithms.md)). The bar is that you can explain what it
      does, why you chose it, how you produced it — the training setup
      included, if it was trained — and what its failure modes are; not that
      it wins.
    - **Mapping the circuit.** Building an occupancy grid of a track that does
      not ship with one, from your own recorded laps.
    - **Own localisation.** A particle filter, scan matching or similar,
      replacing `…/odom`, that you can explain thoroughly.
    - **Own racing line generation** computed from a map rather than shipped as
      data.
    - **A real speed controller.** AutoDRIVE takes torque, not speed, and
      nothing in this repository closes that loop for you. A controller that
      knows about the corner it is entering — rather than reacting once it is
      in it — is both worth lap time and worth talking about.
    - **Clear engineering.** Readable code, sensible structure, evidence you
      measured rather than guessed.

46. Bonus marks affect the recruitment decision, not the leaderboard score.

---

## 6.10 Conduct

47. Do not interfere with another team's work, machines or submissions.
48. Do not attack, overload or attempt to gain access to the organisers'
    infrastructure, or to AutoDRIVE's.
49. If you find a bug in the judging environment, report it. Teams that report a
    genuine bug before the deadline are credited, not penalised. This track is
    new and the environment has a short history; we would rather hear about it.
50. Do not attempt to make the referee report a result other than what the car
    actually did. Exploiting a bug in the judging environment is the same as
    modifying it.

---

## 6.11 Judges' discretion

51. The organisers may adjust or clarify these rules before the deadline. Any
    change is announced in the team channel and reflected here. This includes
    the circuit: if AutoDRIVE publish a revised compete build, we may adopt it,
    and it will be announced.
52. In a situation these rules do not cover, the organisers decide, and will
    explain the reasoning.
53. The organisers' decisions on scoring and disqualification are final.

---

Next: **[7. Submission](07-submission.md)**
