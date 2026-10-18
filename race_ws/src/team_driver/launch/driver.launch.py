"""Start your driver with the parameters from config/driver_params.yaml.

    ros2 launch team_driver driver.launch.py

The simulator is separate: `ros2 launch roboracer_referee simulator.launch.py`.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory('team_driver'), 'config', 'driver_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('params', default_value=default_params,
                              description='Parameter YAML for the driver node'),
        Node(
            package='team_driver',
            executable='driver',
            name='driver',
            output='screen',
            parameters=[LaunchConfiguration('params')],
        ),
    ])
