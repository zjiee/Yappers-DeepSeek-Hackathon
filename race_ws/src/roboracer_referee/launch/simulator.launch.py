"""Bring up the AutoDRIVE Simulator and the devkit bridge.

    ros2 launch roboracer_referee simulator.launch.py
    ros2 launch roboracer_referee simulator.launch.py headless:=true rviz:=false

    # against a simulator already running, here or on your host machine
    ros2 launch roboracer_referee simulator.launch.py simulator:=false

Two processes have to be running for a single topic to appear:

    AutoDRIVE Simulator  --(websocket, port 4567)-->  autodrive_bridge  --> ROS 2

The direction matters and it is the opposite of what people expect. The
**bridge is the server**: it listens on 4567. The **simulator is the client**:
it is given an address with `-ip`/`-port` and dials out to it on startup. So
the bridge has to be up first, which is what the delay below is for.

This launch file does not reimplement the devkit's own bringup. It runs the
devkit's `autodrive_bridge` through `roboracer_referee/sim_bridge`, which
imports that node unmodified and guards one startup race that otherwise
deadlocks every automated headless run. Read the docstring in sim_bridge.py
before assuming it is a wrapper for the sake of one: it is the difference
between a run that starts and a run that hangs with a full topic list and no
messages on any of it.
"""

import os
import shutil

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, LogInfo,
                            OpaqueFunction, TimerAction)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# Where scripts/fetch_simulator.sh puts the Unity build, in order of
# preference. The bind-mounted repository first, so re-fetching a newer
# simulator on the host is picked up without rebuilding anything.
SIM_SEARCH_PATHS = (
    "/hackathon/simulator/autodrive_simulator/AutoDRIVE Simulator.x86_64",
    "/opt/autodrive_simulator/AutoDRIVE Simulator.x86_64",
)


def find_simulator() -> str:
    """Locate the simulator executable, or return "" if it has not been fetched."""
    override = os.environ.get("AUTODRIVE_SIM_PATH", "").strip()
    candidates = ([override] if override else []) + list(SIM_SEARCH_PATHS)
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return ""


def _setup(context, *_args, **_kwargs):
    def arg(name):
        return LaunchConfiguration(name).perform(context).strip()

    def flag(name):
        return arg(name).lower() in ("true", "1", "yes")

    port = arg("port")
    host = arg("host")

    bridge = Node(
        package="roboracer_referee",
        executable="sim_bridge",
        name="autodrive_bridge",
        emulate_tty=True,
        output="screen",
    )

    actions = [bridge]

    if flag("simulator"):
        executable = find_simulator()
        if not executable:
            return [LogInfo(msg=(
                "\n[simulator.launch.py] The AutoDRIVE Simulator is not installed.\n"
                "  Fetch it once, on the host:   ./scripts/fetch_simulator.sh\n"
                "  Or run it on your own machine and launch with simulator:=false.\n"
                "  Looked in: " + ", ".join(SIM_SEARCH_PATHS) + "\n"))]

        command = [executable, "-ip", host, "-port", port]
        if flag("headless"):
            # -batchmode -nographics creates no graphics device at all. The
            # physics, the LiDAR and the lap timing all still run, and it is
            # roughly an order of magnitude cheaper than rendering. The front
            # camera is the one thing it cannot produce - see docs/02.
            command += ["-batchmode", "-nographics"]
        elif not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
            # No display, but something wants pixels (the camera). A virtual
            # framebuffer is the documented way to get them.
            command = ["xvfb-run", "-a"] + command

        actions.append(TimerAction(
            period=float(arg("simulator_delay_s")),
            actions=[ExecuteProcess(cmd=command, output="screen",
                                    name="autodrive_simulator")],
        ))

    if flag("rviz"):
        rviz_config = os.path.join(
            get_package_share_directory("roboracer_referee"), "rviz", "race.rviz")
        if not os.path.isfile(rviz_config):
            rviz_config = os.path.join(
                get_package_share_directory("autodrive_roboracer"),
                "rviz", "autodrive_roboracer.rviz")
        actions.append(Node(
            package="rviz2",
            executable="rviz2",
            name="rviz",
            output="log",
            arguments=["-d", rviz_config],
            condition=IfCondition(LaunchConfiguration("rviz")),
        ))

    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("simulator", default_value="true",
                              description="Start the AutoDRIVE Simulator process here. "
                                          "Set false to drive a simulator you started "
                                          "yourself, on this machine or another."),
        DeclareLaunchArgument("headless", default_value="false",
                              description="Run the simulator with -batchmode -nographics: "
                                          "no window, no GPU, much faster, no camera."),
        DeclareLaunchArgument("rviz", default_value="true",
                              description="Open RViz alongside the simulator"),
        DeclareLaunchArgument("host", default_value="127.0.0.1",
                              description="Address the simulator dials to reach the bridge"),
        DeclareLaunchArgument("port", default_value="4567",
                              description="Port the bridge listens on"),
        DeclareLaunchArgument("simulator_delay_s", default_value="4.0",
                              description="Seconds to let the bridge start listening before "
                                          "the simulator tries to connect to it"),
        OpaqueFunction(function=_setup),
    ])
