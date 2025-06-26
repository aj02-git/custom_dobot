import pyrealsense2 as rs
import time
import numpy as np


class Camera:
    def __init__(self, width=640, height=480):
        # Camera configuration
        self.camera_config = {
            'top': {'name': 'Intel RealSense D435I', 'serial': '317222071930', 'resolution': (width, height)},
            'wrist': {'name': 'Intel RealSense D415', 'serial': '217222067470', 'resolution': (width, height)}
        }
        self.primary_pipeline, self.wrist_pipeline = self.setup_cameras()


    def setup_cameras(self):
        # This function seems correct and does not need changes for robot feedback.
        ctx = rs.context()
        devices = ctx.query_devices()
        available_serials = [dev.get_info(rs.camera_info.serial_number) for dev in devices]
        pipelines = []
        for cam_type in ['top', 'wrist']:
            cam_info = self.camera_config[cam_type]
            if cam_info['serial'] not in available_serials:
                raise ConnectionError(f"Camera {cam_type} with serial {cam_info['serial']} not found.")
            pipeline = rs.pipeline(ctx)
            config = rs.config()
            config.enable_device(cam_info['serial'])
            config.enable_stream(rs.stream.color, *cam_info['resolution'], rs.format.bgr8, 30)
            try:
                pipeline.start(config)
                time.sleep(1)
            except Exception as e:
                for p in pipelines: p.stop()
                raise e
            pipelines.append(pipeline)
        print("Both cameras initialized successfully.")
        return pipelines[0], pipelines[1]

    def capture_frames(self):
        # This function is also fine.
        try:
            primary_frames = self.primary_pipeline.wait_for_frames(1000)
            wrist_frames = self.wrist_pipeline.wait_for_frames(1000)
            primary_color_frame = primary_frames.get_color_frame()
            wrist_color_frame = wrist_frames.get_color_frame()
            if not primary_color_frame or not wrist_color_frame:
                return None, None
            return (np.asanyarray(primary_color_frame.get_data()),
                    np.asanyarray(wrist_color_frame.get_data()))
        except Exception as e:
            print(f"Frame capture failed: {e}")
            return None, None