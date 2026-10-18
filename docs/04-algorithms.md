# 4. Algorithms to start from

**No driver ships with this repository.** There is no reference implementation
to read, race or copy: `race_ws/src/team_driver` is wiring — it connects to the
simulator, subscribes to the sensors, and crawls forward in a straight line
until it hits something. Everything that makes the car go round is yours to
write.

That is the hackathon. What this chapter gives you instead is the menu: the
approaches that actually work on a 1/10-scale car, what each one needs, what it
costs you to build, and where each breaks on *this* circuit. All of them have
been made to work on a RoboRacer by somebody. Pick one, get it finishing laps,
then make it fast.

Choosing well is part of what is being assessed. **Ambition is not scored** —
ten clean laps from a well-tuned reactive driver beats a half-trained policy
that crashes out on lap three, especially at +10 s a collision. Get something
finishing first, then get clever.

| | Needs | Build cost | Ceiling |
| --- | --- | --- | --- |
| [Wall following](#42-reactive-nothing-but-the-lidar) | LiDAR | An afternoon | Low — will not finish here |
| [Follow-the-gap](#42-reactive-nothing-but-the-lidar) | LiDAR | A day | Medium |
| [Pure pursuit / Stanley](#43-planning-against-a-map) | Map + pose | A day | High |
| [Racing line + speed profile](#43-planning-against-a-map) | Map + pose | Days | Highest |
| [MPC / MPPI](#44-model-based-optimal-control) | Model + pose | Days | Highest |
| [RL / imitation](#45-learned-policies) | Time, GPU | Weeks | Unknown — yours to find out |

---

## 4.1 First, the thing that is not an algorithm

Whatever you pick above will decide a *target speed*. Nothing in this
repository turns one into a throttle, and AutoDRIVE does not take a speed
([§2.4](02-simulator.md#24-the-control-interface-is-not-a-speed-request)) — it
takes normalised torque in [−1, 1]. So "slow to 2 m/s for this corner" is not
something you can ask for. **You need a speed controller, and it is the first
thing to build**, because every algorithm below depends on one and none of them
work well with open-loop throttle.

The standard shape is feed-forward plus a PI trim: the throttle needed to hold
a speed is roughly proportional to that speed, so a feed-forward term carries
most of the load and the integral cleans up what the model gets wrong. You have
measured speed from `…/odom` and from the wheel encoders, and the vehicle
parameters are published in
[§2.10](02-simulator.md#210-vehicle-and-sensor-specifications), so the
feed-forward term is something you can derive rather than guess.

Two things to get right, because both bite:

- **Clamp the integral.** One slow corner is otherwise enough to wind it up to
  the point where it holds the throttle open halfway down the next straight.
- **Decide what an overspeed does.** A scaled car with no ABS answers a
  negative throttle by locking its wheels, and a locked wheel steers nowhere at
  all. Lifting off is often the better answer to being slightly fast; braking
  hard is for when you are badly fast.

A good speed controller is worth real lap time on its own, and it is worth
bonus marks at the interview (rule 45).

---

## 4.2 Reactive: nothing but the LiDAR

Reactive drivers decide from the current scan alone. No map, no memory, no
localisation — which makes them the fastest thing to get running and the
easiest to debug, and caps how good they can get.

### Wall following

Hold a constant distance from one wall with a PID controller. Two LiDAR beams —
one straight out to the side, one angled forwards — give you both the distance
to the wall and its angle, and steering on a point projected *ahead* of the car
rather than on the current error is the difference between tracking the wall
and oscillating about it.

**Build this first if ROS 2 is new to you.** It is about forty lines of real
logic, and if it gets the car moving then the bridge, the QoS, your commands
and the workspace are all correct.

**Do not expect it to be competitive here.** The algorithm assumes a continuous
surface to follow and this circuit does not have one: the boundary is a row of
spaced 33 cm air ducts, so a beam aimed at "the wall" regularly passes between
two of them and reports something metres away. The controller then steers hard
at a wall that was never there. That is the algorithm, not the tuning — and
understanding *why* it fails here is the clearest possible argument for the
next one.

### Follow-the-gap, with disparity extension

The strongest purely reactive approach, and on a circuit with no shipped
racing line it is the one that works today. Three ideas stacked up:

1. **A safety bubble.** Find the closest return and blank out an arc around it,
   so the car can never aim at a point it would clip on the way to.
2. **Disparity extension.** Where the scan jumps from near to far there is
   something the LiDAR can see past but the car cannot fit past. Pull the far
   side of the jump in by half a car width. **This matters more on Track 2 than
   on Track 1**: with a duct row for a boundary the scan is full of near/far
   jumps that look like openings and are not, and without this step the car
   drives between two ducts.
3. **Aim at the widest gap, not the deepest beam.** The deepest beam makes the
   car twitch between two nearly identical directions; the middle of the widest
   run of near-maximal readings does not.

Then scale target speed down with steering angle and with how short the gap
ahead is, and hand that to your speed controller.

**Tuning is the whole game and the sensible direction is often wrong.** The
corridor here is about 0.90 m wide and the car is 0.27 m, so the margins you
assume for the car's half-width and the safety bubble interact: too generous
and disparity extension closes off every gap the car might have driven through,
leaving it nowhere to aim and crawling into things slowly; too tight and it
clips ducts constantly. There is a real optimum and the only way to find it is
to run it.

**Where it breaks:** no memory and no plan. It brakes for a corner only once it
can see it, and it can see 10 m. On a 54 m circuit that means it is always late
on the brakes and early off the throttle.

### Also in this family

**Potential fields** — sum a repulsion from every return and an attraction
towards the track ahead, and steer along the result. Elegant, and prone to
local minima that park the car in a corner. **Bug algorithms** — obstacle
circumnavigation; fine for getting somewhere, far too slow for racing. Worth
knowing about; neither is where the lap time is.

---

## 4.3 Planning against a map

Knowing where you are changes the problem: you can see the corner before the
LiDAR can, which means you can brake before it rather than in it. That is most
of the lap time.

You have what this needs. The simulator publishes ground-truth pose on `…/odom`
and `…/ips` and the rules allow you to use both ([§2.6](02-simulator.md#26-ground-truth-pose--use-it),
rule 35). The simulator ships no occupancy grid, so we traced one from it:
`maps/icra26_compete.pgm` with a centreline in
`maps/icra26_compete_centerline.csv` ([§2.9](02-simulator.md#29-the-map)).
Building a better map than ours — or your own, from your own recorded laps — is
worth bonus marks (rule 45).

### Path tracking

**Pure pursuit** is the standard and the one to start with. Find the point on
your path a lookahead distance ahead of the car, and steer along the circular
arc that reaches it; the steering angle follows from the arc's curvature and
the wheelbase. Two properties make it popular: it is a few lines of geometry,
and the lookahead distance is a single intuitive knob — too short and it saws
at the wheel, too long and it cuts every apex. Scaling lookahead with speed is
the usual refinement.

**Stanley control** steers on cross-track error measured at the front axle plus
a heading term. Sharper than pure pursuit at tracking the line exactly, less
forgiving of a line with discontinuities in it.

Either one will follow the shipped centreline. Neither is fast on its own,
because a centreline driven at one speed is not a lap.

### The two things that make it fast

1. **A speed for every point.** Compute the path's curvature, cap cornering
   speed by the lateral grip you can hold, then propagate braking and
   acceleration limits forwards and backwards around the loop so the car slows
   down *in time*. This is the single biggest win available from a planner, and
   it is why §4.1 comes first: the result is still a target speed, and the
   speed controller has to be good enough to hold it.

2. **A racing line, not a centreline.** Wide in, apex, wide out — shorter and
   faster than the middle of the track. Minimum-curvature and minimum-time
   line optimisation are both well documented and both solvable from the map
   you have. Generating your own line from a map, rather than shipping one as
   data, is explicitly worth bonus marks (rule 45); hand-typed waypoints from
   watching the car are not (rule 36).

### When the line is blocked

A path follower follows its line and nothing else — put an obstacle on that
line and it drives into it. On a circuit the organisers describe as possibly
carrying bifurcations and obstacles, that is not hypothetical. Two answers:

- **Plan around it.** A* or Dijkstra over a grid, or a sampling planner
  (RRT\*), re-run locally when the scan says the line is blocked.
- **Switch behaviour.** Follow the line when the track is clear, fall back to
  gap following when it is not. Cruder, robust, and a genuinely good answer.

---

## 4.4 Model-based optimal control

Instead of tracking a path, optimise the controls directly against a model of
the car, every cycle.

**MPC.** Predict the car's motion over a short horizon with a kinematic or
dynamic bicycle model, solve for the throttle and steering sequence that
minimises a cost — lap progress, deviation from a line, control effort —
subject to the actuator and track limits, apply the first control, repeat. It
handles the speed and steering problem in one place instead of two, which is
its real attraction here, and the vehicle parameters you need are all published
in [§2.10](02-simulator.md#210-vehicle-and-sensor-specifications). The costs
are solve time inside a 40 Hz budget and a model that has to be good enough.

**MPPI** replaces the solver with sampling: roll out several thousand random
control sequences, weight them by cost, take the weighted average. No
derivatives and no convexity needed, it parallelises onto the GPU, and it
copes with a cost function you can only evaluate. Popular on scaled racing
cars for exactly those reasons.

**LQR** around a reference trajectory is the cheap classical option — fast and
principled, but linear, so it gives up at the limit of grip.

Principled, fast, and the tuning is honest work. This is a strong choice if
somebody on the team has done control theory.

---

## 4.5 Learned policies

Allowed, encouraged, and worth bonus marks if you can explain what you built
(rule 45). Also the easiest way to spend three weeks and finish with nothing
that laps, so read §4.6 before committing.

**Reinforcement learning.** The AutoDRIVE bridge is an ordinary ROS 2
interface, so you can wrap it as a Gymnasium environment and train a policy
against the simulator directly — scan in, throttle and steering out. Expect the
hard parts to be reward shaping (progress, not speed; penalise contact
properly), wall-clock training time — the simulator runs in real time, unlike a
stepped gym — and keeping inference inside the control loop's budget. Training
on the *practice* build and racing on *compete* is also exactly the
generalisation problem ICRA set.

**Imitation learning.** Drive well by some other means — teleop
([§2.7](02-simulator.md#27-driving-by-hand)), or one of the planners above —
record it, and train a policy to copy it. Cheap to get working, and it inherits
whatever your teacher does badly. Behaviour cloning is the simple version;
DAgger, which asks the expert what it would have done in the states the student
actually visits, is the standard fix for the compounding-error problem that
kills plain cloning.

**End-to-end from the camera.** Possible, and the camera is published — but
note that headless runs produce no image
([§2.2](02-simulator.md#22-topics)), which constrains how you train and how
you are judged.

**Residual and hybrid approaches.** Learn a correction on top of a classical
controller rather than replacing it. Much less likely to fail catastrophically,
much easier to explain, and it still counts as replacing the approach.

**What rule 42 asks of a learned component.** Exactly what it asks of an `if`
statement — but what it asks for is the *method*, not the weights. Nobody will
ask what a particular weight is for. Be ready to say what the network sees and
emits, how you trained it (the environment, the reward, the data and how much
of it), why that method rather than the alternatives, how you checked it works,
and where it fails. Explain how the box was built and you have explained the
box.

---

## 4.6 What to build, in what order

Roughly in order of lap time gained per hour spent:

1. **A speed controller** (§4.1). Everything else needs one.

2. **Stop hitting things.** A collision is +10 s and eleven of them is a
   disqualification, against a lap of roughly 20 s. Nothing else on this list
   comes close. Most contact is corner entry speed rather than steering: decide
   speed from the distance to what is ahead, not just from the steering angle
   you are already holding.

3. **Something that finishes ten laps.** Any of §4.2 will do. A result you can
   measure beats an idea you cannot.

4. **Use your position** (§4.3). You know exactly where you are and a reactive
   planner throws that away. Even a coarse "which section of the track am I in"
   lets you pick different behaviour for a straight and a chicane — and on a
   circuit you can only see 10 m of, memory is worth more than it was on
   Track 1.

5. **A line and a speed profile** (§4.3). This is where the lap time is, and it
   is defensible in an interview.

6. **Then get ambitious** (§4.4, §4.5) — with something that already finishes
   in reserve.

**Measure everything.** Run `./scripts/evaluate.sh` after each change:

```sh
./scripts/evaluate.sh --team my_team --laps 10
```

An idea that sounds better and is not shows up in the times immediately. Two
warnings about reading those times:

- **The simulator is not deterministic.** The same code over the same ten laps
  will not give the same collision count twice. That is why the judges take the
  best of three (rule 23), and why a single run is not evidence that a change
  helped.
- **Two laps is not enough to measure a collision rate.** Short runs are for
  iterating; judge a change on a full-length one before you believe it.

---

## 4.7 Where to read more

Starting points, not a reading list to finish:

- **Follow-the-gap and disparity extension** — Sezer & Gokasan, *A novel
  obstacle avoidance algorithm: "Follow the Gap Method"* (2012); Otterness,
  *The "disparity extender" algorithm* (2019).
- **Pure pursuit** — Coulter, *Implementation of the Pure Pursuit Path Tracking
  Algorithm*, CMU-RI-TR-92-01.
- **Racing lines and speed profiles** — Heilmeier et al., *Minimum curvature
  trajectory planning and control for an autonomous race car* (2019).
- **MPC and MPPI on scaled cars** — Williams et al., *Information-theoretic
  MPC for model-based reinforcement learning* (2017).
- **The F1TENTH course materials**, which cover most of §4.2 and §4.3 from
  first principles and are written for exactly this vehicle.

And the obvious one: chapter 2 is the specification of the car you are
controlling. Most of the tuning questions in this chapter are answered by
[§2.10](02-simulator.md#210-vehicle-and-sensor-specifications).

---

Whatever you build, put it behind `ros2 run team_driver driver` (rule 38) and
declare its dependencies (rule 37).

Next: **[5. Evaluation](05-evaluation.md)**
