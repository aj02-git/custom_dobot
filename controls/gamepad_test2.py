import pygame
import time
from dobot import Robot
import socket


r_obj = Robot()

r_obj.connect()
print("pose values are____________________: ",r_obj.get_data()[0])

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
UNITS_TO_JUMP = 4
DEAD_ZONE = 0.1

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() > 0:
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
else:
    joystick = None
    print("Connect joystick first")

clock = pygame.time.Clock()

left_axis_x, left_axis_y = 0.0, 0.0
right_axis_x, right_axis_y = 0.0, 0.0
hat_x, hat_y = 0, 0

running = True
init_pose, init_angles = r_obj.get_data()
x, y, z, rx, ry, rz = init_pose

last_print_time = time.time()

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.JOYBUTTONDOWN:
            # Just print event
            if event.button == 8:
                print("Gripper turned on.")
                r_obj.toggle_gripper()
            if event.button == 11:
                running = False
                # More descriptive output

        # -- Remove Logic from Button Down to polling instead --

    # --- Polling for joystick actions ---
    if joystick:
        # Get axis values (left stick for movement, right stick, hat for other stuff)
        left_axis_y = joystick.get_axis(0)
        left_axis_x = joystick.get_axis(1)
        right_axis_z = joystick.get_axis(3)

        if abs(left_axis_x) < DEAD_ZONE: left_axis_x = 0.0
        if abs(left_axis_y) < DEAD_ZONE: left_axis_y = 0.0
        if abs(right_axis_z) < DEAD_ZONE: right_axis_z = 0.0

        # Adjust movement by axis
        x += (-left_axis_x) * UNITS_TO_JUMP
        y += (-left_axis_y) * UNITS_TO_JUMP
        z += (-right_axis_z) * UNITS_TO_JUMP

        # Clamping
        x = max(min(x, 750), 240)
        y = max(min(y, 550), -330)
        z = max(min(z, 500), -20)

        # =====================================================================
        # === CHECK BUTTONS FOR CONTINUOUS ROTATION (Polling) ===
        if joystick.get_button(3):  # Button 3: Continuously decrease rx
            rx -= 1 # Reduce the amount decreased for better control.  Higher number makes the roation faster.
        if joystick.get_button(4):  # Button 4: Continuously increase ry
            ry += 1 # Reduce the amount increased for better control. Higher number makes the roation faster.

        if joystick.get_button(7):  # Button 7: Continuously increase rz
            rz += 1 # Reduce the amount increased for better control. Higher number makes the roation faster.

        if joystick.get_button(1):  # Button 1: Continuously increase rx
            rx += 1 # Reduce the amount increased for better control. Higher number makes the roation faster.

        if joystick.get_button(0):  # Button 0: Continuously decrease ry
            ry -= 1 # Reduce the amount increased for better control. Higher number makes the roation faster.

        if joystick.get_button(6):  # Button 6: Continuously decrease rz
            rz -= 1 # Reduce the amount increased for better control. Higher number makes the roation faster.

        # Clamping rotation values
        rx = max(min(rx, 180), -180)
        ry = max(min(ry, 180), -180)
        rz = max(min(rz, 180), -180)
        # =====================================================================

    try:
        r_obj.send_actions(x, y, z, rx, ry, rz)
    except (UnicodeDecodeError, socket.error) as e:
        print(f"Connection error ({type(e).__name__}): {e}")
        print("Attempting to reconnect to the move port...")
        r_obj.move.close()  # Close the old socket *before* reconnecting
        r_obj.move = r_obj._connect_move()  # Re-initialize the connection

        try:
            r_obj.move.ServoP(x, y, z, rx, ry, rz)
            print("Reconnected and sent ServoP successfully.")  # Add success message

        except Exception as e:
            print(f"Error after reconnection: {e}")
            break  # Break the loop if reconnection fails again

    except Exception as e:
        print(f"Other error: {e}")
        break

    clock.tick(15)

pygame.quit()
r_obj.disconnect()