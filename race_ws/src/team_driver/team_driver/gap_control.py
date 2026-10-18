"""Geometry and speed control, independent of ROS for offline checks."""

import math

import numpy as np


class GapController:
    DEFAULTS = {
        'max_range': 10.0,
        'max_speed': 1.0,
        'corner_speed': 0.45,
        'vehicle_half_width': 0.135,
        'clearance_margin': 0.05,
        'bubble_radius': 0.20,
        'disparity_threshold': 0.30,
        'stop_distance': 0.40,
        'lookahead': 0.65,
        'speed_feedforward': 0.04,
        'speed_kp': 0.10,
        'speed_ki': 0.04,
        'max_throttle': 0.16,
        'max_brake': 0.04,
        'acceleration_limit': 0.5,
    }

    def __init__(self, **settings):
        unknown = set(settings) - set(self.DEFAULTS)
        if unknown:
            raise ValueError(f'Unknown settings: {unknown}')
        for name, default in self.DEFAULTS.items():
            value = float(settings.get(name, default))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
            setattr(self, name, value)
        if self.max_throttle > 1 or self.max_brake > 1:
            raise ValueError('Throttle limits must not exceed 1')
        if self.corner_speed > self.max_speed:
            raise ValueError('corner_speed must not exceed max_speed')
        self.reset()

    def reset(self):
        self.integral = 0.0
        self.target_speed = 0.0
        self.steering = 0.0

    def stop(self, speed):
        self.reset()
        return 0.0, -self.max_brake if speed > 0.4 else 0.0

    def plan(self, ranges, angles, speed, elapsed):
        ranges = np.asarray(ranges, dtype=float)
        angles = np.asarray(angles, dtype=float)
        if (ranges.ndim != 1 or ranges.shape != angles.shape or ranges.size < 3
                or not np.all(np.isfinite(angles)) or not math.isfinite(speed)):
            return self.stop(0.0)
        if not math.isfinite(elapsed) or elapsed <= 0:
            return self.stop(speed)
        elapsed = min(elapsed, 0.1)
        sector = np.abs(angles) <= math.radians(95)
        angles = angles[sector]
        ranges = ranges[sector]
        if angles.size < 3 or np.any(np.diff(angles) <= 0):
            return self.stop(speed)
        ranges = np.clip(np.nan_to_num(
            ranges, nan=0.0, posinf=self.max_range, neginf=0.0), 0.0, self.max_range)
        forward = np.abs(angles) < math.radians(12)
        if not np.any(forward) or np.any(ranges[forward] < self.stop_distance):
            return self.stop(speed)

        expanded = ranges.copy()
        half_width = self.vehicle_half_width + self.clearance_margin
        jumps = np.flatnonzero(np.abs(np.diff(ranges)) > self.disparity_threshold)
        for index in jumps:
            near_index = index if ranges[index] < ranges[index + 1] else index + 1
            distance = ranges[near_index]
            spread = math.asin(min(1.0, half_width / max(distance, 0.01)))
            if near_index == index:
                affected = (angles >= angles[index]) & (angles <= angles[index] + spread)
            else:
                affected = (angles <= angles[index + 1]) & (angles >= angles[index + 1] - spread)
            expanded[affected] = np.minimum(expanded[affected], distance)

        nearest = int(np.argmin(ranges))
        bubble_angle = math.asin(min(1.0, self.bubble_radius / max(ranges[nearest], 0.01)))
        expanded[np.abs(angles - angles[nearest]) <= bubble_angle] = 0.0
        best_range = float(np.max(expanded))
        if best_range < self.stop_distance + 0.15:
            return self.stop(speed)
        available = expanded >= max(self.stop_distance + 0.15, 0.75 * best_range)
        edges = np.diff(np.concatenate(([False], available, [False])).astype(int))
        starts = np.flatnonzero(edges == 1)
        ends = np.flatnonzero(edges == -1) - 1
        if starts.size == 0:
            return self.stop(speed)
        widths = angles[ends] - angles[starts]
        centres = (angles[ends] + angles[starts]) / 2.0
        selected = int(np.argmax(widths - 0.05 * np.abs(centres)))
        target_angle = float(centres[selected])
        steering_angle = math.atan2(2.0 * 0.324 * math.sin(target_angle), self.lookahead)
        desired = float(np.clip(steering_angle / 0.5236, -1.0, 1.0))
        steering_step = 2.5 * elapsed
        self.steering += float(np.clip(desired - self.steering, -steering_step, steering_step))

        forward_clearance = float(np.min(ranges[forward])) - self.stop_distance
        clearance_speed = math.sqrt(2.0 * 0.7 * max(0.0, forward_clearance))
        corner_limit = self.max_speed - (self.max_speed - self.corner_speed) * abs(desired)
        target = min(corner_limit, clearance_speed)
        return self.steering, self.speed_control(target, speed, elapsed)

    def speed_control(self, target, speed, elapsed):
        self.target_speed = min(target, self.target_speed + self.acceleration_limit * elapsed)
        error = self.target_speed - speed
        if error < -0.1:
            self.integral = 0.0
            throttle = -self.max_brake if error < -0.8 else 0.0
        else:
            proposed = float(np.clip(self.integral + error * elapsed, -0.5, 0.5))
            command = self.speed_feedforward * self.target_speed + self.speed_kp * error + self.speed_ki * proposed
            if 0.0 <= command <= self.max_throttle:
                self.integral = proposed
            throttle = float(np.clip(command, 0.0, self.max_throttle))
        return throttle
