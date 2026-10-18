import math
import unittest

import numpy as np

from team_driver.path_control import PathController


class SpeedProfileTests(unittest.TestCase):
    def setUp(self):
        self.points = np.loadtxt('/hackathon/maps/icra26_compete_centerline.csv', delimiter=',')
        self.controller = PathController(self.points, max_speed=3.0, corner_speed=0.4,
                                         acceleration_limit=1.5)
        self.angles = np.linspace(-2.356, 2.356, 1080)
        self.ranges = np.full(1080, 10.0)

    def test_profile_limits_and_closed_lap(self):
        controller = self.controller
        squared = controller.speed_profile ** 2
        following = np.roll(squared, -1)
        self.assertTrue(np.all(squared <= 9.0))
        self.assertTrue(np.all(squared * controller.curvatures <= controller.lateral_acceleration + 1e-8))
        self.assertTrue(np.all(squared - following <= 2 * controller.braking_deceleration * controller.segment_lengths + 1e-8))
        self.assertTrue(np.all(following - squared <= 2 * controller.acceleration_limit * controller.segment_lengths + 1e-8))
        self.assertTrue(np.any(squared < np.minimum(9.0, controller.lateral_acceleration / np.maximum(controller.curvatures, 1e-6)) - 0.1))
        point, _, _ = controller.sample(controller.lap_length + 0.1)
        wrapped, _, _ = controller.sample(0.1)
        np.testing.assert_allclose(point, wrapped)

    def test_brakes_release_with_steering_and_at_low_speed(self):
        controller = self.controller
        controller.target_speed = 1.0
        controller.steering = 0.0
        straight = controller.speed_control(1.0, 2.5, 0.025)
        controller.steering = 1.0
        turning = controller.speed_control(1.0, 2.5, 0.025)
        self.assertLess(straight, turning)
        self.assertLess(turning, 0.0)
        self.assertGreaterEqual(straight, -controller.max_brake)
        self.assertEqual(controller.speed_control(0.0, 0.2, 0.025), 0.0)

    def test_acceleration_ramp_and_integral_bounds(self):
        controller = self.controller
        for iteration in range(400):
            previous = controller.target_speed
            throttle = controller.speed_control(3.0, 0.0, 0.025)
            self.assertLessEqual(controller.target_speed - previous, 1.5 * 0.025 + 1e-9)
            self.assertGreaterEqual(throttle, 0.0)
            self.assertLessEqual(throttle, controller.max_throttle)
        self.assertLessEqual(abs(controller.integral), 0.5)

    def test_bad_scan_and_off_track_stop(self):
        controller = self.controller
        self.assertEqual(controller.plan_path([], [], 0.0, 0.025, (0.8, 3.16), -math.pi / 2), (0.0, 0.0))
        invalid = self.ranges.copy()
        invalid[np.abs(self.angles) < 0.1] = np.nan
        self.assertLessEqual(controller.plan_path(invalid, self.angles, 1.0, 0.025, (0.8, 3.16), -math.pi / 2)[1], 0.0)
        self.assertEqual(controller.plan_path(self.ranges, self.angles, 0.0, 0.025, (100, 100), 0.0), (0.0, 0.0))

    def test_obstacle_on_route_but_not_beside_route(self):
        controller = self.controller
        position = self.points[0]
        heading = math.atan2(controller.segments[0, 1], controller.segments[0, 0])
        obstacle, _, _ = controller.sample(1.0)
        offset = obstacle - position
        forward = math.cos(heading) * offset[0] + math.sin(heading) * offset[1] - 0.2733
        left = -math.sin(heading) * offset[0] + math.cos(heading) * offset[1]
        distance = controller.obstacle_distance(np.array([math.hypot(forward, left)]),
                                                np.array([math.atan2(left, forward)]), position, heading, 0.0, 2.0)
        self.assertGreater(distance, 0.75)
        self.assertLessEqual(distance, 1.04)
        beside = controller.obstacle_distance(np.array([math.hypot(forward, left + 0.6)]),
                                              np.array([math.atan2(left + 0.6, forward)]), position, heading, 0.0, 2.0)
        self.assertTrue(math.isinf(beside))

    def test_idealized_path_tracking(self):
        controller = self.controller
        position = np.array([0.8, 3.16])
        yaw = -math.pi / 2
        speed = 0.0
        visited = set()
        largest_error = 0.0
        for iteration in range(6000):
            steering, throttle = controller.plan_path(self.ranges, self.angles, speed, 0.025, position, yaw)
            self.assertTrue(math.isfinite(steering) and math.isfinite(throttle))
            speed += float(np.clip(controller.target_speed - speed, -1.3 * 0.025, 1.5 * 0.025))
            position += speed * 0.025 * np.array([math.cos(yaw), math.sin(yaw)])
            yaw += speed / 0.324 * math.tan(steering * 0.5236) * 0.025
            visited.add(controller.index)
            largest_error = max(largest_error, controller.cross_track_error)
        self.assertGreater(len(visited), len(self.points) * 0.95)
        self.assertLess(largest_error, 0.3)


if __name__ == '__main__':
    unittest.main()
