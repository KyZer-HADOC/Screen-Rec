"""
Captures microphone audio and/or system (desktop) audio on Windows using
PyAudioWPatch, which adds WASAPI loopback support to PyAudio. Both streams
are resampled to a common rate and mixed in real time, then written to a WAV
file. The final mux step (core/muxer.py) combines this WAV with the video.

Hardened: if a device fails to open (no mic present, loopback not
available, etc.) that stream is silently disabled instead of crashing the
whole recording, and a warning is reported via on_warn.
"""
import threading
import wave

import numpy as np
import pyaudiowpatch as pyaudio

RATE = 44100
CHUNK = 1024
FORMAT = pyaudio.paInt16


class AudioCapture:
    def __init__(self, record_mic=True, record_system=True,
                 mic_device_index=None, mic_volume=1.0, system_volume=1.0,
                 on_warn=None):
        self.record_mic = record_mic
        self.record_system = record_system
        self.mic_device_index = mic_device_index
        self.mic_volume = mic_volume
        self.system_volume = system_volume
        self.on_warn = on_warn or (lambda msg: None)

        self._pa = pyaudio.PyAudio()
        self._mic_stream = None
        self._sys_stream = None
        self._lock = threading.Lock()
        self._mic_rate = RATE
        self._sys_rate = RATE
        self._sys_channels = 2
        self.mic_active = False
        self.sys_active = False

    def _get_default_loopback_device(self):
        """Finds the WASAPI loopback device that mirrors the default speakers."""
        wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self._pa.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )
        if not default_speakers.get("isLoopbackDevice", False):
            for loopback in self._pa.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    return loopback
        return default_speakers

    def start(self):
        self._frames_mic = []
        self._frames_sys = []

        if self.record_mic:
            try:
                mic_info = (
                    self._pa.get_device_info_by_index(self.mic_device_index)
                    if self.mic_device_index is not None
                    else self._pa.get_default_input_device_info()
                )
                self._mic_rate = int(mic_info["defaultSampleRate"])
                self._mic_stream = self._pa.open(
                    format=FORMAT, channels=1, rate=self._mic_rate,
                    input=True, input_device_index=mic_info["index"],
                    frames_per_buffer=CHUNK,
                    stream_callback=self._make_callback(self._frames_mic),
                )
                self._mic_stream.start_stream()
                self.mic_active = True
            except Exception as e:  # noqa: BLE001
                self.mic_active = False
                self.on_warn(f"Microphone unavailable, recording without it: {e}")

        if self.record_system:
            try:
                loop_dev = self._get_default_loopback_device()
                self._sys_channels = int(loop_dev["maxInputChannels"]) or 2
                self._sys_rate = int(loop_dev["defaultSampleRate"])
                self._sys_stream = self._pa.open(
                    format=FORMAT, channels=self._sys_channels,
                    rate=self._sys_rate,
                    input=True, input_device_index=loop_dev["index"],
                    frames_per_buffer=CHUNK,
                    stream_callback=self._make_callback(self._frames_sys),
                )
                self._sys_stream.start_stream()
                self.sys_active = True
            except Exception as e:  # noqa: BLE001
                self.sys_active = False
                self.on_warn(f"System audio unavailable, recording without it: {e}")

    def _make_callback(self, sink):
        def _cb(in_data, frame_count, time_info, status):
            with self._lock:
                sink.append(in_data)
            return (None, pyaudio.paContinue)
        return _cb

    def stop_and_save(self, wav_path: str) -> int:
        """Writes the mixed WAV file. Returns the number of sample frames written
        (0 means the file is effectively silent/empty, useful for the caller to
        decide whether to attach an audio track at all)."""
        for stream in (self._mic_stream, self._sys_stream):
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass

        mic_audio = (
            self._decode(self._frames_mic, channels=1, src_rate=self._mic_rate)
            if self.mic_active else None
        )
        sys_audio = (
            self._decode(self._frames_sys, channels=self._sys_channels,
                          src_rate=self._sys_rate)
            if self.sys_active else None
        )

        mixed = self._mix(mic_audio, sys_audio)
        self._write_wav(wav_path, mixed)
        try:
            self._pa.terminate()
        except Exception:  # noqa: BLE001
            pass
        return int(mixed.shape[0])

    @staticmethod
    def _resample(arr: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if src_rate == dst_rate or arr.shape[0] == 0:
            return arr
        duration = arr.shape[0] / src_rate
        dst_len = int(round(duration * dst_rate))
        if dst_len <= 0:
            return np.zeros((0, arr.shape[1]), dtype=np.float32)
        src_idx = np.linspace(0, arr.shape[0] - 1, num=arr.shape[0])
        dst_idx = np.linspace(0, arr.shape[0] - 1, num=dst_len)
        out = np.stack(
            [np.interp(dst_idx, src_idx, arr[:, c]) for c in range(arr.shape[1])],
            axis=1,
        ).astype(np.float32)
        return out

    @classmethod
    def _decode(cls, raw_frames, channels, src_rate):
        if not raw_frames:
            return np.zeros((0, 2), dtype=np.float32)
        buf = b"".join(raw_frames)
        arr = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            usable_len = (arr.shape[0] // channels) * channels
            arr = arr[:usable_len].reshape(-1, channels)
            if channels != 2:
                mono = arr.mean(axis=1, keepdims=True)
                arr = np.repeat(mono, 2, axis=1)
        else:
            arr = np.repeat(arr.reshape(-1, 1), 2, axis=1)
        return cls._resample(arr, src_rate, RATE)

    def _mix(self, mic, sysaudio):
        streams = []
        if mic is not None and mic.size:
            streams.append(mic * self.mic_volume)
        if sysaudio is not None and sysaudio.size:
            streams.append(sysaudio * self.system_volume)
        if not streams:
            return np.zeros((0, 2), dtype=np.float32)
        max_len = max(s.shape[0] for s in streams)
        padded = [np.pad(s, ((0, max_len - s.shape[0]), (0, 0))) for s in streams]
        mixed = np.sum(padded, axis=0)
        mixed = np.clip(mixed, -1.0, 1.0)
        return mixed

    @staticmethod
    def _write_wav(path, float_stereo):
        int_data = (float_stereo * 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(int_data.tobytes())

    def list_input_devices(self):
        devices = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append({"index": i, "name": info["name"]})
        return devices
