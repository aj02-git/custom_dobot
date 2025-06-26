import pygame
import time
import socket
import threading
from queue import Queue

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
            # This is a blocking call. The thread will wait here until
            # an item is available in the queue.
            data_packet = queue.get()

            # A 'None' value is our signal to stop the thread.
            if data_packet is None:
                print("Sentinel received. Recorder thread shutting down.")
                break

            # Unpack the data from the tuple
            timestamp, top_frame, wrist_frame, obs_pose, obs_angles, obs_gripper, actions_p, action_gripper = data_packet

            # Perform the slow data collection call
            record_obj.collect_data_point(timestamp, top_frame, wrist_frame, obs_pose, obs_angles, obs_gripper,
                                          actions_p, action_gripper)

        except Exception as e:
            print(f"Error in recorder thread: {e}")
            break

    # After the loop breaks, close the recording files
    print("Closing recording files...")
    record_obj.close_data_recording()
    print("Recording files closed.")


# --- Main Application ---
# --- Configuration ---
target_period = 1 / 15
episode_num = "0020"
task = "Pick up the Lid and close the steel bowl with it"
base_path = "dobot_data/21_June_pick_place_colored_boxes/obs_data"
csv_filename = f"episode_{episode_num}_robot_log"
top_video_filename = f"episode_{episode_num}_top_video"
wrist_video_filename = f"episode_{episode_num}_wrist_video"

# --- Pygame Joystick Configuration ---
UNITS_TO_JUMP = 6
DEAD_ZONE = 0.1

# --- Initialize Objects ---
r_obj = Robot()
c_obj = Camera()
record_obj = RecordData(task, c_obj)

# --- Setup Connections and Recordings ---
r_obj.connect()
print("Pose values are: ", r_obj.get_data()[0])

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() > 0:
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"Joystick '{joystick.get_name()}' initialized.")
else:
    joystick = None
    print("Connect joystick first")
    # You might want to exit here if the joystick is required
    # exit()

# --- Setup Threading for Recording ---
data_queue = Queue()  # Create the queue to communicate between threads
record_obj.setup_data_recording(
    base_path=base_path,
    csv_filename=csv_filename,
    top_video_filename=top_video_filename,
    wrist_video_filename=wrist_video_filename
)
# Create and start the recorder thread. It will immediately wait on queue.get().
recorder_thread = threading.Thread(target=recorder_worker, args=(data_queue, record_obj))
recorder_thread.start()

# --- Main Control Loop ---
running = True
timestamp = 0
loop_start_time = time.perf_counter()  # Initialize for first timestamp calculation

while running:
    # --- Fast Operations: Data Acquisition ---
    obs_pose, obs_angles = r_obj.get_data()
    obs_gripper = r_obj.suction_on
    top_frame, wrist_frame = c_obj.capture_frames()

    # --- Fast Operations: Event Polling ---
    for event in pygame.event.get():
        if event.type == pygame.JOYBUTTONDOWN:
            if event.button == 8:  # Gripper toggle
                print("Gripper toggled.")
                r_obj.toggle_gripper()
            if event.button == 11:  # Stop button
                running = False

    x, y, z, rx, ry, rz = obs_pose
    # --- Fast Operations: Joystick Polling and Action Calculation ---
    if joystick:
        left_axis_y = joystick.get_axis(0)
        left_axis_x = joystick.get_axis(1)
        right_axis_z = joystick.get_axis(3)

        if abs(left_axis_x) < DEAD_ZONE: left_axis_x = 0.0
        if abs(left_axis_y) < DEAD_ZONE: left_axis_y = 0.0
        if abs(right_axis_z) < DEAD_ZONE: right_axis_z = 0.0

        x += (-left_axis_x) * UNITS_TO_JUMP
        y += (-left_axis_y) * UNITS_TO_JUMP
        z += (-right_axis_z) * UNITS_TO_JUMP

        x = max(min(x, 750), 240)
        y = max(min(y, 550), -330)
        z = max(min(z, 300), -20)

        if joystick.get_button(3): rx -= 5
        if joystick.get_button(1): rx += 5
        if joystick.get_button(4): ry += 5
        if joystick.get_button(0): ry -= 5
        if joystick.get_button(7): rz += 5
        if joystick.get_button(6): rz -= 5

        rx = max(min(rx, 180), -180)
        ry = max(min(ry, 180), -180)
        rz = max(min(rz, 180), -180)

    action_gripper = r_obj.suction_on
    actions_p = [x, y, z, rx, ry, rz]

    # --- Fast Operations: Send Actions to Robot ---
    try:
        r_obj.send_actions(x, y, z, rx, ry, rz)
    except (UnicodeDecodeError, socket.error) as e:
        print(f"Connection error ({type(e).__name__}): {e}. Attempting to reconnect...")
        r_obj.move.close()
        r_obj.move = r_obj._connect_move()
        try:
            r_obj.send_actions(x, y, z, rx, ry, rz)
            print("Reconnected and sent actions successfully.")
        except Exception as e_reconnect:
            print(f"Error after reconnection: {e_reconnect}")
            running = False  # Stop if reconnection fails
    except Exception as e_other:
        print(f"An unexpected error occurred: {e_other}")
        running = False

    # --- Fast Operation: Put all data into the queue for the recorder thread ---
    data_packet = (timestamp, top_frame, wrist_frame, obs_pose, obs_angles, obs_gripper, actions_p, action_gripper)
    data_queue.put(data_packet)

    # --- FPS Control ---
    current_time = time.perf_counter()
    work_duration = current_time - loop_start_time
    sleep_duration = target_period - work_duration
    if sleep_duration > 0:
        time.sleep(sleep_duration)

    timestamp += (time.perf_counter() - loop_start_time)
    loop_start_time = time.perf_counter()

# --- Shutdown Sequence ---
print("Main loop finished. Starting shutdown sequence.")
pygame.quit()

# 1. Signal the recorder thread to stop by sending the 'None' sentinel
data_queue.put(None)

# 2. Wait for the recorder thread to finish processing all items in the queue
#    and close its files. This prevents data loss.
print("Waiting for recorder thread to finish...")
recorder_thread.join()
print("Recorder thread finished.")

# 3. Now that all data is saved, disconnect the robot
r_obj.disconnect()
print("Robot disconnected. Program finished.")