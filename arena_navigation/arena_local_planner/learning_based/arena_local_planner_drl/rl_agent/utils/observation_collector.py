#! /usr/bin/env python
from typing import Tuple

from numpy.core.numeric import normalize_axis_tuple
import rospy
import random
import numpy as np
from collections import deque

import time  # for debuging
import threading

# observation msgs
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Pose2D, PoseStamped, Twist
from nav_msgs.msg import Path
from rosgraph_msgs.msg import Clock
from nav_msgs.msg import Odometry

# message filter
import message_filters

# for transformations
from tf.transformations import *

from gym import spaces
import numpy as np


class ObservationCollector:
    def __init__(
        self,
        ns: str,
        num_lidar_beams: int,
        lidar_range: float,
    ):
        """a class to collect and merge observations

        Args:
            num_lidar_beams (int): [description]
            lidar_range (float): [description]
        """
        """SET A METHOD TO EXTRACT IF MARL IS BEIN REQUESTED"""
        MARL = rospy.get_param("num_robots") > 1

        self.ns = ns
        if ns is None or ns == "":
            self.ns_prefix = ""
        else:
            self.ns_prefix = (
                "/" + ns + "/" if not ns.endswith("/") else "/" + ns
            )

        # define observation_space
        self.observation_space = ObservationCollector._stack_spaces(
            (
                spaces.Box(
                    low=0,
                    high=lidar_range,
                    shape=(num_lidar_beams,),
                    dtype=np.float32,
                ),
                spaces.Box(low=0, high=10, shape=(1,), dtype=np.float32),
                spaces.Box(
                    low=-np.pi, high=np.pi, shape=(1,), dtype=np.float32
                ),
            )
        )

        self._laser_num_beams = num_lidar_beams

        self._clock = Clock()
        self._scan = LaserScan()
        self._robot_pose = Pose2D()
        self._robot_vel = Twist()
        self._subgoal = Pose2D()
        self._globalplan = np.array([])

        # subscriptions
        self._scan_sub = rospy.Subscriber(
            f"{self.ns_prefix}scan",
            LaserScan,
            self.callback_scan,
            tcp_nodelay=True,
        )
        self._robot_state_sub = rospy.Subscriber(
            f"{self.ns_prefix}odom",
            Odometry,
            self.callback_robot_state,
            tcp_nodelay=True,
        )

        # self._clock_sub = rospy.Subscriber(
        #     f'{self.ns_prefix}clock', Clock, self.callback_clock, tcp_nodelay=True)

        # when using MARL listen to goal directly since no intermediate planner is considered
        goal_topic = (
            f"{self.ns_prefix}goal" if MARL else f"{self.ns_prefix}subgoal"
        )
        self._subgoal_sub = rospy.Subscriber(
            f"{goal_topic}", PoseStamped, self.callback_subgoal
        )
        self._globalplan_sub = rospy.Subscriber(
            f"{self.ns_prefix}globalPlan", Path, self.callback_global_plan
        )

        # synchronization parameters
        self._first_sync_obs = (
            True  # whether to return first sync'd obs or most recent
        )
        self.max_deque_size = 10
        self._sync_slop = 0.1

        self._laser_deque = deque()
        self._rs_deque = deque()

    def get_observation_space(self):
        return self.observation_space

    def get_observations(self):
        # try to retrieve sync'ed obs
        laser_scan, robot_pose = self.get_sync_obs()
        if laser_scan is not None and robot_pose is not None:
            # print("Synced successfully")
            self._scan = laser_scan
            self._robot_pose = robot_pose
        # else:
        #     print("Not synced")
        if len(self._scan.ranges) > 0:
            scan = self._scan.ranges.astype(np.float32)
        else:
            scan = np.zeros(self._laser_num_beams, dtype=float)

        rho, theta = ObservationCollector._get_goal_pose_in_robot_frame(
            self._subgoal, self._robot_pose
        )
        merged_obs = np.hstack([scan, np.array([rho, theta])])

        obs_dict = {
            "laser_scan": scan,
            "goal_in_robot_frame": [rho, theta],
            "global_plan": self._globalplan,
            "robot_pose": self._robot_pose,
        }

        self._laser_deque.clear()
        self._rs_deque.clear()
        return merged_obs, obs_dict

    @staticmethod
    def _get_goal_pose_in_robot_frame(
        goal_pos: Pose2D, robot_pos: Pose2D
    ) -> Tuple[float, float]:
        y_relative = goal_pos.y - robot_pos.y
        x_relative = goal_pos.x - robot_pos.x
        rho = (x_relative ** 2 + y_relative ** 2) ** 0.5
        theta = (
            np.arctan2(y_relative, x_relative) - robot_pos.theta + 4 * np.pi
        ) % (2 * np.pi) - np.pi
        return rho, theta

    def get_sync_obs(self):
        laser_scan = None
        robot_pose = None

        # print(f"laser deque: {len(self._laser_deque)}, robot state deque: {len(self._rs_deque)}")
        while len(self._rs_deque) > 0 and len(self._laser_deque) > 0:
            laser_scan_msg = self._laser_deque.popleft()
            robot_pose_msg = self._rs_deque.popleft()

            laser_stamp = laser_scan_msg.header.stamp.to_sec()
            robot_stamp = robot_pose_msg.header.stamp.to_sec()

            while abs(laser_stamp - robot_stamp) > self._sync_slop:
                if laser_stamp > robot_stamp:
                    if len(self._rs_deque) == 0:
                        return laser_scan, robot_pose
                    robot_pose_msg = self._rs_deque.popleft()
                    robot_stamp = robot_pose_msg.header.stamp.to_sec()
                else:
                    if len(self._laser_deque) == 0:
                        return laser_scan, robot_pose
                    laser_scan_msg = self._laser_deque.popleft()
                    laser_stamp = laser_scan_msg.header.stamp.to_sec()

            laser_scan = self.process_scan_msg(laser_scan_msg)
            robot_pose, _ = self.process_robot_state_msg(robot_pose_msg)

            if self._first_sync_obs:
                break

        # print(f"Laser_stamp: {laser_stamp}, Robot_stamp: {robot_stamp}")
        return laser_scan, robot_pose

    def callback_clock(self, msg_Clock):
        self._clock = msg_Clock.clock.to_sec()
        return

    def callback_subgoal(self, msg_Subgoal):
        self._subgoal = self.process_subgoal_msg(msg_Subgoal)
        return

    def callback_global_plan(self, msg_global_plan):
        self._globalplan = ObservationCollector.process_global_plan_msg(
            msg_global_plan
        )
        return

    def callback_scan(self, msg_laserscan):
        if len(self._laser_deque) == self.max_deque_size:
            self._laser_deque.popleft()
        self._laser_deque.append(msg_laserscan)

    def callback_robot_state(self, msg_robotstate):
        if len(self._rs_deque) == self.max_deque_size:
            self._rs_deque.popleft()
        self._rs_deque.append(msg_robotstate)

    def callback_observation_received(
        self, msg_LaserScan, msg_RobotStateStamped
    ):
        # process sensor msg
        self._scan = self.process_scan_msg(msg_LaserScan)
        self._robot_pose, self._robot_vel = self.process_robot_state_msg(
            msg_RobotStateStamped
        )
        self.obs_received = True
        return

    def process_scan_msg(self, msg_LaserScan: LaserScan):
        # remove_nans_from_scan
        self._scan_stamp = msg_LaserScan.header.stamp.to_sec()
        scan = np.array(msg_LaserScan.ranges)
        scan[np.isnan(scan)] = msg_LaserScan.range_max
        msg_LaserScan.ranges = scan
        return msg_LaserScan

    def process_robot_state_msg(self, msg_Odometry):
        pose3d = msg_Odometry.pose.pose
        twist = msg_Odometry.twist.twist
        return self.pose3D_to_pose2D(pose3d), twist

    def process_pose_msg(self, msg_PoseWithCovarianceStamped):
        # remove Covariance
        pose_with_cov = msg_PoseWithCovarianceStamped.pose
        pose = pose_with_cov.pose
        return self.pose3D_to_pose2D(pose)

    def process_subgoal_msg(self, msg_Subgoal):
        return self.pose3D_to_pose2D(msg_Subgoal.pose)

    @staticmethod
    def process_global_plan_msg(globalplan):
        global_plan_2d = list(
            map(
                lambda p: ObservationCollector.pose3D_to_pose2D(p.pose),
                globalplan.poses,
            )
        )
        return np.array(list(map(lambda p2d: [p2d.x, p2d.y], global_plan_2d)))

    @staticmethod
    def pose3D_to_pose2D(pose3d):
        pose2d = Pose2D()
        pose2d.x = pose3d.position.x
        pose2d.y = pose3d.position.y
        quaternion = (
            pose3d.orientation.x,
            pose3d.orientation.y,
            pose3d.orientation.z,
            pose3d.orientation.w,
        )
        euler = euler_from_quaternion(quaternion)
        yaw = euler[2]
        pose2d.theta = yaw
        return pose2d

    @staticmethod
    def _stack_spaces(ss: Tuple[spaces.Box]):
        low = []
        high = []
        for space in ss:
            low.extend(space.low.tolist())
            high.extend(space.high.tolist())
        return spaces.Box(np.array(low).flatten(), np.array(high).flatten())


if __name__ == "__main__":

    rospy.init_node("states", anonymous=True)
    print("start")

    state_collector = ObservationCollector("sim1/", 360, 10)
    i = 0
    r = rospy.Rate(100)
    while i <= 1000:
        i = i + 1
        obs = state_collector.get_observations()

        time.sleep(0.001)
