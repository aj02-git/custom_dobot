# --- START OF FILE test_data_collection_3.py ---

import pygame
import time
import socket
import threading
from queue import Queue
import traceback  # Useful for debugging

# Assuming these are your custom utility classes
from dobot import Robot
from camera_utils import Camera
from record import RecordData


# --- Recorder Worker Function (runs in a separate thread) ---
def recorder_worker(queue, record_obj):
    """
    This function runs in the background, consuming data from the queue
    and performing the slow I/O operations (writing video and CSV).
    """
    print("Recorder thread started.")
    while True:
        try:
            data_packet = queue.get()

            if data_packet is None:
                print("Sentinel received. Recorder thread shutting down.")
                break

            timestamp, top_frame, wrist_frame, obs_pose, obs_angles, obs_gripper, actions_p, action_gripper = data_packet

            record_obj.collect_data_point(timestamp, top_frame, wrist_frame, obs_pose, obs_angles, obs_gripper,
                                          actions_p, action_gripper)
        except Exception as e:
            print(f"Error in recorder thread: {e}")
            break

    print("Closing recording files...")
    record_obj.close_data_recording()
    print("Recording files closed.")


# --- Main Application ---
# --- Configuration ---
TARGET_HZ = 15  # Let's aim for a slightly higher, more responsive rate
target_period = 1 / TARGET_HZ
episode_num = "0140"
task = "Take out all the items from the basket and place it on the table"
base_path = "dobot_data/02_July_pick_place_colored_boxes/obs_data"
csv_filename = f"episode_{episode_num}_robot_log_basket"
top_video_filename = f"episode_{episode_num}_top_video_basket"
wrist_video_filename = f"episode_{episode_num}_wrist_video_basket"

# --- Pygame Joystick Configuration ---
DEAD_ZONE = 0.55
# --- NEW: Velocity-based control parameters ---
MAX_LINEAR_VELOCITY =85.0  # Max speed in mm/s
MAX_ANGULAR_VELOCITY = 35.0  # Max speed in degrees/s

# --- Initialize Objects ---
r_obj = Robot()
c_obj = Camera()
record_obj = RecordData(task, c_obj)

# --- Setup Connections and Recordings ---
r_obj.connect()  # This now also starts the robot's feedback thread
c_obj.start_capture()  # Manually start the camera capture thread

# Wait a moment for the first feedback to arrive
time.sleep(0.5)
initial_pose, _ = r_obj.get_data()
if not any(initial_pose):  # Check if the pose is all zeros
    print("Warning: Initial robot pose is all zeros. Waiting a bit longer...")
    time.sleep(1.0)
    initial_pose, _ = r_obj.get_data()
    if not any(initial_pose):
        raise RuntimeError("Failed to get initial robot pose. Check connection.")
print("Initial pose is: ", initial_pose)

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() > 0:
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"Joystick '{joystick.get_name()}' initialized.")
else:
    joystick = None
    print("Connect joystick first")
    # Consider exiting if joystick is essential
    # exit()

# --- Setup Threading for Recording ---
data_queue = Queue()
record_obj.setup_data_recording(
    base_path=base_path,
    csv_filename=csv_filename,
    top_video_filename=top_video_filename,
    wrist_video_filename=wrist_video_filename
)
recorder_thread = threading.Thread(target=recorder_worker, args=(data_queue, record_obj))
recorder_thread.start()

# --- Main Control Loop ---
running = True
total_timestamp = 0
last_loop_time = time.perf_counter()

# --- VELOCITY CONTROL: Initialize the target pose with the robot's starting position ---
# This is the "ideal" position we will command the robot to go to.
command_pose = list(initial_pose)

