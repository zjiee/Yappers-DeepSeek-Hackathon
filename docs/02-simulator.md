# 2. The simulator

The simulator is the [AutoDRIVE Simulator](https://autodrive-ecosystem.github.io),
`2026-icra` **compete** build — a Unity application carrying a high-fidelity
digital twin of the RoboRacer 1/10-scale car and the ICRA 2026 competition
circuit. It is the same binary the ICRA teams raced.

It does not speak ROS. It speaks a websocket protocol, and the **AutoDRIVE
Devkit** translates that into ROS 2 topics. The devkit is vendored unmodified
at [`external/autodrive_devkit/`](../external/autodrive_devkit/) and you may
not change it (rule 29).

---

## 2.1 How the pieces fit together

```
  AutoDRIVE Simulator  ──websocket, port 4567──▶  autodrive_bridge  ──▶  ROS 2 topics
      (Unity)                                      (the devkit)              │
                                                                             ▼
                                                                       your driver
```

**The bridge is the server. The simulator is the client.** The bridge listens
on port 4567; the simulator is given an address and dials out to it. So the
bridge always starts first, and if you start them the other way round the
simulator has nothing to connect to and every topic stays silent.

It is also a strict request/response loop: the simulator sends one frame of
sensor data and waits, the bridge replies with a throttle and a steering
command, and only then does the next frame arrive. One consequence is worth
knowing — if your node stops publishing commands entirely the loop keeps
turning, because the bridge replies with whatever it last received, but if the
*bridge* ever fails to reply the simulation stops dead.

```sh
ros2 launch roboracer_referee simulator.launch.py

# no window and no graphics device at all - much faster, and what judging uses
ros2 launch roboracer_referee simulator.launch.py headless:=true rviz:=false

# against a simulator you started yourself, here or on your Mac
ros2 launch roboracer_referee simulator.launch.py simulator:=false
```

### Headless

`headless:=true` runs the simulator with `-batchmode -nographics`. No window,
no graphics device, no GPU. The physics, the LiDAR, the collision detection and
the lap timing all still run — the front camera is the only thing that does
not, because there is nothing to render into. It is roughly an order of
magnitude cheaper than rendering, which is why a scored run uses it.

If you need the camera without a window, `./scripts/run_simulator.sh --xvfb`
renders into a virtual framebuffer instead.

You will see pages of `Shader ... is not supported on this GPU` and some ALSA
audio complaints on startup in headless mode. They are noise. There is no GPU
to compile shaders for and no sound card to open.

### The circuit

The circuit lives **inside the simulator**. It owns the start/finish line, the
lap counter and the collision detection, and reports what happened afterwards;
a scored run never opens a map.

There is a map in [`maps/`](../maps/) all the same, traced off the simulator so
you have something to plan against — see §2.9. These numbers are measured from
it and from recorded laps, not quoted from a brochure:

| | |
| --- | --- |
| Track | ICRA 2026 compete circuit, in the compete build |
| Bounding box | about 6.3 × 18.2 m — a long, narrow circuit |
| Lap length | 54.4 m down the centreline |
| Width | about 2 m typical, under 1 m at the tightest point |
| Boundary | 33 cm diameter air ducts, the same as the physical RoboRacer tracks |
| Surface | polished concrete: flat and reflective |
| Features | two long straights either side of a switchback complex |
| Spawn | (0.80, 3.16) facing −y; the lap boundary is at y = 3.80 |

It is tighter than it sounds. A 2 m corridor for a 0.27 m car is generous; the
sub-metre pinch points are not, and they are where a lap is lost.

Two consequences of the boundary being a *row of separate ducts* rather than a
wall, both of which will cost you if you ignore them:

1. **The LiDAR sees through the gaps between ducts.** A beam that slips between
   two of them reports the far side of the track, or nothing. A naive "steer at
   the deepest reading" therefore aims the car straight at a duct. Disparity
   extension exists to fix exactly this — see
   [§4.2](04-algorithms.md#42-reactive-nothing-but-the-lidar).
2. **The gaps are not a route.** Going between two ducts is leaving the course.
   The simulator scores a collision when you touch one, so it enforces itself.

---

## 2.2 Topics

```sh
ros2 topic list
ros2 topic info /autodrive/roboracer_1/lidar
ros2 interface show sensor_msgs/msg/LaserScan
```

Everything lives under `/autodrive/roboracer_1/`. Below, `…` stands for that
prefix.

### What you read

| Topic | Type | What it is |
| --- | --- | --- |
| `…/lidar` | `sensor_msgs/LaserScan` | 1080 beams over 270°, 0.06–10 m, 40 Hz |
| `…/front_camera` | `sensor_msgs/Image` | RGB, 48.8° FoV. **Empty in a headless run** |
| `…/imu` | `sensor_msgs/Imu` | Orientation, angular velocity, linear acceleration |
| `…/left_encoder`, `…/right_encoder` | `sensor_msgs/JointState` | Rear wheel angles, 16 PPR × 120 |
| `…/throttle`, `…/steering` | `std_msgs/Float32` | Actuator feedback, what the car is actually doing |
| `…/ips` | `geometry_msgs/Point` | **Ground-truth position** in the `world` frame |
| `…/odom` | `nav_msgs/Odometry` | **Ground-truth pose and velocity.** The one to use |
| `…/lap_count` | `std_msgs/Int32` | Laps completed, cumulative |
| `…/lap_time` | `std_msgs/Float32` | Elapsed time in the lap in progress |
| `…/last_lap_time`, `…/best_lap_time` | `std_msgs/Float32` | As they say. `inf` until the first lap closes |
| `…/collision_count` | `std_msgs/Int32` | Contacts with the boundary, cumulative |
| `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | `world` → `roboracer_1` → sensor frames |

### What you write

| Topic | Type | What it does |
| --- | --- | --- |
| `…/throttle_command` | `std_msgs/Float32` | Normalised throttle, [−1, 1] |
| `…/steering_command` | `std_msgs/Float32` | Normalised steering, [−1, 1] → ±0.5236 rad |

### What you must not write

| Topic | Type | Notes |
| --- | --- | --- |
| `/autodrive/reset_command` | `std_msgs/Bool` | Teleports the car to its spawn and zeroes the lap and collision counters. **The referee's. Off limits (rule 31).** |

---

## 2.3 The restricted topics, and what this hackathon does about them

The AutoDRIVE competition's own rules mark several topics *restricted*: usable
for development and debugging, but not "while autonomously racing at run-time".
Those are `…/ips`, `…/odom`, `/tf`, and the whole race-telemetry set —
`…/lap_count`, `…/lap_time`, `…/last_lap_time`, `…/best_lap_time`,
`…/collision_count`.

**This hackathon lifts that restriction for reading.** Every input topic above
is yours to use during a scored run, ground-truth pose included. Nothing you
*subscribe* to is restricted here.

**Publishing `/autodrive/reset_command` stays restricted.** It is the only
output the competition restricts and it remains off limits, for the obvious
reason: it teleports the car and resets the counters the referee scores from.
Publishing it during a run is interfering with the referee (rule 31), which is
not a penalty but a disqualification.

Why lift the reading restriction at all? Because this is a recruitment
hackathon, not a robotics competition. Writing a particle filter to recover a
pose the simulator is already publishing is a good exercise and a genuinely
hard one, and it is worth **bonus marks** at the interview — but it is not the
thing being assessed, and making it compulsory would mean most teams spend the
whole hackathon on localisation and never write a planner.

So: use `…/odom`. If you would rather not, say so in your `SUBMISSION.md` and
come and defend it.

---

## 2.4 The control interface is not a speed request

This is the difference from Track 1 that catches people.

```
/autodrive/roboracer_1/throttle_command    Float32   [-1, 1]
/autodrive/roboracer_1/steering_command    Float32   [-1, 1]  ->  +-0.5236 rad
```

Throttle is **normalised motor torque**, not a target speed. −1 is full
reverse, 0 is coasting, +1 is everything the motor has. There is no speed
controller anywhere between your node and the wheels, so:

- `throttle = 0.3` is a different speed on the straight than it is in a corner,
  and a different speed again going into one;
- "take this corner at 3 m/s" is a control problem you now own;
- a plan that produces a speed profile — a racing line, an MPC solution — needs
  a controller underneath it before the car will follow it.

**Nothing in this repository writes that controller for you.** The usual shape
is feed-forward proportional to the target speed, PI on the error, a clamped
integral, and a lift-rather-than-brake rule — because a scaled car with no ABS
answers a negative throttle by locking its wheels, and a locked wheel steers
nowhere. [§4.1](04-algorithms.md#41-first-the-thing-that-is-not-an-algorithm)
covers what it has to get right and why it is the first thing to build.

Measure your speed from `…/odom` (which carries velocity) or integrate the
encoders yourself.

```python
from std_msgs.msg import Float32
self.throttle_pub.publish(Float32(data=0.3))
self.steering_pub.publish(Float32(data=-0.5))   # half a lock to the right
```

### Quality of service — read this before you debug for an hour

The bridge publishes and subscribes with `RELIABLE`, `KEEP_LAST(1)`,
`VOLATILE`. Use anything else and **the topics silently do not connect**: a
`BEST_EFFORT` subscriber — which is the natural choice for sensor data, and
what most ROS tutorials show — will never receive one message from a `RELIABLE`
publisher, while `ros2 topic list` still shows the topic and `ros2 topic info`
still shows the publisher.

`devkit_qos()` in `control.py` is the profile. Use it for every subscription
and every publisher that talks to the bridge.

---

## 2.5 The LiDAR scan

```python
angles = scan.angle_min + np.arange(len(scan.ranges)) * scan.angle_increment
```

- 1080 beams, `angle_min` −2.356 rad (−135°) to `angle_max` +2.356 rad,
  0.25° apart, at 40 Hz.
- Index 0 is hard right, the middle index is straight ahead, the last is hard
  left. Take the count from `len(scan.ranges)` rather than hard-coding 1080.
- Positive angles are to the **left**, matching the steering sign convention.
- Range is 0.06 m to **10 m** — a third of Track 1's. On a 30 m track that
  means you cannot see the end of the main straight. Plan accordingly.
- Always clean the array:

```python
ranges = np.nan_to_num(np.asarray(scan.ranges), nan=0.0, posinf=10.0, neginf=0.0)
```

The scanner sits 0.2733 m ahead of the rear axle and 0.096 m up, so a range of
0.3 m in front is already a scrape, not 0.3 m of clearance.

---

## 2.6 Ground-truth pose — use it

`…/odom` gives the car's exact pose and velocity in the `world` frame, with no
noise and no drift. **The hackathon rules allow this and we recommend it**
(§2.3).

```python
from nav_msgs.msg import Odometry

def odom_callback(self, msg):
    self.x = msg.pose.pose.position.x
    self.y = msg.pose.pose.position.y
    q = msg.pose.pose.orientation
    self.yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                          1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    self.speed = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)
```

Why it matters: a purely reactive driver sees 10 m, so it has to slow down for
a corner it has not yet reached. Knowing where you are on the track lets you
brake for a corner you already know is coming, and pick up the throttle before
you can see the exit. That is most of the lap time.

`…/ips` carries the position alone, at the same rate. `…/odom` carries that
plus velocity, so there is rarely a reason to prefer it.

Writing your own localisation is **not required** and it is genuinely hard. If
you do build one and can explain it properly, it is worth bonus marks at the
interview. There is a map in `maps/` to localise against (§2.9), so the
groundwork is there — a particle filter over the LiDAR and that grid is the
standard approach.

---

## 2.7 Driving by hand

```sh
# One-off command: quarter throttle, a touch of left steering
ros2 topic pub --once /autodrive/roboracer_1/throttle_command std_msgs/msg/Float32 "{data: 0.25}"
ros2 topic pub --once /autodrive/roboracer_1/steering_command std_msgs/msg/Float32 "{data: 0.2}"

# Keyboard teleoperation, from the devkit
ros2 run autodrive_roboracer teleop_keyboard

# Watch the state
ros2 topic echo /autodrive/roboracer_1/odom --no-arr
ros2 topic echo /autodrive/roboracer_1/lap_time
```

Remember the commands are level-triggered: a throttle of 0.25 stays 0.25 until
something says otherwise.

To put the car back on the grid outside a scored run, toggle the reset command
and **toggle it back**, or the simulator sits in a reset loop:

```sh
ros2 topic pub --once /autodrive/reset_command std_msgs/msg/Bool "{data: true}"
ros2 topic pub --once /autodrive/reset_command std_msgs/msg/Bool "{data: false}"
```

During a scored run this topic is off limits (rule 31).

---

## 2.8 RViz and Foxglove

```sh
ros2 launch roboracer_referee simulator.launch.py rviz:=true
```

The devkit ships an RViz layout showing the LiDAR, the camera, the vehicle
frames and the referee's status text, plus `/driver/markers` for anything your
own node publishes. Publish a `visualization_msgs/MarkerArray` there in the
`roboracer_1` or `world` frame; the template driver shows how. Seeing where
your algorithm thinks it is aiming is by far the fastest way to work out why it
just hit a duct.

The simulator's own **HUD** is worth a look too, when you are running it with
graphics: speed, throttle, steering, encoder ticks, IMU, the LiDAR preview and
the live race telemetry, all in one panel.

AutoDRIVE also publishes a Foxglove layout in their
[competition repository](https://github.com/AutoDRIVE-Ecosystem/AutoDRIVE-RoboRacer-Sim-Racing/tree/main/foxglove)
if you prefer it to RViz.

---

## 2.9 The map

The simulator ships the circuit as Unity geometry, not as an occupancy grid, so
[`maps/icra26_compete.pgm`](../maps/) was traced off the simulator: ground-truth
pose plus the LiDAR, ray-carved into a grid over several laps. It is a 220 × 476
grid at 5 cm.

```sh
./scripts/track_tool.py validate      # check the grid and the planning geometry
./scripts/track_tool.py centerline    # (re)write maps/icra26_compete_centerline.csv
```

`pure_pursuit` follows that centreline out of the box, which is both the demo
and the proof the map is right — it laps in under 20 seconds without touching
anything.

**Building a better one is still worth doing**, and it is worth bonus marks at
the interview (rule 45). Ours is traced from a reactive driver's wandering, so
it is accurate but not beautiful, and it says nothing about where the fast line
is. Record your own and do better:

```sh
ros2 bag record /autodrive/roboracer_1/lidar /autodrive/roboracer_1/ips \
                /autodrive/roboracer_1/odom /tf /tf_static -o my_lap
```

**None of this affects a scored run.** The referee never opens a map; it reads
the simulator's own lap and collision telemetry. See
[chapter 5](05-evaluation.md). That separation is deliberate, and it is why the
environment worked before this map existed.

---

## 2.10 Vehicle and sensor specifications

The RoboRacer digital twin, from the
[AutoDRIVE technical guide](https://autodrive-ecosystem.github.io/competitions/roboracer-sim-racing-guide-2026).

| Quantity | Value |
| --- | --- |
| Length × width | 0.500 × 0.270 m |
| Wheelbase | 0.324 m |
| Track width | 0.236 m |
| Wheel radius | 0.059 m |
| Total mass | 3.906 kg |
| Centre of mass | (0.155, 0, 0.014) m from the rear axle |
| Drive | All-wheel drive, 428 N·m motor torque |
| Top speed | 22.88 m/s (you will not get near this) |
| Steering | Ackermann, ±0.5236 rad (±30°), max rate 3.2 rad/s |
| Suspension | 500 N/m spring, 100 N·s/m damper |

Sensor frames, relative to `roboracer_1` at the centre of the rear axle:

| Frame | x (m) | y (m) | z (m) |
| --- | ---: | ---: | ---: |
| `lidar` | 0.2733 | 0.0 | 0.096 |
| `front_camera` | −0.015 | 0.0 | 0.150 (pitched 10° down) |
| `ips`, `imu` | 0.08 | 0.0 | 0.055 |
| `left_encoder` / `right_encoder` | 0.0 | ±0.118 | 0.0 |

| Sensor | Specification |
| --- | --- |
| LiDAR | 270° 2D, 1080 beams at 0.25°, 0.06–10 m, 40 Hz |
| Camera | 48.83° FoV, 16:9, JPEG-compressed, RGB |
| IMU | Orientation, angular velocity, linear acceleration |
| Encoders | 16 pulses per revolution, ×120 ratio, rear wheels |
| IPS | Position vector in the `world` frame |

±0.5236 rad is the car's real limit and the simulator will honour all of it —
but a sharper angle at speed is also how you spin, so clamping yourself to
something more conservative while you are getting a driver working is a
reasonable first move. Note also that the 3.2 rad/s rate limit means a step
command does not arrive instantly however hard you ask.

---

Next: **[3. ROS 2 primer](03-workshop.md)**
