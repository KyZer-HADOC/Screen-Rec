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
import logging
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
from core import win_power
from core.zoom_engine import ZoomEngine

QUALITY_PRESETS = {
    # name: (max_dimension_long_side, bitrate_mbps)
    "low": (1280, 4),
    "medium": (1920, 8),
    "high": (2560, 16),
}


log = logging.getLogger("ssr")


def _setup_logging():
    """Log to %APPDATA%/SmartScreenRecorder/log.txt so silent failures in
    the windowed .exe (no console) can actually be diagnosed."""
    if log.handlers:
        return
    try:
        base = os.getenv("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "SmartScreenRecorder")
        os.makedirs(d, exist_ok=True)
        h = logging.FileHandler(os.path.join(d, "log.txt"), encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    except Exception:  # noqa: BLE001
        pass


_setup_logging()


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

        self._t0 = time.perf_counter()
        self._paused_total = 0.0
        self._frames_due = 0
        self._last_processed = None

        win_power.begin_recording_mode()
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
        win_power.end_recording_mode()

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

    def _draw_cursor(self, frame, crop_rect, scale_x, scale_y):
        """mss never captures the mouse pointer, so draw one ourselves at the
        real current cursor position (white arrow with dark outline)."""
        if not self.cfg.get("show_cursor", True):
            return frame
        pos = win_power.cursor_pos() or self.input_tracker.get_position()
        cx0, cy0, cw, ch = crop_rect
        lx = pos[0] - self._region["left"]
        ly = pos[1] - self._region["top"]
        if not (cx0 <= lx <= cx0 + cw and cy0 <= ly <= cy0 + ch):
            return frame
        px = int((lx - cx0) * scale_x)
        py = int((ly - cy0) * scale_y)
        k = max(0.8, min(scale_x, scale_y)) * float(self.cfg.get("cursor_scale", 1.0))
        # classic arrow shape, tip at (0, 0)
        arrow = np.array([(0, 0), (0, 17), (4, 13), (7, 20), (10, 19),
                          (7, 12), (12, 12)], dtype=np.float32) * k
        pts = (arrow + np.array([px, py], dtype=np.float32)).astype(np.int32)
        cv2.fillPoly(frame, [pts], (255, 255, 255), lineType=cv2.LINE_AA)
        cv2.polylines(frame, [pts], True, (0, 0, 0), thickness=max(1, int(round(k))),
                      lineType=cv2.LINE_AA)
        return frame

    def _capture_loop(self, fps: int):
        """Crash-proof wrapper: any error is logged, the capture keeps going,
        and the user is told if it ever has to give up."""
        failures = 0
        while not self._stop_flag.is_set():
            try:
                self._capture_loop_inner(fps)
                return
            except Exception as e:  # noqa: BLE001
                failures += 1
                log.exception("capture loop error (#%d)", failures)
                if failures >= 20:
                    self.on_error(f"Recording capture failed repeatedly: {e}")
                    return
                time.sleep(0.2)

    def _capture_loop_inner(self, fps: int):
        """
        Writes frames on a strict wall-clock schedule so the saved video's
        duration always matches the real time spent recording. Slow frames
        are caught up by duplicating the last frame; paused time is excluded.
        Timing state lives on self so the loop can resume after an error.
        """
        out_w, out_h = self._out_size
        max_catchup_frames = max(int(fps * 2), 1)
        last_tick = time.perf_counter()

        with mss.mss() as sct:
            while not self._stop_flag.is_set():
                if self._pause_flag.is_set():
                    pause_started = time.perf_counter()
                    while self._pause_flag.is_set() and not self._stop_flag.is_set():
                        time.sleep(0.02)
                    self._paused_total += time.perf_counter() - pause_started
                    last_tick = time.perf_counter()
                    continue

                now = time.perf_counter()
                dt = max(now - last_tick, 1e-3)
                last_tick = now

                raw = sct.grab(self._region)
                frame = np.array(raw)[:, :, :3]  # BGRA -> BGR
                frame = np.ascontiguousarray(frame)

                if self.cfg.get("smart_recording", False):
                    pos = win_power.cursor_pos() or self.input_tracker.get_position()
                    lx = pos[0] - self._region["left"]
                    ly = pos[1] - self._region["top"]
                    self._zoom_engine.set_zoom_factor(self.cfg.get("zoom_factor", 2.0))
                    self._zoom_engine.set_smoothing(self.cfg.get("zoom_smoothing", 0.15))
                    x, y, w, h = self._zoom_engine.update(lx, ly, dt=dt)
                    w, h = max(w, 2), max(h, 2)
                    cropped = np.ascontiguousarray(frame[y:y + h, x:x + w])
                    scale_x = out_w / w
                    scale_y = out_h / h
                    resized = cv2.resize(cropped, (out_w, out_h),
                                          interpolation=cv2.INTER_LINEAR)
                    rect = (x, y, w, h)
                else:
                    scale_x = out_w / self._region["width"]
                    scale_y = out_h / self._region["height"]
                    resized = cv2.resize(frame, (out_w, out_h),
                                          interpolation=cv2.INTER_LINEAR)
                    rect = (0, 0, self._region["width"], self._region["height"])

                # draw on the OUTPUT-sized frame so line widths/radii stay crisp
                resized = self._draw_clicks(resized, rect, scale_x, scale_y)
                resized = self._draw_cursor(resized, rect, scale_x, scale_y)
                self._last_processed = resized

                elapsed = time.perf_counter() - self._t0 - self._paused_total
                target_frames = int(elapsed * fps) + 1
                target_frames = min(target_frames, self._frames_due + max_catchup_frames)
                while self._frames_due < target_frames:
                    self._writer.write(self._last_processed)
                    self._frames_written += 1
                    self._frames_due += 1

                next_due_time = self._t0 + self._paused_total + (self._frames_due / fps)
                sleep_time = next_due_time - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.05))
