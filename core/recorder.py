"""
The main recording engine. Runs the capture loop on a background thread:
  1. Grab a frame of the chosen region (mss)
  2. If Smart Recording is on, crop+zoom the frame around the smoothed
     cursor position (ZoomEngine)
  3. Draw colour-coded click flashes (InputTracker) transformed into the
     current crop's coordinate space
  4. Write the frame to a temp video file
  5. On stop, mux the temp video with the recorded audio into the final file

Also exposes a screenshot() method usable independently of recording.
"""
import os
import tempfile
import threading
import time
from datetime import datetime

import cv2
import mss
import numpy as np

from core.audio_capture import AudioCapture
from core.input_tracker import InputTracker
from core.muxer import mux
from core.zoom_engine import ZoomEngine

QUALITY_PRESETS = {
    # name: (max_dimension_long_side, bitrate_mbps)
    "low": (1280, 4),
    "medium": (1920, 8),
    "high": (2560, 16),
}


class RecordingState:
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"


class Recorder:
    def __init__(self, config, on_status=None, on_error=None):
        self.cfg = config
        self.on_status = on_status or (lambda *_: None)
        self.on_error = on_error or (lambda *_: None)

        self.state = RecordingState.IDLE
        self._thread = None
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()

        self.input_tracker = InputTracker()
        self._zoom_engine = None
        self._audio = None
        self._tmp_video_path = None
        self._tmp_audio_path = None
        self._final_path = None

    # ---------- region resolution ----------

    def _resolve_region(self):
        """Returns an mss-compatible monitor dict for the configured mode."""
        with mss.mss() as sct:
            mode = self.cfg.get("mode")
            if mode == "area" and self.cfg.get("area_rect"):
                x, y, w, h = self.cfg.get("area_rect")
                return {"left": x, "top": y, "width": w, "height": h}
            if mode == "display":
                idx = self.cfg.get("monitor_index", 1)
                monitors = sct.monitors
                idx = idx if idx < len(monitors) else 1
                return dict(monitors[idx])
            # fullscreen / gaming -> primary monitor
            return dict(sct.monitors[1])

    def get_preview_region(self):
        """Public helper so the UI can show a live thumbnail of the region
        that would be captured, without starting an actual recording."""
        return self._resolve_region()

    # ---------- public controls ----------

    def start(self):
        if self.state != RecordingState.IDLE:
            return
        self._stop_flag.clear()
        self._pause_flag.clear()

        region = self._resolve_region()
        self._region = region

        fps = int(self.cfg.get("fps", 30))
        quality = self.cfg.get("quality", "high")
        if quality == "custom":
            out_w, out_h = self.cfg.get("custom_resolution", [1920, 1080])
            bitrate = int(self.cfg.get("custom_bitrate_mbps", 12))
        else:
            max_dim, bitrate = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])
            src_w, src_h = region["width"], region["height"]
            scale = min(1.0, max_dim / max(src_w, src_h))
            out_w, out_h = int(src_w * scale) // 2 * 2, int(src_h * scale) // 2 * 2
        # guard against degenerate 0-sized output (e.g. a tiny selected area)
        out_w = max(out_w, 2)
        out_h = max(out_h, 2)
        self._out_size = (out_w, out_h)
        self._bitrate = bitrate

        self._zoom_engine = ZoomEngine(region["width"], region["height"],
                                        zoom_factor=self.cfg.get("zoom_factor", 2.0),
                                        smoothing=self.cfg.get("zoom_smoothing", 0.15))

        tmp_dir = tempfile.mkdtemp(prefix="ssr_")
        # Raw capture uses AVI/XVID (or MJPG as fallback) rather than mp4/mp4v:
        # the mp4v fourcc frequently fails to open (or writes an unreadable,
        # 0-length file) on the stock Windows opencv-python wheel. AVI+XVID
        # is reliably writable there; the final output is still re-encoded
        # to a proper MP4 (H.264) by the ffmpeg mux step below.
        self._tmp_video_path = os.path.join(tmp_dir, "video_raw.avi")
        self._tmp_audio_path = os.path.join(tmp_dir, "audio.wav")

        self._writer = self._open_writer(self._tmp_video_path, fps, self._out_size)
        self._frames_written = 0

        record_mic = self.cfg.get("record_mic", True)
        record_sys = self.cfg.get("record_system_audio", True)
        self._audio_requested = record_mic or record_sys
        self._audio = None
        if self._audio_requested:
            self._audio = AudioCapture(
                record_mic=record_mic,
                record_system=record_sys,
                mic_device_index=self.cfg.get("mic_device_index"),
                mic_volume=self.cfg.get("mic_volume", 1.0),
                system_volume=self.cfg.get("system_volume", 1.0),
                on_warn=lambda msg: self.on_error(msg),
            )
            self._audio.start()

        self.input_tracker.start()
        self.state = RecordingState.RECORDING
        self.on_status("recording_started")

        self._thread = threading.Thread(target=self._capture_loop, args=(fps,), daemon=True)
        self._thread.start()

    @staticmethod
    def _open_writer(path, fps, size):
        for codec in ("XVID", "MJPG"):
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(path, fourcc, fps, size)
            if writer.isOpened():
                return writer
            writer.release()
        raise RuntimeError(
            "Could not open a video writer (tried XVID, MJPG). "
            "This usually means OpenCV's video backend isn't available - "
            "try `pip install opencv-python` again or reinstall it."
        )

    def pause(self):
        if self.state == RecordingState.RECORDING:
            self._pause_flag.set()
            self.state = RecordingState.PAUSED
            self.on_status("paused")

    def resume(self):
        if self.state == RecordingState.PAUSED:
            self._pause_flag.clear()
            self.state = RecordingState.RECORDING
            self.on_status("resumed")

    def toggle_pause(self):
        if self.state == RecordingState.RECORDING:
            self.pause()
        elif self.state == RecordingState.PAUSED:
            self.resume()

    def set_smart_recording(self, enabled: bool):
        self.cfg.set("smart_recording", enabled)
        self.on_status("smart_recording_toggled")

    def stop(self) -> str:
        """Stops recording, muxes audio+video, returns final output path."""
        if self.state == RecordingState.IDLE:
            return None
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.input_tracker.stop()
        self._writer.release()

        if self._frames_written == 0:
            self.on_error(
                "No frames were captured during this recording - the output "
                "would be empty, so nothing was saved. Check that the "
                "capture region/monitor is valid and try again."
            )
            self.state = RecordingState.IDLE
            self.on_status("stopped")
            return None

        # Only attach an audio track if audio actually produced samples -
        # an empty/failed audio stream must never be allowed to truncate
        # the final video (see core/muxer.py for why).
        audio_sample_count = 0
        if self._audio_requested and self._audio:
            audio_sample_count = self._audio.stop_and_save(self._tmp_audio_path)
        has_audio = audio_sample_count > 0

        save_dir = self.cfg.get("save_dir")
        os.makedirs(save_dir, exist_ok=True)
        fname = datetime.now().strftime(self.cfg.get("filename_pattern")) + \
            "." + self.cfg.get("video_container", "mp4")
        self._final_path = os.path.join(save_dir, fname)

        try:
            mux(self._tmp_video_path, self._tmp_audio_path, self._final_path,
                bitrate_mbps=self._bitrate, has_audio=has_audio)
        except Exception as e:  # noqa: BLE001
            self.on_error(f"Mux failed, keeping raw video only: {e}")
            self._final_path = self._tmp_video_path

        self.state = RecordingState.IDLE
        self.on_status("stopped")
        return self._final_path

    def screenshot(self) -> str:
        """Independent single-frame capture, saved as PNG."""
        region = self._region if self.state != RecordingState.IDLE else self._resolve_region()
        with mss.mss() as sct:
            raw = sct.grab(region)
            frame = np.array(raw)[:, :, :3]  # BGRA -> BGR

        save_dir = self.cfg.get("save_dir")
        os.makedirs(save_dir, exist_ok=True)
        fname = datetime.now().strftime(self.cfg.get("screenshot_pattern")) + ".png"
        path = os.path.join(save_dir, fname)
        cv2.imwrite(path, frame)
        self.on_status(f"screenshot_saved:{path}")
        return path

    # ---------- capture loop ----------

    def _click_color(self, button: str):
        key = {"left": "click_color_left", "right": "click_color_right",
               "middle": "click_color_middle"}[button]
        r, g, b = self.cfg.get(key)
        return (b, g, r)  # BGR for OpenCV

    def _draw_clicks(self, frame, crop_rect, scale_x, scale_y):
        if not self.cfg.get("show_clicks", True):
            return frame
        active = self.input_tracker.get_active_clicks()
        if not active:
            return frame  # skip the copy/blend entirely when there's nothing to draw

        now = time.time()
        fade_s = self.cfg.get("click_fade_ms", 450) / 1000.0
        max_r = self.cfg.get("click_max_radius", 32)
        cx0, cy0, cw, ch = crop_rect

        overlay = frame.copy()
        any_drawn = False
        for click in active:
            age = now - click.t
            if age > fade_s:
                continue
            progress = age / fade_s
            # local coords within captured region
            lx = click.x - self._region["left"]
            ly = click.y - self._region["top"]
            if not (cx0 <= lx <= cx0 + cw and cy0 <= ly <= cy0 + ch):
                continue
            px = int((lx - cx0) * scale_x)
            py = int((ly - cy0) * scale_y)
            radius = int(6 + progress * max_r)
            color = self._click_color(click.button)
            cv2.circle(overlay, (px, py), radius, color, thickness=3,
                       lineType=cv2.LINE_AA)
            any_drawn = True
        if any_drawn:
            cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, dst=frame)
        return frame

    def _capture_loop(self, fps: int):
        """
        Writes frames on a strict wall-clock schedule so the saved video's
        duration always matches the real time spent recording, regardless
        of how long grabbing/processing each frame actually takes:

          - a slow frame (e.g. big monitor + smart-zoom + resize) no longer
            shrinks the output's reported duration - we duplicate the most
            recently processed frame to catch up to the schedule instead of
            just writing one frame per loop iteration.
          - paused time is excluded from the schedule so pausing doesn't
            change playback speed once resumed.
        """
        out_w, out_h = self._out_size
        start_time = time.perf_counter()
        paused_total = 0.0
        last_tick = start_time
        frames_due = 0          # how many frames *should* exist by now
        last_processed = None
        # safety cap: never duplicate more than 2 seconds worth of frames in
        # one go (e.g. after the OS suspends the process) to avoid a huge
        # write burst freezing the app.
        max_catchup_frames = max(int(fps * 2), 1)

        with mss.mss() as sct:
            while not self._stop_flag.is_set():
                if self._pause_flag.is_set():
                    pause_started = time.perf_counter()
                    while self._pause_flag.is_set() and not self._stop_flag.is_set():
                        time.sleep(0.02)
                    paused_total += time.perf_counter() - pause_started
                    last_tick = time.perf_counter()
                    continue

                now = time.perf_counter()
                dt = max(now - last_tick, 1e-3)
                last_tick = now

                raw = sct.grab(self._region)
                frame = np.array(raw)[:, :, :3]  # BGRA -> BGR

                if self.cfg.get("smart_recording", False):
                    cx, cy = self.input_tracker.get_position()
                    lx = cx - self._region["left"]
                    ly = cy - self._region["top"]
                    self._zoom_engine.set_zoom_factor(self.cfg.get("zoom_factor", 2.0))
                    self._zoom_engine.set_smoothing(self.cfg.get("zoom_smoothing", 0.15))
                    x, y, w, h = self._zoom_engine.update(lx, ly, dt=dt)
                    cropped = frame[y:y + h, x:x + w]
                    scale_x = out_w / w
                    scale_y = out_h / h
                    cropped = self._draw_clicks(cropped, (x, y, w, h), scale_x, scale_y)
                    resized = cv2.resize(cropped, (out_w, out_h),
                                          interpolation=cv2.INTER_LINEAR)
                else:
                    full_rect = (0, 0, self._region["width"], self._region["height"])
                    scale_x = out_w / self._region["width"]
                    scale_y = out_h / self._region["height"]
                    frame = self._draw_clicks(frame, full_rect, scale_x, scale_y)
                    resized = cv2.resize(frame, (out_w, out_h),
                                          interpolation=cv2.INTER_LINEAR)

                last_processed = resized

                elapsed = time.perf_counter() - start_time - paused_total
                target_frames = int(elapsed * fps) + 1
                target_frames = min(target_frames, frames_due + max_catchup_frames)
                while frames_due < target_frames:
                    self._writer.write(last_processed)
                    self._frames_written += 1
                    frames_due += 1

                # if we're running ahead of real time (fast machine / simple
                # capture), sleep off the remainder instead of busy-looping
                next_due_time = start_time + paused_total + (frames_due / fps)
                sleep_time = next_due_time - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.05))
