# Workshop material

Reference material from the ROS 2 workshop, kept here so you can go back to it.
None of it is part of the hackathon build or the judging environment.

| | |
| --- | --- |
| [`slides/`](slides/) | ROS 2 theory and practical, Docker, reactive navigation. Markdown source and PDFs. |
| [`ros2_ws/`](ros2_ws/) | Teaching packages: publishers, subscribers, services, actions, custom messages, bag recording. |
| [`assets/`](assets/) | Images used by the slides. |

Start with [`../docs/03-workshop.md`](../docs/03-workshop.md) for the short
version.

---

## Paths in the slides are out of date

The slides were written against the old repository layout and the old
container. The concepts are unchanged; the paths are not.

| Slides say | Now |
| --- | --- |
| `~/F1Tenth_Workshop/install_linux` | `install/linux/` (also `install/macos`, `install/windows`) |
| `/f1tenth_workshop/` inside the container | `/hackathon/` |
| `/f1tenth_workshop/f1tenth_simulator` | `race_ws/src/team_driver/` — and the gap finder and wall follower templates the slides work through are no longer provided; see [docs/04-algorithms.md](../docs/04-algorithms.md) |
| `ros2_ws` | `race_ws` for your entry; `workshop/ros2_ws` for these teaching packages |
| Edit `sim.yaml` and rebuild to change map | `ros2 launch roboracer_referee simulator.launch.py` |

Also note that F1TENTH is now **RoboRacer**. The older simulator repositories
are still published under the old name (`f1tenth_gym`, `f1tenth_gym_ros`,
`f1tenth_racetracks`), so those names appear in these slides and were correct
when they were written.

## The simulator sections are Track 1's, not this one

Anything in here about `f1tenth_gym`, `/scan`, `/drive` or
`AckermannDriveStamped` describes the **Track 1** environment. Track 2 runs the
AutoDRIVE Simulator, where the topics live under `/autodrive/roboracer_1/` and
the car takes a normalised throttle rather than a speed:

| Slides say | Track 2 |
| --- | --- |
| `/scan` | `/autodrive/roboracer_1/lidar` |
| `/ego_racecar/odom` | `/autodrive/roboracer_1/odom` |
| `/drive` (`AckermannDriveStamped`) | `/autodrive/roboracer_1/throttle_command` and `/steering_command`, both `std_msgs/Float32` |
| `ros2 launch f1tenth_gym_ros gym_launch.py` | `ros2 launch roboracer_referee simulator.launch.py` |

The ROS 2 concepts — nodes, topics, messages, parameters, launch files,
`colcon` — are identical and are the reason to read this material.
[docs/02-simulator.md](../docs/02-simulator.md) is the authority on what Track 2
actually publishes.

---

## Building the teaching packages

They are a separate workspace on purpose, so they are not compiled during an
evaluation run.

```sh
cd /hackathon/workshop/ros2_ws
colcon build --symlink-install
source install/local_setup.bash
ros2 run my_package minimal_publisher
```
