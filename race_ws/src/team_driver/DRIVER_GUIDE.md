# Predictive centreline driver

The driver follows the organiser-provided centreline using ground-truth pose.
It builds a speed profile once at startup and uses LiDAR to check for obstacles
on the upcoming path. The camera is not needed.

## Run

Keep the simulator connected to the existing bridge. In a separate container
terminal, after building the package:

```bash
source /hackathon/race_ws/install/setup.bash
ros2 launch team_driver driver.launch.py
```

The launch file loads `config/driver_params.yaml`. The startup message prints
the effective speed and acceleration limits. A plain `ros2 run team_driver
driver` does not load that YAML and uses conservative defaults unless passed
`--ros-args --params-file /hackathon/race_ws/src/team_driver/config/driver_params.yaml`.
Use the explicit parameter file for evaluation as well.

Ctrl+C publishes zero throttle and steering before exiting. Zero throttle
means coasting, not an immediate physical stop. Do not run two drivers at once.

## How it anticipates a corner

1. Estimate curvature around each centreline point.
2. Limit corner speed using `speed² × curvature ≤ lateral_acceleration`.
3. Work backward around the closed lap to enforce the braking-distance limit.
4. Work forward to enforce the acceleration limit, including the lap boundary.
5. Sample that profile with a reaction-time margin, slowing before corner entry.
6. Follow a point ahead on the path. Look farther ahead on straights, keeping
   the shorter steering lookahead in tight bends to avoid cutting across them.

LiDAR returns are compared with a vehicle-width corridor along the upcoming
curved path. An object inside that corridor imposes an additional speed limit.
The original immediate forward-obstacle stop is retained. Unknown forward
readings, excessive path error, or stale sensors cancel acceleration.

## Acceleration and braking

Feed-forward, bounded PI feedback and target-acceleration feed-forward turn
the target speed into normalized throttle. Overspeed produces progressive
negative throttle, capped by `max_brake`. That cap decreases as steering grows,
and active braking is disabled below 0.6 m/s to avoid driving backwards.

This is a brake-release heuristic, not a calibrated weight-transfer or ABS
model. Full negative throttle is deliberately not used. The assumed grip and
braking limits require simulator validation before raising them.

## Tuning

| Parameter | Current proposed value | Purpose |
| --- | --- | --- |
| `max_speed` | 3.0 m/s | Retains the user's tested straight-line ceiling |
| `acceleration_limit` | 1.5 m/s² | Faster target-speed ramp; previously 0.5 |
| `lateral_acceleration` | 2.8 m/s² | Limits speed according to corner curvature |
| `braking_deceleration` | 1.3 m/s² | Assumed deceleration for planning braking points |
| `braking_reaction_time` | 0.20 s | Allows for response delay |
| `braking_margin` | 0.15 m | Additional distance allowance |
| `max_brake` | 0.04 | Retains the previous negative-throttle cap |
| `lookahead` / `max_lookahead` | 0.65 / 0.95 m | Steering target-distance limits |

`corner_speed: 0.4` is preserved for experimental gap mode. Predictive pure
pursuit now derives corner speed from curvature and grip instead of using
the old linear steering-to-speed formula. Targets are not guaranteed actual
speed limits; the vehicle may overshoot.

## Validation and limits

The previous driver completed the user's reported ten-lap practice session
without recorded collisions, with a displayed best lap of 30.5 seconds. A
rollback copy was saved separately before this change.

Six offline tests cover acceleration and braking constraints around the lap,
brake release while turning, bounded acceleration/integral, invalid input and
off-track stops, obstacle placement, and idealized path tracking. These passed.
They do not validate tire grip, actual braking distance, lap time or legal
course adherence in the real simulator. Live comparison is still pending.

Run the tests inside the configured ROS workspace with:

```bash
python3 -m unittest discover -s /hackathon/race_ws/src/team_driver/tests -v
```

Compare repeated full laps against the previous version and record collisions,
lap times and maximum path error. Windows practice is not an official Linux
headless judged run. Keep the working baseline until repeated full-length
evaluations demonstrate an improvement.
