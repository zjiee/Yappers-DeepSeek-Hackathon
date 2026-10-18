"""Pure pursuit with a closed-loop, curvature-limited speed profile."""

import math

import numpy as np

from team_driver.gap_control import GapController


class PathController(GapController):
    DEFAULTS = {
        **GapController.DEFAULTS,
        'lateral_acceleration': 2.8,
        'braking_deceleration': 1.3,
        'braking_reaction_time': 0.20,
        'braking_margin': 0.15,
        'lookahead_time': 0.08,
        'max_lookahead': 0.95,
        'acceleration_feedforward': 0.025,
        'brake_kp': 0.05,
        'brake_deadband': 0.15,
    }

    def __init__(self, points, **settings):
        super().__init__(**settings)
        self.points = np.asarray(points, dtype=float)
        if (self.points.ndim != 2 or self.points.shape[1] != 2
                or len(self.points) < 5 or not np.all(np.isfinite(self.points))):
            raise ValueError('Centreline must contain at least five finite x,y points')
        self.segments = np.roll(self.points, -1, axis=0) - self.points
        self.segment_lengths = np.linalg.norm(self.segments, axis=1)
        if np.any(self.segment_lengths <= 1e-6):
            raise ValueError('Centreline must not contain repeated adjacent points')
        self.arc = np.concatenate(([0.0], np.cumsum(self.segment_lengths)))
        self.lap_length = float(self.arc[-1])
        if self.max_lookahead < self.lookahead or self.lap_length < self.max_lookahead:
            raise ValueError('Lookahead limits must fit the closed path')
        before = self.points - np.roll(self.points, 2, axis=0)
        after = np.roll(self.points, -2, axis=0) - self.points
        denominator = (np.linalg.norm(before, axis=1) * np.linalg.norm(after, axis=1)
                       * np.linalg.norm(before + after, axis=1))
        self.curvatures = np.abs(2.0 * (before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0])
                                 / np.maximum(denominator, 1e-8))
        self.speed_profile = self.build_speed_profile()

    def reset(self):
        super().reset()
        self.index = None
        self.profile_speed = 0.0
        self.clearance_speed = 0.0
        self.cross_track_error = 0.0
        self.limit_reason = 'waiting'

    def build_speed_profile(self):
        squared = np.minimum(self.max_speed ** 2,
                             self.lateral_acceleration / np.maximum(self.curvatures, 1e-6))
        for iteration in range(len(self.points)):
            previous = squared.copy()
            for index in range(len(squared) - 1, -1, -1):
                following = (index + 1) % len(squared)
                squared[index] = min(squared[index], squared[following]
                                     + 2.0 * self.braking_deceleration * self.segment_lengths[index])
            for index in range(len(squared)):
                following = (index + 1) % len(squared)
                squared[following] = min(squared[following], squared[index]
                                         + 2.0 * self.acceleration_limit * self.segment_lengths[index])
            if np.max(np.abs(squared - previous)) < 1e-9:
                break
        return np.sqrt(squared)

    def sample(self, distances):
        distances = np.asarray(distances) % self.lap_length
        indices = np.searchsorted(self.arc, distances, side='right') - 1
        fraction = (distances - self.arc[indices]) / self.segment_lengths[indices]
        points = self.points[indices] + np.asarray(fraction)[..., None] * self.segments[indices]
        return points, indices, fraction

    def obstacle_distance(self, ranges, angles, position, yaw, progress, speed):
        horizon = min(self.max_range, max(2.0, speed * self.braking_reaction_time
                                         + speed ** 2 / (2.0 * self.braking_deceleration) + 1.0))
        distances = np.linspace(0.0, horizon, int(horizon / 0.15) + 2)
        route, _, _ = self.sample(progress + distances)
        route[0] = position
        valid = np.isfinite(ranges) & (ranges > 0.06) & (ranges < self.max_range)
        if not np.any(valid):
            return math.inf
        local_forward = 0.2733 + ranges[valid] * np.cos(angles[valid])
        local_left = ranges[valid] * np.sin(angles[valid])
        obstacles = np.column_stack((
            position[0] + math.cos(yaw) * local_forward - math.sin(yaw) * local_left,
            position[1] + math.sin(yaw) * local_forward + math.cos(yaw) * local_left,
        ))
        vectors = np.diff(route, axis=0)
        squared_length = np.sum(vectors ** 2, axis=1)
        offsets = obstacles[:, None, :] - route[None, :-1, :]
        fractions = np.clip(np.sum(offsets * vectors[None, :, :], axis=2)
                            / np.maximum(squared_length[None, :], 1e-8), 0.0, 1.0)
        separation = offsets - fractions[:, :, None] * vectors[None, :, :]
        inside = np.sum(separation ** 2, axis=2) < (self.vehicle_half_width + self.clearance_margin) ** 2
        along = distances[:-1][None, :] + fractions * np.diff(distances)[None, :]
        inside &= along > 0.30
        return float(np.min(along[inside])) if np.any(inside) else math.inf

    def plan_path(self, ranges, angles, speed, elapsed, position, yaw):
        if (position is None or not math.isfinite(yaw) or not np.all(np.isfinite(position))
                or not math.isfinite(elapsed) or elapsed <= 0 or not math.isfinite(speed)):
            return self.stop(0.0)
        elapsed = min(elapsed, 0.1)
        ranges = np.asarray(ranges, dtype=float)
        angles = np.asarray(angles, dtype=float)
        if (ranges.ndim != 1 or ranges.shape != angles.shape or len(ranges) < 3
                or not np.all(np.isfinite(angles)) or np.any(np.diff(angles) <= 0)):
            return self.stop(speed)
        forward = np.abs(angles) < math.radians(10)
        if not np.any(forward) or np.any(np.isnan(ranges[forward])) or np.any(ranges[forward] <= 0.06):
            return self.stop(speed)
        if float(np.min(ranges[forward])) < self.stop_distance:
            return self.stop(speed)

        position = np.asarray(position, dtype=float)
        candidates = (np.arange(len(self.points)) if self.index is None
                      else (self.index + np.arange(-5, 21)) % len(self.points))
        offsets = position - self.points[candidates]
        fractions = np.clip(np.sum(offsets * self.segments[candidates], axis=1)
                            / self.segment_lengths[candidates] ** 2, 0.0, 1.0)
        projections = self.points[candidates] + fractions[:, None] * self.segments[candidates]
        errors = np.linalg.norm(projections - position, axis=1)
        nearest = int(np.argmin(errors))
        if errors[nearest] > 0.75:
            return self.stop(speed)
        self.cross_track_error = float(errors[nearest])
        self.index = int(candidates[nearest])
        progress = float(self.arc[self.index] + fractions[nearest] * self.segment_lengths[self.index])
        preview_distances = np.arange(0.0, max(1.0, speed * 0.5), 0.15)
        _, preview_indices, _ = self.sample(progress + preview_distances)
        upcoming_curvature = float(np.max(self.curvatures[preview_indices]))
        adaptive_lookahead = min(self.max_lookahead, self.lookahead + self.lookahead_time * max(0.0, speed - 1.0))
        lookahead = max(self.lookahead, adaptive_lookahead / (1.0 + 0.4 * upcoming_curvature))
        target_point, _, _ = self.sample(progress + lookahead)
        offset = target_point - position
        local_forward = math.cos(yaw) * offset[0] + math.sin(yaw) * offset[1]
        local_left = -math.sin(yaw) * offset[0] + math.cos(yaw) * offset[1]
        if local_forward < 0:
            return self.stop(speed)
        curvature = 2.0 * local_left / max(float(offset @ offset), 0.01)
        desired = float(np.clip(math.atan(0.324 * curvature) / 0.5236, -1.0, 1.0))
        self.steering += float(np.clip(desired - self.steering, -2.5 * elapsed, 2.5 * elapsed))

        reserve = self.braking_margin + max(0.0, speed) * self.braking_reaction_time
        offsets = np.linspace(0.0, reserve, max(2, int(reserve / 0.1) + 2))
        _, indices, fraction = self.sample(progress + offsets)
        following = (indices + 1) % len(self.points)
        sampled_squared = ((1.0 - fraction) * self.speed_profile[indices] ** 2
                           + fraction * self.speed_profile[following] ** 2)
        self.profile_speed = float(np.sqrt(np.min(sampled_squared)))
        steering_limit = math.sqrt(self.lateral_acceleration / max(abs(curvature), 1e-6))
        obstacle = self.obstacle_distance(ranges, angles, position, yaw, progress, speed)
        available = max(0.0, obstacle - 0.50 - self.braking_margin)
        reaction = self.braking_deceleration * self.braking_reaction_time
        self.clearance_speed = max(0.0, math.sqrt(reaction ** 2 + 2.0 * self.braking_deceleration * available) - reaction)
        limits = {'profile': self.profile_speed, 'steering': steering_limit, 'obstacle': self.clearance_speed}
        self.limit_reason = min(limits, key=limits.get)
        target = min(self.max_speed, *limits.values())
        return self.steering, self.speed_control(target, speed, elapsed)

    def speed_control(self, target, speed, elapsed):
        previous_target = self.target_speed
        self.target_speed = min(target, previous_target + self.acceleration_limit * elapsed)
        acceleration = float(np.clip((self.target_speed - previous_target) / elapsed,
                                     -self.braking_deceleration, self.acceleration_limit))
        error = self.target_speed - speed
        if error < -self.brake_deadband:
            self.integral = 0.0
            brake_limit = self.max_brake * (1.0 - 0.7 * abs(self.steering))
            brake = min(brake_limit, self.brake_kp * (-error - self.brake_deadband))
            return -brake if speed > 0.6 else 0.0
        proposed = float(np.clip(self.integral + error * elapsed, -0.5, 0.5))
        command = (self.speed_feedforward * self.target_speed + self.speed_kp * error
                   + self.speed_ki * proposed + self.acceleration_feedforward * acceleration)
        if 0.0 <= command <= self.max_throttle:
            self.integral = proposed
        return float(np.clip(command, 0.0, self.max_throttle))
