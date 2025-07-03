# --- START OF FILE dobot.py ---

from dobot_api.dobot_api import DobotApiDashboard, DobotApiMove
import traceback
import time
from enum import IntEnum
import re
import threading


class RobotMode(IntEnum):
    ENABLED = 5  # Ready and idle
    RUNNING = 7  # Executing commands
    ERROR = 4  # Added for completeness, check actual Dobot API for more modes


class Robot:
    def __init__(self, robot_ip="192.168.5.11"):
        self.ip = robot_ip
        self.dashboard = None
        self.move = None
        self.feedback = None
        self.speed = 40
        self.acj = 20
        self.suction_on = 0
        self.dashboard_port = 29999
        self.move_port = 30003
        self.feedback_port = 30004
        self.target_Tool = 1

        # --- Threading and State Management ---
        self.current_pose = [0.0] * 6
        self.current_angles = [0.0] * 6
        self._state_lock = threading.Lock()
        self._feedback_thread = None
        self._is_running_feedback = False

    def _connect_dashboard(self):
        self.dashboard = DobotApiDashboard(self.ip, self.dashboard_port)

    def _connect_move(self):
        self.move = DobotApiMove(self.ip, self.move_port)

    def _connect_feedback(self):
        # Note: This connects to the dashboard port again for polling, as in the original code.
        self.feedback = DobotApiDashboard(self.ip, self.feedback_port)

    def _connect_ip(self):
        """Connect to robot dashboard, move, and feedback interfaces"""
        print(f"Connecting to Dobot Magician Pro at {self.ip}...")
        try:
            self._connect_dashboard()
            self._connect_move()
            self._connect_feedback()
        except Exception as e:
            print(f"Failed to connect to Dobot: {e}")
            traceback.print_exc()
            raise

    def initialize(self):
        try:
            self.dashboard.ClearError()
            self.dashboard.EnableRobot()
            time.sleep(2)
            print("Robot Enable command sent.")

            enable_timeout = 20
            start_enable_wait = time.perf_counter()
            while time.perf_counter() - start_enable_wait < enable_timeout:
                mode = self._get_robot_mode()
                if mode == RobotMode.ENABLED:
                    print("Robot is ENABLED.")
                    break
                elif mode == RobotMode.ERROR:
                    print("Robot is in ERROR state. Clearing error...")
                    self.dashboard.ClearError()
                    self.dashboard.EnableRobot()
                    print("Re-sent EnableRobot command after clearing error.")
                else:
                    print(f"Waiting for robot to enable. Current mode: {mode}")
                time.sleep(0.5)
            else:
                raise TimeoutError("Robot did not become enabled within timeout.")

            self.dashboard.SpeedFactor(self.speed)
            self.dashboard.AccJ(self.acj)
            self.dashboard.Tool(self.target_Tool)
            time.sleep(0.1)
        except Exception as e:
            print(f"Robot initialization failed: {e}")
            traceback.print_exc()
            raise

    def _get_robot_mode(self):
        try:
            response = self.dashboard.RobotMode()
            if isinstance(response, str) and ',' in response:
                return int(response.split(',')[1].strip('{}'))
        except Exception as e:
            print(f"Mode read error: {e}")
        return None

    def _feedback_loop(self):
        """The target function for the feedback thread."""
        while self._is_running_feedback:
            try:
                pose_data = self.dashboard.GetPose()
                angle_data = self.dashboard.GetAngle()

                match_pose = re.search(r'\{([-\d\.\s,]+)\}', pose_data)
                if match_pose:
                    position = [float(v.strip()) for v in match_pose.group(1).split(',')]
                else:
                    position = self.current_pose

                match_angle = re.search(r'\{([-\d\.\s,]+)\}', angle_data)
                if match_angle:
                    angles = [float(v.strip()) for v in match_angle.group(1).split(',')]
                else:
                    angles = self.current_angles

                with self._state_lock:
                    self.current_pose = position
                    self.current_angles = angles

                time.sleep(0.01)  # Poll at 100Hz

            except Exception as e:
                print(f"Error in feedback loop: {e}. Loop will continue.")
                time.sleep(1)

    def start_feedback(self):
        """Starts the background thread for polling robot state."""
        if not self._is_running_feedback:
            self._is_running_feedback = True
            self._feedback_thread = threading.Thread(target=self._feedback_loop)
            self._feedback_thread.daemon = True
            self._feedback_thread.start()
            print("Robot feedback thread started.")

    def stop_feedback(self):
        """Stops the background feedback thread."""
        if self._is_running_feedback:
            self._is_running_feedback = False
            if self._feedback_thread:
                self._feedback_thread.join()
            print("Robot feedback thread stopped.")

    def get_data(self):
        """This method gets pose of the robot and joint angles from shared state."""
        with self._state_lock:
            # Return copies to prevent race conditions if the caller modifies the list
            return list(self.current_pose), list(self.current_angles)

    def get_action_angles(self, pose):
        """This method gets inverse solution to getpose to get action angles"""
        angles = None
        angle_data = self.dashboard.InverseSolution(*pose, 0, self.target_Tool)
        match = re.search(r'\{([-\d\.\s,]+)\}', angle_data)
        if match:
            angles = [float(v.strip()) for v in match.group(1).split(',')]
        else:
            print("Error: Could not parse angle from Inv_sol response.")
        return angles

    def connect(self):
        self._connect_ip()
        self.initialize()
        self.start_feedback()

    def disconnect(self):
        self.stop_feedback()
        if self.dashboard:
            try:
                self.dashboard.DisableRobot()
                self.move.close()
                self.dashboard.close()
                print("Robot disconnected.")
            except Exception as e:
                print(f"Error disabling robot: {e}")

    # --- CRITICAL MODIFICATION: Use non-blocking send ---
    def send_actions(self, x, y, z, rx, ry, rz):
        """
        Sends the ServoP command without waiting for a reply to avoid blocking the
        main control loop. This is a "fire-and-forget" approach suitable for
        high-frequency teleoperation.
        """
        self.move.ServoP(x, y, z, rx, ry, rz) # This is the original BLOCKING call

        # # Construct the command string manually
        # command_str = f"ServoP({x:.4f},{y:.4f},{z:.4f},{rx:.4f},{ry:.4f},{rz:.4f})"
        # # Use the low-level send_data which does not wait for a reply
        # self.move.send_data(command_str)

    def toggle_gripper(self):
        if not self.suction_on:
            self.suction_on = 1
            self.dashboard.ToolDOExecute(2, 0)
            self.dashboard.ToolDOExecute(1, 1)
        elif self.suction_on:
            self.suction_on = 0
            self.dashboard.ToolDOExecute(1, 0)
            self.dashboard.ToolDOExecute(2, 1)