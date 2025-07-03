import pyrealsense2 as rs
import time
import numpy as np
import threading


class Camera:
    def __init__(self, width=640, height=480):
        # Camera configuration
        self.camera_config = {
            'top': {'name': 'Intel RealSense D435I', 'serial': '317222071930', 'resolution': (width, height)},
            'wrist': {'name': 'Intel RealSense D415', 'serial': '217222067470', 'resolution': (width, height)}
        }
        self.primary_pipeline, self.wrist_pipeline = self.setup_cameras()

        # --- NEW: Threading and Frame Management ---
        self.latest_top_frame = np.zeros((height, width, 3), dtype=np.uint8)
        self.latest_wrist_frame = np.zeros((height, width, 3), dtype=np.uint8)
        self._frame_lock = threading.Lock()
        self._capture_thread = None
        self._is_capturing = False

    def setup_cameras(self):
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

    # --- NEW: Threaded capture loop ---
    def _capture_loop(self):
        """The target function for the frame capture thread."""
        while self._is_capturing:
            try:
                primary_frames = self.primary_pipeline.wait_for_frames(1000)
                wrist_frames = self.wrist_pipeline.wait_for_frames(1000)

                if primary_frames and wrist_frames:
                    primary_color_frame = primary_frames.get_color_frame()
                    wrist_color_frame = wrist_frames.get_color_frame()

                    if primary_color_frame and wrist_color_frame:
                        top_frame_data = np.asanyarray(primary_color_frame.get_data())
                        wrist_frame_data = np.asanyarray(wrist_color_frame.get_data())

                        with self._frame_lock:
                            self.latest_top_frame = top_frame_data
                            self.latest_wrist_frame = wrist_frame_data
            except Exception as e:
                print(f"Frame capture failed in thread: {e}")
                time.sleep(0.5)

    # --- NEW: Thread management methods ---
    def start_capture(self):
        """Starts the background thread for capturing frames."""
        if not self._is_capturing:
            self._is_capturing = True
            self._capture_thread = threading.Thread(target=self._capture_loop)
            self._capture_thread.daemon = True
            self._capture_thread.start()
            print("Camera capture thread started.")

    def stop_capture(self):
        """Stops the background capture thread."""
        if self._is_capturing:
            self._is_capturing = False
            if self._capture_thread:
                self._capture_thread.join()
            print("Camera capture thread stopped.")

    # --- MODIFIED: capture_frames is now non-blocking ---
    def capture_frames(self):
        """This method now reads from the latest frames, making it non-blocking."""
        with self._frame_lock:
            return self.latest_top_frame, self.latest_wrist_frame

    # --- NEW: Graceful shutdown method ---
    def close(self):
        """Stops the thread and closes the camera pipelines."""
        self.stop_capture()
        if self.primary_pipeline:
            self.primary_pipeline.stop()
        if self.wrist_pipeline:
            self.wrist_pipeline.stop()
        print("Cameras stopped and closed.")