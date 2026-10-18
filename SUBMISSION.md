# Team yappers

## Members
| Name | Matric number | Email |
| --- | --- | --- |
| Lee Zi Jie | U2521931K | LEEZ0111@e.ntu.edu.sg |
| Kelvin Hou | U2521590H | YHOU010@e.ntu.edu.sg |
| Tan Soon Kang | U2523802E | TANS0450@e.ntu.edu.sg |
| Samuel Liow | U2522584k | ZLIOW002@e.ntu.edu.sg |
| Lew En Xun | U2522615A | LEWE0003@e.ntu.edu.sg |
## Approach
Our driver is a predictive pure-pursuit controller that follows the organiser-provided centreline (`maps/icra26_compete_centerline.csv`). At startup it estimates curvature along the centreline and builds a speed profile: corner speed is limited by lateral acceleration (v^2 * curvature <= a_lat), then a backward pass enforces braking distance and a forward pass enforces the acceleration limit around the closed lap. At run time it samples that profile with a reaction-time margin so the car slows before a corner, and steers toward a lookahead point on the path, with a longer lookahead on straights and a shorter one in tight bends.

We chose this because the track is a known, fixed circuit, so planning against the centreline gives smoother and faster laps than a purely reactive approach. We also kept a gap-follow mode in the code for experiments, but it is not used in the submitted run. We raised the speed limits gradually from a slower configuration that completed 10 laps (about 30 s per lap) to the current one.

<what you tried that did not work, one or two sentences>

## How it uses the inputs
- LiDAR: compared against a vehicle-width corridor along the upcoming path to impose an extra speed limit when an object is in the way. A forward-obstacle stop is also kept, and unknown forward readings cancel acceleration.
- Pose: simulator ground truth from the odom topic, matched against the organiser-provided centreline. We did not build our own localisation.
- Camera / IMU / encoders: not used.

## Speed control
Normalised throttle is built from a feed-forward term (throttle per m/s of target speed), a bounded PI feedback loop, and target-acceleration feed-forward. Overspeed produces a limited negative throttle (braking), which shrinks as steering grows and is disabled below 0.6 m/s. The target speed is a plan, not a guarantee, so the car can overshoot it. Key parameters are in `race_ws/src/team_driver/config/driver_params.yaml` (max_speed 3.5 m/s, acceleration_limit 2.0 m/s^2, lateral_acceleration 3.3 m/s^2).

## Results on our own machine
Runs committed in `results/submitted/`: `yappers__20261018T075350Z.json` and `yappers__20261018T083212Z.json`. Both are COMPLETE, 10/10 laps, 0 collisions.

| Best lap | 10-lap total | Collisions | Runs attempted |
| --- | --- | --- | --- |
| 21.202 s | 213.032 s | 0 | 4 (2 COMPLETE, 2 aborted) |

The two aborted runs happened while setting up: a stale, suspended bridge process from an earlier session held port 4567, so the simulator never connected. They are not committed. After killing it, both later runs completed.

### The machine that produced them
| CPU | GPU | RAM | OS | Typical real-time factor |
| --- | --- | --- | --- | --- |
| <Intel Core Ultra 7 270K Plus> | <RTX 5070> | <32GB> | Windows <Windows 11>, Ubuntu on WSL 2 with Docker Desktop | <results/yappers__20261018T075350Z.json
results/yappers__20261018T083212Z.json> |

Both completed runs were headless, via `./scripts/evaluate.sh`.

## Anything precomputed
Nothing is trained or precomputed offline. The speed profile is computed at startup from the organiser's centreline file.

## Dependencies we added
None. `requirements.txt` and `apt-packages.txt` only carry the template's defaults.

## Third-party code and references
Organiser-provided template, devkit, centreline and referee.

## AI assistance
We used Claude (Anthropic) to help with Docker/WSL setup, debugging the simulator connection, and understanding the template and driver>. 

## Known issues
- The speed profile assumes grip and braking limits that were only validated by trial in the simulator, not calibrated.
- Collision counts vary between runs, so we cannot promise 0 collisions on the judging machine.
- Lock in