try:
    while running:
        loop_start_time = time.perf_counter()
        delta_time = loop_start_time - last_loop_time
        last_loop_time = loop_start_time

        # --- Fast, NON-BLOCKING data acquisition (for observation/logging) ---
        obs_pose, obs_angles = r_obj.get_data()
        obs_gripper = r_obj.suction_on
        top_frame, wrist_frame = c_obj.capture_frames()

        # --- Event Polling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.JOYBUTTONDOWN:
                if event.button == 8:  # Gripper toggle
                    print("Gripper toggled.")
                    r_obj.toggle_gripper()
                if event.button == 11:  # Stop button
                    running = False

        # --- Joystick Polling and Velocity Calculation ---
        if joystick:
            # Get raw joystick values
            axis_ly = joystick.get_axis(1) * 1  # Forward/Back
            axis_lx = joystick.get_axis(0) * 1  # Left/Right
            axis_ry = -joystick.get_axis(3)  # Up/Down

            # Apply dead zone
            vx = 0.0 if abs(axis_lx) < DEAD_ZONE else axis_lx
            vy = 0.0 if abs(axis_ly) < DEAD_ZONE else axis_ly
            vz = 0.0 if abs(axis_ry) < DEAD_ZONE else axis_ry

            # --- NEW: VELOCITY-BASED CONTROL ---
            # Update the ideal command_pose based on joystick velocity and delta_time
            command_pose[0] += vy * MAX_LINEAR_VELOCITY * delta_time  # Y-stick moves X-coord
            command_pose[1] += vx * MAX_LINEAR_VELOCITY * delta_time  # X-stick moves Y-coord
            command_pose[2] += vz * MAX_LINEAR_VELOCITY * delta_time  # R-stick moves Z-coord

            # Rotational velocity from buttons
            if joystick.get_button(3): command_pose[3] -= MAX_ANGULAR_VELOCITY * delta_time
            if joystick.get_button(1): command_pose[3] += MAX_ANGULAR_VELOCITY * delta_time
            if joystick.get_button(4): command_pose[4] += MAX_ANGULAR_VELOCITY * delta_time
            if joystick.get_button(0): command_pose[4] -= MAX_ANGULAR_VELOCITY * delta_time
            if joystick.get_button(7): command_pose[5] += MAX_ANGULAR_VELOCITY * delta_time
            if joystick.get_button(6): command_pose[5] -= MAX_ANGULAR_VELOCITY * delta_time

            # Apply safety limits to the final commanded pose
            command_pose[0] = max(min(command_pose[0], 750), 240)
            command_pose[1] = max(min(command_pose[1], 550), -330)
            command_pose[2] = max(min(command_pose[2], 300), -20)
            command_pose[3] = max(min(command_pose[3], 180), -180)
            command_pose[4] = max(min(command_pose[4], 180), -180)
            command_pose[5] = max(min(command_pose[5], 180), -180)

        # If no joystick, the command_pose simply stays where it is.
        action_gripper = r_obj.suction_on
        # action_a = r_obj.get_action_angles(command_pose)

        # --- Send the calculated ideal pose to the robot (NON-BLOCKING) ---
        r_obj.send_actions(*command_pose)

        # --- Put all data into the queue for the recorder thread ---
        # We log the observation (obs_*) and the command we sent (command_pose)
        data_packet = (
        total_timestamp, top_frame, wrist_frame, obs_pose, obs_angles, obs_gripper, command_pose, action_gripper)
        data_queue.put(data_packet)

        # --- FPS Control ---
        work_duration = time.perf_counter() - loop_start_time
        sleep_duration = target_period - work_duration
        # print("sleep duration", sleep_duration)
        if sleep_duration > 0:
            time.sleep(sleep_duration)
        # Update timestamp for the next loop
        total_timestamp += (time.perf_counter() - loop_start_time)

except (Exception, KeyboardInterrupt) as e:
    print(f"An exception occurred in the main loop: {e}")
    traceback.print_exc()

finally:
    # --- Graceful Shutdown Sequence ---
    print("\nMain loop finished. Starting graceful shutdown.")
    pygame.quit()

    # 1. Stop the camera thread and close pipelines
    if 'c_obj' in locals():
        c_obj.close()

    # 2. Signal the recorder thread to stop by sending the 'None' sentinel
    if 'data_queue' in locals():
        data_queue.put(None)

    # 3. Wait for the recorder thread to finish processing all items
    if 'recorder_thread' in locals() and recorder_thread.is_alive():
        print("Waiting for recorder thread to finish...")
        recorder_thread.join()  # This prevents data loss
        print("Recorder thread finished.")

    # 4. Now that all data is saved, disconnect the robot
    if 'r_obj' in locals():
        r_obj.disconnect()

    print("Program finished.")