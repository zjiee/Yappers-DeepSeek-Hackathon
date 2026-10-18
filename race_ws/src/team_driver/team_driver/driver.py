"""Conservative centreline or gap following with feedback speed control."""

import math
import time

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32

from team_driver.gap_control import GapController
from team_driver.path_control import PathController


class Driver(Node):
    def __init__(self):
        super().__init__('driver')
        self.declare_parameter('vehicle_ns', '/autodrive/roboracer_1')
        self.declare_parameter('planner', 'pure_pursuit')
        self.declare_parameter('centreline_csv', '/hackathon/maps/icra26_compete_centerline.csv')
        self.planner = self.get_parameter('planner').value
        defaults = PathController.DEFAULTS if self.planner == 'pure_pursuit' else GapController.DEFAULTS
        settings = {}
        for name, default in defaults.items():
            self.declare_parameter(name, default)
            settings[name] = self.get_parameter(name).value
        if self.planner == 'pure_pursuit':
            points = np.loadtxt(self.get_parameter('centreline_csv').value, delimiter=',')
            self.controller = PathController(points, **settings)
        elif self.planner == 'gap':
            self.controller = GapController(**settings)
        else:
            raise ValueError('planner must be pure_pursuit or gap')
        namespace = self.get_parameter('vehicle_ns').value.rstrip('/')
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.throttle_pub = self.create_publisher(Float32, f'{namespace}/throttle_command', qos)
        self.steering_pub = self.create_publisher(Float32, f'{namespace}/steering_command', qos)
        self.create_subscription(Odometry, f'{namespace}/odom', self.odom_callback, qos)
        self.create_subscription(LaserScan, f'{namespace}/lidar', self.scan_callback, qos)
        self.speed = 0.0
        self.position = None
        self.yaw = 0.0
        self.last_odom = None
        self.last_scan = None
        self.last_report = 0.0
        self.create_timer(0.1, self.watchdog)
        self.get_logger().info(
            f'{self.planner} driver ready; max_speed={self.controller.max_speed:.2f} m/s, '
            f'acceleration_limit={self.controller.acceleration_limit:.2f} m/s^2; waiting for sensors.')

    def odom_callback(self, message):
        velocity = message.twist.twist.linear
        speed = math.hypot(velocity.x, velocity.y)
        if math.isfinite(speed):
            self.speed = speed
            pose = message.pose.pose
            self.position = (pose.position.x, pose.position.y)
            rotation = pose.orientation
            self.yaw = math.atan2(
                2.0 * (rotation.w * rotation.z + rotation.x * rotation.y),
                1.0 - 2.0 * (rotation.y * rotation.y + rotation.z * rotation.z))
            self.last_odom = time.monotonic()

    def scan_callback(self, scan):
        now = time.monotonic()
        elapsed = 0.025 if self.last_scan is None else now - self.last_scan
        self.last_scan = now
        if self.last_odom is None or now - self.last_odom > 0.5:
            self.stop()
            return
        angles = scan.angle_min + np.arange(len(scan.ranges)) * scan.angle_increment
        if self.planner == 'pure_pursuit':
            steering, throttle = self.controller.plan_path(
                scan.ranges, angles, self.speed, elapsed, self.position, self.yaw)
        else:
            steering, throttle = self.controller.plan(scan.ranges, angles, self.speed, elapsed)
        self.publish(steering, throttle)
        if now - self.last_report > 2.0:
            detail = ''
            if self.planner == 'pure_pursuit':
                detail = (f' limit={self.controller.limit_reason}'
                          f' path_error={self.controller.cross_track_error:.2f}m')
            self.get_logger().info(
                f'speed={self.speed:.2f} target={self.controller.target_speed:.2f} m/s '
                f'steering={steering:.2f} throttle={throttle:.3f}{detail}')
            self.last_report = now

    def watchdog(self):
        now = time.monotonic()
        if (self.last_scan is None or self.last_odom is None
                or now - self.last_scan > 0.5 or now - self.last_odom > 0.5):
            self.stop()

    def publish(self, steering, throttle):
        self.steering_pub.publish(Float32(data=float(np.clip(steering, -1.0, 1.0))))
        self.throttle_pub.publish(Float32(data=float(np.clip(throttle, -1.0, 1.0))))

    def stop(self):
        self.controller.reset()
        self.publish(0.0, 0.0)


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = Driver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
