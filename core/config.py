"""
Persistent configuration for Smart Screen Recorder.
Stored as JSON under %APPDATA%/SmartScreenRecorder/config.json
"""
import json
import os
from pathlib import Path

APP_NAME = "SmartScreenRecorder"


def _config_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _default_save_dir() -> str:
    videos = Path.home() / "Videos" / APP_NAME
    videos.mkdir(parents=True, exist_ok=True)
    return str(videos)


DEFAULTS = {
    # capture
    "mode": "fullscreen",          # fullscreen | area | display | gaming
    "monitor_index": 1,            # 1 = primary (mss convention)
    "area_rect": None,             # [x, y, w, h] for 'area' mode
    "fps": 30,
    "quality": "high",             # low | medium | high | custom
    "custom_resolution": [1920, 1080],
    "custom_bitrate_mbps": 12,

    # smart recording (cursor-follow zoom)
    "smart_recording": False,
    "zoom_factor": 2.0,            # 1.0 = no zoom, up to 4.0
    "zoom_smoothing": 0.15,        # 0..1, lower = smoother/slower follow

    # audio
    "record_mic": True,
    "record_system_audio": True,
    "mic_device_index": None,      # None = default
    "mic_volume": 1.0,
    "system_volume": 1.0,

    # click visualization
    "show_clicks": True,
    "click_color_left": [255, 60, 60],     # RGB - Blue-ish per user (kept configurable)
    "click_color_right": [235, 40, 40],    # Red
    "click_color_middle": [255, 220, 40],  # Yellow
    "click_fade_ms": 450,
    "click_max_radius": 32,

    # hotkeys
    "hotkeys": {
        "smart_recording": "F9",
        "screenshot": "F10",
        "start": "F11",
        "stop": "F12",
        "pause": "F8",
    },

    # output
    "save_dir": None,   # resolved lazily to _default_save_dir()
    "filename_pattern": "Recording_%Y%m%d_%H%M%S",
    "screenshot_pattern": "Screenshot_%Y%m%d_%H%M%S",
    "video_container": "mp4",

    # ui
    "theme": "dark",
    "minimize_to_tray": True,
}


class Config:
    def __init__(self):
        self.path = _config_dir() / "config.json"
        self.data = dict(DEFAULTS)
        self.load()
        if not self.data.get("save_dir"):
            self.data["save_dir"] = _default_save_dir()
            self.save()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                merged = dict(DEFAULTS)
                merged.update(loaded)
                # keep nested hotkeys merged too
                merged["hotkeys"] = {**DEFAULTS["hotkeys"], **loaded.get("hotkeys", {})}
                self.data = merged
            except (json.JSONDecodeError, OSError):
                self.data = dict(DEFAULTS)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def update(self, **kwargs):
        self.data.update(kwargs)
        self.save()
