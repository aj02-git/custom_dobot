from dobot_api.dobot_api import DobotApiDashboard, DobotApiMove, DobotApiFeedBack
import traceback
import time
from enum import IntEnum
import re


class RobotMode(IntEnum):
    ENABLED = 5      # Ready and idle
    RUNNING = 7      # Executing commands
    ERROR = 4        # Added for completeness, check actual Dobot API for more modes


class Robot:
    def __init__(self, robot_ip="192.168.5.11"):
        self.ip = robot_ip
        self.dashboard = None
        self.move = None
        self.feedback= None
        self.speed = 100
        self.acj = 20
        self.suction_on = 0
        self.dashboard_port = 29999
        self.move_port = 30003
        self.feedback_port = 30004
        self.target_Tool = 1

    #TODO : change the mentod name to dashboard_connect and for move alsoo

    def _connect_dashboard(self):
        self.dashboard = DobotApiDashboard(self.ip, self.dashboard_port)
    def _connect_move(self):
        self.move = DobotApiMove(self.ip, self.move_port)
    def _connect_feedback(self):
        self.feedback = DobotApiFeedBack(self.ip, self.feedback_port)

    def _connect_ip(self):
        """Connect to robot dashboard, move, and feedback interfaces"""
        print(f"Connecting to Dobot Magician Pro at {self.ip}...")
        try:
            # Dashboard for control and status commands (e.g., Enable, Mode)
            self._connect_dashboard()
            self._connect_move() # Move commands also go to 30003
            self._connect_feedback()
            # Feedback for the high-frequency data stream
            #self.feedback = DobotApiFeedBack(self.ip, 30004)
        except Exception as e:
            print(f"Failed to connect to Dobot: {e}")
            traceback.print_exc()
            raise


    def initialize(self):
        try:
            self.dashboard.ClearError()
            self.dashboard.Continue()
            self.dashboard.EnableRobot()
            time.sleep(2)
            print("Robot Enable command sent.")
            ## remove print statements and use logging


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
                    self.dashboard.Continue()
                    time.sleep(0.5)
                    self.dashboard.EnableRobot()
                    print("Re-sent EnableRobot command after clearing error.")
                else:
                    print(f"Waiting for robot to enable. Current mode: {mode}")
                time.sleep(0.5)
            else:
                raise TimeoutError("Robot did not become enabled within timeout.")


            self.dashboard.SpeedFactor(self.speed)
            self.dashboard.AccJ(self.acj)
            time.sleep(1)
            self.dashboard.Tool(self.target_Tool)
            # Give the controller a moment to process the command and update its internal state
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


    def get_data(self):
        """This method gets pose of the robot and joint angles and return as a dict"""
        position = angles =None
        pose_data = self.dashboard.GetPose()
        match = re.search(r'\{([-\d\.\s,]+)\}', pose_data)
        if match:
            position = [float(v.strip()) for v in match.group(1).split(',')]

        else:
            print("Error: Could not parse pose from GetPose() response.")

        angle_data = self.dashboard.GetAngle()
        match = re.search(r'\{([-\d\.\s,]+)\}', angle_data)
        if match:
            angles = [float(v.strip()) for v in match.group(1).split(',')]
        else:
            print("Error: Could not parse angle from GetAngle() response.")
        return position, angles # need to add logic to check the size of the position and angles.


    def get_action_angles(self, pose):
        """This method gets inverse solution to getpose to get action angles"""
        angles = None
        angle_data = self.dashboard.InverseSolution(*pose,0,self.target_Tool) # The tool index here MUST match the active tool.
        match = re.search(r'\{([-\d\.\s,]+)\}', angle_data)
        if match:
            angles = [float(v.strip()) for v in match.group(1).split(',')]
        else:
            print("Error: Could not parse angle from Inv_sol response.")
        return angles


    def connect(self):
        self._connect_ip()
        self.initialize()


    def disconnect(self):
        if self.dashboard:
            try:
                self.dashboard.ClearError()
                self.dashboard.Continue()
                self.dashboard.DisableRobot()
                self.move.close()  # Ensure the move socket is closed at the end
                self.dashboard.close()
                print("Robot disconnected.")
            except Exception as e:
                print(f"Error disabling robot: {e}")

    def send_actions(self, x, y, z, rx, ry, rz):
        #need to write a check logic where the actions are in the range. or else it raises a error.
        # actions = str(actions)[1:-1]
        command= f"ServoP({x}, {y}, {z}, {rx}, {ry}, {rz})"
        self.move.send_data(command)
        #self.move.ServoP(x, y, z, rx, ry, rz)## later change it to send_data

    def send_angles(self, action_a):
        #need to write a check logic where the actions are in the range. or else it raises a error.
        j1, j2, j3, j4, j5, j6 = action_a
        gain = 500 # Proportional gain (200-1000). Higher = stiffer, more aggressive.
        lookahead_time = 50 # Derivative/Damping term (20-100). Higher = smoother.  t={0.070}
        command = f"ServoJ({j1:.4f},{j2:.4f},{j3:.4f},{j4:.4f},{j5:.4f},{j6:.4f},t= {0.1}, gain={gain},lookahead_time={lookahead_time})"
        self.move.send_data(command)
        #self.move.ServoJ(j1,j2, j3, j4, j5, j6, t= 0.11, gain=500,lookahead_time=60)## later change it to send_data

    def toggle_gripper(self):
        if not self.suction_on:
            self.suction_on=1
            self.dashboard.ToolDOExecute(2, 0)
            self.dashboard.ToolDOExecute(1, 1)
        elif self.suction_on:
            self.suction_on = 0
            self.dashboard.ToolDOExecute(1, 0)
            self.dashboard.ToolDOExecute(2, 1)







