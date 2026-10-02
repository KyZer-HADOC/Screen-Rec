"""
Computes the cursor-follow "smart zoom" crop window for each frame,
with exponential smoothing so the zoom glides toward the cursor instead
of snapping instantly. The smoothing is time-based (not per-frame), so
the follow speed stays consistent even if frames arrive at irregular
intervals (e.g. a slow frame under CPU load, or a different preview fps
than the real recording fps) - the effect looks the same either way.
"""

# The "smoothing" setting (0..1) is calibrated against this reference frame
# time, so its on-screen meaning stays the same as before this file
# supported variable dt: at exactly REFERENCE_DT between updates, alpha
# == smoothing, same as the old fixed-step behaviour.
REFERENCE_DT = 1.0 / 30.0


class ZoomEngine:
    def __init__(self, frame_w: int, frame_h: int, zoom_factor: float = 2.0,
                 smoothing: float = 0.15):
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.zoom_factor = max(1.0, min(zoom_factor, 4.0))
        self.smoothing = max(0.01, min(smoothing, 1.0))
        # current smoothed center of the crop window (starts at screen center)
        self._cx = frame_w / 2.0
        self._cy = frame_h / 2.0

    def set_zoom_factor(self, factor: float):
        self.zoom_factor = max(1.0, min(factor, 4.0))

    def set_smoothing(self, smoothing: float):
        self.smoothing = max(0.01, min(smoothing, 1.0))

    def crop_size(self):
        cw = self.frame_w / self.zoom_factor
        ch = self.frame_h / self.zoom_factor
        return cw, ch

    def update(self, cursor_x: int, cursor_y: int, dt: float = None):
        """Advance the smoothed center toward the cursor.

        dt: seconds since the previous update. If omitted, behaves like the
        old fixed-step version (one REFERENCE_DT step)."""
        if dt is None:
            alpha = self.smoothing
        else:
            steps = max(dt, 1e-4) / REFERENCE_DT
            # alpha such that repeating it `steps` times over dt matches
            # doing it once per REFERENCE_DT at the configured smoothing
            alpha = 1.0 - (1.0 - self.smoothing) ** steps
            alpha = max(0.0, min(alpha, 1.0))
        self._cx += (cursor_x - self._cx) * alpha
        self._cy += (cursor_y - self._cy) * alpha
        return self.get_crop_rect()

    def get_crop_rect(self):
        """Returns (x, y, w, h) clamped inside the frame bounds."""
        cw, ch = self.crop_size()
        x = self._cx - cw / 2.0
        y = self._cy - ch / 2.0
        x = max(0.0, min(x, self.frame_w - cw))
        y = max(0.0, min(y, self.frame_h - ch))
        return int(round(x)), int(round(y)), int(round(cw)), int(round(ch))

    def reset(self):
        self._cx = self.frame_w / 2.0
        self._cy = self.frame_h / 2.0

