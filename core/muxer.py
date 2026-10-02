"""
Combines the raw captured video (written by the recorder as a temp .avi/.mp4
with no audio) and the recorded audio (.wav) into the final output file,
using the ffmpeg binary bundled by imageio-ffmpeg (no separate install needed).
"""
import subprocess

import imageio_ffmpeg


def mux(video_path: str, audio_path: str, output_path: str,
        bitrate_mbps: int = 12, has_audio: bool = True):
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    if has_audio:
        # No -shortest here on purpose: if the audio stream is empty or
        # shorter than the video (e.g. a mic/loopback hiccup), -shortest
        # would truncate the WHOLE output to that length, producing a
        # near-zero-duration file. -map explicitly + no -shortest keeps
        # the video's full length regardless of the audio track's length.
        cmd = [
            ffmpeg_exe, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", f"{bitrate_mbps}M",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        cmd = [
            ffmpeg_exe, "-y",
            "-i", video_path,
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", f"{bitrate_mbps}M",
            "-movflags", "+faststart",
            output_path,
        ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg mux failed:\n{result.stderr.decode(errors='ignore')}"
        )
    return output_path
