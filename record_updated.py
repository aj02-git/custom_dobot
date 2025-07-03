
import csv
import traceback
import os
from datetime import datetime
import cv2

class RecordData:
    def __init__(self, task, c_obj):
        self.task = task
        #self.r_obj = r_obj
        self.c_obj =c_obj
        self.csv_writer = None
        self.csv_file = None
        self.collection_rate = 15

    def setup_data_recording(self, base_path="dobot_data", csv_filename="robot_log", top_video_filename="top_camera",
                         wrist_video_filename="wrist_camera"):
        """MODIFICATION: Updated CSV header for new observation data."""
        os.makedirs(base_path, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        csv_path = os.path.join(base_path, f"{csv_filename}_{timestamp_str}.csv")
        self.csv_file = open(csv_path, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            'timestamp',
            'obs_x', 'obs_y', 'obs_z', 'obs_rx', 'obs_ry', 'obs_rz',  # Observed pose
            'obs_j1', 'obs_j2', 'obs_j3', 'obs_j4', 'obs_j5', 'obs_j6',  # Observed joint angles
            'obs_gripper',
            'action_x', 'action_y', 'action_z', 'action_rx', 'action_ry', 'action_rz',
            'action_gripper',
            # 'action_j1', 'action_j2', 'action_j3', 'action_j4', 'action_j5', 'action_j6',
            f"{self.task}"
        ])
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        resolution_top = self.c_obj.camera_config['top']['resolution']
        self.top_video_writer = cv2.VideoWriter(os.path.join(base_path, f"{top_video_filename}_{timestamp_str}.mp4"),
                                                fourcc, self.collection_rate, resolution_top)

        resolution_wrist = self.c_obj.camera_config['wrist']['resolution']
        self.wrist_video_writer = cv2.VideoWriter(
            os.path.join(base_path, f"{wrist_video_filename}_{timestamp_str}.mp4"), fourcc, self.collection_rate,
            resolution_wrist)

        print(f"Initialized data recording with timestamp {timestamp_str}")


    def close_data_recording(self):
        """Close all data recording files."""
        print("Closing data recording files...")
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
            print("CSV file closed.")
        print("All data recording files closed.")


    def collect_data_point(self, timestamp, top_frame, wrist_frame, obs_pose, obs_angles,obs_gripper, actions_p, action_gripper, action_a=None):
        """MODIFICATION: This function now receives feedback data instead of fetching it."""
        try:
            # top_frame, wrist_frame = self.c_obj.capture_frames()
            if top_frame is None or wrist_frame is None:
                print("Warning: Failed to capture camera frames for data point.")
                return False

            #obs_pose, obs_angles = self.r_obj.get_data()

            if self.csv_writer:
                row_data = [
                    f"{timestamp:.4f}",
                    *obs_pose,  # OBSERVED pose from feedback
                    *obs_angles,  # OBSERVED angles from feedback
                    obs_gripper,
                    *actions_p,
                    action_gripper
                ]
                self.csv_writer.writerow(row_data)

            if self.top_video_writer: self.top_video_writer.write(top_frame)
            if self.wrist_video_writer: self.wrist_video_writer.write(wrist_frame)

            return True
        except Exception as e:
            print(f"Error in _collect_data_point: {e}")
            traceback.print_exc()
            return False
