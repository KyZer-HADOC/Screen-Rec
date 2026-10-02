"""
Global hotkey manager. Works system-wide on Windows (even when the app
window isn't focused) using the `keyboard` library.

Note: on some Windows setups the `keyboard` library needs the app to be
run as Administrator to catch keys while an elevated app (e.g. some games)
has focus. This is documented in the README.
"""
import keyboard


class HotkeyManager:
    def __init__(self):
        self._registered = {}  # action_name -> key_string

    def register(self, action_name: str, key: str, callback):
        self.unregister(action_name)
        keyboard.add_hotkey(key, callback, suppress=False)
        self._registered[action_name] = key

    def unregister(self, action_name: str):
        key = self._registered.pop(action_name, None)
        if key:
            try:
                keyboard.remove_hotkey(key)
            except KeyError:
                pass

    def unregister_all(self):
        for name in list(self._registered.keys()):
            self.unregister(name)

    def rebind(self, action_name: str, new_key: str, callback):
        """Convenience: unregister old binding for this action, register new one."""
        self.register(action_name, new_key, callback)
