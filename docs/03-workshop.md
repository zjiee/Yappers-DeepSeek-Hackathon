# 3. ROS 2 primer

If ROS 2 is new to you, start here. If you sat through the workshop, skip to
[chapter 4](04-algorithms.md).

You need surprisingly little ROS to win this. A node, a subscriber, a
publisher, and parameters — that is the whole surface area of a competitive
entry.

---

## 3.1 The five ideas

**Node** — one process doing one job. Your driver is a node. The AutoDRIVE
bridge is a node. The referee is a node.

**Topic** — a named channel carrying one message type.
`/autodrive/roboracer_1/lidar` carries LiDAR;
`/autodrive/roboracer_1/throttle_command` carries throttle. Publishers and
subscribers find each other automatically; neither knows the other exists.

**Message** — a typed struct. `sensor_msgs/LaserScan` has `ranges`,
`angle_min`, `angle_increment`. Inspect any type with
`ros2 interface show <type>`.

**Parameter** — a named value you can set at launch without editing code. This
is how you tune without rebuilding, and it is worth using from day one.

**Workspace** — a folder of packages that `colcon build` compiles and
`source install/local_setup.bash` puts on your path. Yours is
`/hackathon/race_ws`.

---

## 3.2 The whole pattern

```python
import rclpy
from rclpy.node import Node
from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile,
                       QoSReliabilityPolicy)
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32

NS = '/autodrive/roboracer_1'

# The AutoDRIVE bridge publishes RELIABLE / KEEP_LAST(1) / VOLATILE. Match it,
# or your subscription silently receives nothing at all - see §3.5.
QOS = QoSProfile(durability=QoSDurabilityPolicy.VOLATILE,
                 reliability=QoSReliabilityPolicy.RELIABLE,
                 history=QoSHistoryPolicy.KEEP_LAST, depth=1)


class Driver(Node):
    def __init__(self):
        super().__init__('driver')
        self.declare_parameter('throttle', 0.2)
        self.throttle = self.get_parameter('throttle').value

        self.throttle_pub = self.create_publisher(Float32, f'{NS}/throttle_command', QOS)
        self.steering_pub = self.create_publisher(Float32, f'{NS}/steering_command', QOS)
        self.create_subscription(LaserScan, f'{NS}/lidar', self.scan_callback, QOS)

    def scan_callback(self, scan):
        self.steering_pub.publish(Float32(data=0.0))
        self.throttle_pub.publish(Float32(data=float(self.throttle)))


def main():
    rclpy.init()
    rclpy.spin(Driver())
```

Everything else is the driving algorithm.

---

## 3.3 Commands worth knowing

```sh
ros2 topic list                       # what exists
ros2 topic echo /autodrive/roboracer_1/lap_count      # watch messages go by
ros2 topic hz /autodrive/roboracer_1/lidar            # rate - is anything alive?
ros2 topic info /autodrive/roboracer_1/lidar --verbose   # publishers, subscribers, QoS
ros2 interface show sensor_msgs/msg/LaserScan
ros2 node list
ros2 param list /driver
ros2 param set /driver throttle 0.3   # retune a running node
ros2 run <package> <executable>
ros2 launch <package> <file.launch.py>
```

When something does not work, `ros2 topic hz` is almost always the fastest way
to find out which link in the chain is dead.

---

## 3.4 Building

```sh
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash
```

`--symlink-install` makes Python edits take effect immediately. You only need
to rebuild after adding a new file or editing `setup.py`.

Build one package only:

```sh
colcon build --symlink-install --packages-select team_driver
```

---

## 3.5 Two things that will waste an afternoon

Both of these look like a broken simulator and are not.

**Quality of Service.** ROS 2 subscriptions and publishers negotiate a
contract, and an incompatible pair simply never connects — no error, no
warning. `ros2 topic list` still lists the topic and `ros2 topic info` still
shows a publisher. The AutoDRIVE bridge is `RELIABLE`, `KEEP_LAST(1)`,
`VOLATILE`; a `BEST_EFFORT` subscriber, which is the natural choice for sensor
data and what most tutorials show, will never receive one message from it. Use
the profile above, or `devkit_qos()` from
[`driver.py`](../race_ws/src/team_driver/team_driver/driver.py).

**Start order.** The bridge listens on port 4567 and the simulator dials out to
it. If the simulator starts first it has nothing to connect to, and you get a
full topic list with no data on any of it. `simulator.launch.py` handles the
ordering for you; if you start them by hand, bridge first.

---

## 3.6 Workshop material

The full workshop content is in [`workshop/`](../workshop/):

| | |
| --- | --- |
| [`workshop/slides/`](../workshop/slides/) | ROS 2 theory and practical slides, Docker, reactive navigation |
| [`workshop/ros2_ws/`](../workshop/ros2_ws/) | Teaching packages: publishers, subscribers, services, actions, custom messages, bag recording |
| [`workshop/ros2_ws/README.md`](../workshop/ros2_ws/README.md) | Walkthrough for those packages |

The workshop workspace is separate from `race_ws` on purpose — it is reference
material, and it is not built during evaluation. It was written against a
different ROS distribution and uses `/scan` and `/drive` rather than the
AutoDRIVE topics; the concepts carry over unchanged, the topic names do not.

---

## 3.7 Further reading

- [ROS 2 Humble tutorials](https://docs.ros.org/en/humble/Tutorials.html) — the
  official ones are good, and Humble is what this image runs. The beginner CLI
  and client library sections are enough.
- [AutoDRIVE technical guide](https://autodrive-ecosystem.github.io/competitions/roboracer-sim-racing-guide-2026) —
  the simulator, the devkit, the vehicle and every sensor, from the people who
  built it. Read it; this repository summarises it but does not replace it.
- [RoboRacer (F1TENTH) course materials](https://f1tenth-coursekit.readthedocs.io/) —
  lectures on reactive methods, pure pursuit and planning.
- [AutoDRIVE Ecosystem paper](https://doi.org/10.3390/robotics12030077) — Samak
  et al., *Robotics* 12(3), 2023, if you want the design rationale.

---

Next: **[4. Algorithms to start from](04-algorithms.md)**
