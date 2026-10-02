"""
Tracks the global mouse cursor position and click events using pynput.
Runs a background listener thread; the recorder polls/reads shared state.
"""
import threading
import time
from collections import deque

from pynput import mouse


class ClickEvent:
    __slots__ = ("x", "y", "button", "t")

    def __init__(self, x, y, button, t):
        self.x = x
        self.y = y
        self.button = button  # "left" | "right" | "middle"
        self.t = t


class InputTracker:
    """Thread-safe tracker for cursor position and recent click events."""

    def __init__(self, click_lifetime_s: float = 1.0):
        self._pos = (0, 0)
        self._lock = threading.Lock()
        self._clicks = deque()
        self._click_lifetime_s = click_lifetime_s
        self._listener = None

    def start(self):
        self._listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_move(self, x, y):
        with self._lock:
            self._pos = (x, y)

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        name = "left"
        if button == mouse.Button.right:
            name = "right"
        elif button == mouse.Button.middle:
            name = "middle"
        with self._lock:
            self._clicks.append(ClickEvent(x, y, name, time.time()))
            self._prune_locked()

    def _on_scroll(self, x, y, dx, dy):
        with self._lock:
            self._clicks.append(ClickEvent(x, y, "middle", time.time()))
            self._prune_locked()

    def _prune_locked(self):
        cutoff = time.time() - self._click_lifetime_s
        while self._clicks and self._clicks[0].t < cutoff:
            self._clicks.popleft()

    def get_position(self):
        with self._lock:
            return self._pos

    def get_active_clicks(self):
        """Returns a snapshot list of ClickEvents still within their lifetime."""
        with self._lock:
            self._prune_locked()
            return list(self._clicks)
