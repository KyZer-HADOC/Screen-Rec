"""
Windows helpers that keep the recorder running at full speed while the
window is minimised / hidden to tray / not focused.

Why this matters: Windows 10/11 throttle background processes (EcoQoS
"efficiency mode", coarse timer resolution, sleep when idle). For a screen
recorder that shows up as a frozen or stuttering video as soon as you
leave the app window. We opt out of all of that while recording.
"""
import ctypes
import sys

IS_WIN = sys.platform == "win32"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

_PROCESS_POWER_THROTTLING = 4  # PROCESS_INFORMATION_CLASS
_THROTTLE_CONTROL_EXECUTION_SPEED = 0x1
_THROTTLE_CONTROL_IGNORE_TIMER_RESOLUTION = 0x4


class _PowerThrottlingState(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong),
                ("ControlMask", ctypes.c_ulong),
                ("StateMask", ctypes.c_ulong)]


def disable_throttling():
    """Opt this process out of EcoQoS / timer-resolution throttling."""
    if not IS_WIN:
        return
    try:
        k32 = ctypes.windll.kernel32
        state = _PowerThrottlingState(
            1,
            _THROTTLE_CONTROL_EXECUTION_SPEED | _THROTTLE_CONTROL_IGNORE_TIMER_RESOLUTION,
            0,  # StateMask 0 = throttling OFF for the controlled bits
        )
        k32.SetProcessInformation(
            k32.GetCurrentProcess(), _PROCESS_POWER_THROTTLING,
            ctypes.byref(state), ctypes.sizeof(state))
        k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00008000)  # ABOVE_NORMAL
    except Exception:  # noqa: BLE001
        pass


def begin_recording_mode():
    """Call when a recording starts."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)  # 1 ms timer resolution
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    except Exception:  # noqa: BLE001
        pass


def end_recording_mode():
    """Call when a recording stops."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:  # noqa: BLE001
        pass


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor_pos():
    """Real, always-current global cursor position (x, y) or None."""
    if not IS_WIN:
        return None
    pt = _POINT()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
        return pt.x, pt.y
    return None
