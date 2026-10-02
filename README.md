## Download a ready-made Setup.exe

Every push to `main` automatically builds a Windows installer via GitHub
Actions (see `.github/workflows/build-windows.yml`) - no local Python setup
needed to just install and use the app:

1. Go to the repo's **Actions** tab → latest **Build Windows Setup.exe** run.
2. Download the **SmartScreenRecorder-Setup** artifact (a zip containing
   `SmartScreenRecorder-Setup.exe`).
3. Run it - it installs to Program Files, adds Start Menu / optional
   Desktop shortcuts, and includes an uninstaller.

Pushing a version tag (e.g. `git tag v1.0.0 && git push --tags`) also
attaches the installer directly to a GitHub **Release**, so people can
download it from the Releases page without needing an Actions login.

### Building it yourself

```bash
pip install -r requirements-build.txt
python tools/generate_icon.py             # -> assets/icon.ico (generated, not committed)
pyinstaller --noconfirm build.spec        # -> dist/SmartScreenRecorder/
# then, with Inno Setup (https://jrsoftware.org/isinfo.php) installed:
ISCC.exe installer.iss                    # -> installer_output/SmartScreenRecorder-Setup.exe
```

## Update: fixed short/1-second recordings + smoother Smart Zoom

- **Fixed: recording duration much shorter than the real time spent
  recording (e.g. "recorded 10s, got a ~1s video").** The capture loop used
  to write exactly one frame per loop iteration and count duration as
  `frames_written / fps`. If grabbing + zooming + resizing a frame ever
  took longer than one frame interval (very likely on a large/4K monitor,
  or with Smart Recording + click overlays on), the loop simply fell
  behind - real elapsed time kept increasing but far fewer frames were
  ever written, so the saved file (frames ÷ fps) came out much shorter
  than the real recording. The capture loop is now scheduled against a
  wall-clock timeline: it tracks exactly how many frames *should* exist by
  now and writes duplicates of the latest processed frame to catch up, so
  the output's duration always matches the real time you were recording
  (minus any paused time), no matter how heavy the processing is.
- **Smoother Smart Zoom**: the cursor-follow smoothing is now time-based
  instead of per-frame, so the zoom glides at a consistent speed even when
  individual frames take variable time to process - it no longer speeds
  up/slows down or jitters when the system is under load.
- **Small performance win**: click-flash drawing now skips the
  frame-copy/blend step entirely when there are no active clicks to draw,
  instead of doing it on every single frame.

## Update: live preview + fixed empty-output bug

- **Live Preview** panel added to the top of the main window — shows the
  currently selected capture region in real time (12fps thumbnail), and
  simulates the Smart Zoom effect live so you can tune zoom/smoothing by eye
  before recording.
- **Fixed: recordings coming out empty / 0.00 length.** Root causes:
  1. The raw capture was written with the `mp4v` codec into a `.mp4`
     container, which frequently fails silently (0-byte/unreadable file) on
     the stock Windows `opencv-python` wheel. Raw capture now uses AVI/XVID
     (falling back to MJPG) which is reliable on Windows, then ffmpeg
     re-encodes it to a proper H.264 MP4 at the end.
  2. The final mux used ffmpeg's `-shortest` flag — if the audio stream
     failed to capture anything (e.g. mic or loopback device didn't open),
     that empty audio stream forced the *entire* output down to ~0 seconds.
     The mux no longer uses `-shortest`, and an audio track is only
     attached if it actually contains samples.
  3. Audio device failures (missing mic, no loopback device) now degrade
     gracefully instead of silently producing empty audio — you'll get a
     warning instead of a broken file.
  4. If literally zero video frames were captured (e.g. invalid region),
     the app now tells you instead of saving a broken file.

# Smart Screen Recorder (Windows)

Full-featured screen recorder: multiple capture modes, cursor-following
"smart zoom", colour-coded click flashes, mic + system audio, and global
hotkeys that work even when the app is minimized to the tray.

## Setup (Windows, Python 3.10–3.12 recommended)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python tools/generate_icon.py   # optional - gives the window/tray a proper icon
python main.py
```

No separate ffmpeg install is needed — `imageio-ffmpeg` bundles a static
ffmpeg binary used only for the final audio+video mux.

> **Run as Administrator** if hotkeys don't respond while another elevated
> app (some games, some antivirus-protected apps) has focus — this is a
> limitation of the Windows global-hotkey hook used by the `keyboard`
> library, not this app.

## Features

- **Modes**: Full Screen, Selected Area (drag to pick a region), Display
  (choose a specific monitor), Gaming (fullscreen preset).
- **Smart Recording**: zooms into whichever part of the screen your mouse
  is on, smoothly following the cursor as it moves (adjustable zoom amount
  and follow-smoothness in the main window).
- **Colour-coded clicks**: Left click = blue, Right click = red, Mouse
  wheel/middle = yellow, by default — fully customizable in Settings →
  Click Colours.
- **Audio**: microphone and/or system (desktop) audio, mixed together.
  System audio uses WASAPI loopback via `PyAudioWPatch` — Windows only.
- **Quality**: Low / Medium / High presets, or Custom resolution + bitrate.
- **Hotkeys** (global, editable in Settings):
  | Key | Action |
  |-----|--------|
  | F9  | Toggle Smart Recording |
  | F10 | Screenshot |
  | F11 | Start recording |
  | F12 | Stop recording |
  | F8  | Pause / Resume |
- **Save location**: choose any folder; files are auto-named with a
  timestamp (`Recording_YYYYMMDD_HHMMSS.mp4`, `Screenshot_YYYYMMDD_HHMMSS.png`).

## How Smart Recording works

Each captured frame is cropped to a window around the cursor (window size
= screen size ÷ zoom factor) and scaled back up to the output resolution.
The crop's center eases toward the cursor every frame (exponential
smoothing) instead of snapping instantly, so the zoom glides rather than
jitters. Click flashes are drawn in the *original* frame's coordinate
space and re-mapped into the zoomed/cropped view, so they stay accurate
even while zoomed in.

## Known limitations

- Capture uses `mss` (GDI-based). It works for windowed/borderless games
  and virtually everything else, but some exclusive-fullscreen DirectX/
  Vulkan games may show a black screen — this is a Windows capture-API
  limitation shared by most non-DXGI recorders. A future version could
  add Desktop Duplication API (DXGI) capture for full game support.
- `keyboard`-based global hotkeys may need Administrator rights to work
  over elevated windows.

## Project layout

```
main.py                  entry point
core/
  config.py               settings persistence (JSON)
  recorder.py             capture loop, smart zoom, click overlay, screenshots
  zoom_engine.py           cursor-follow crop/zoom math
  input_tracker.py         global mouse position + click tracking
  audio_capture.py         mic + WASAPI loopback capture/mix
  muxer.py                 ffmpeg mux of video + audio
  hotkeys.py               global hotkey registration
  region_selector.py       drag-to-select capture area overlay
ui/
  main_window.py           main window
  settings_dialog.py       hotkeys / colours / custom quality
  tray.py                  system tray icon + menu
  styles.py                dark theme stylesheet
```

## Extending it

- Add more quality presets or per-mode FPS caps in `core/config.py`.
- Swap `mss` for a DXGI-based capturer if you need exclusive-fullscreen
  game capture.
- The click-colour mapping and smart-zoom math are isolated in
  `recorder.py` / `zoom_engine.py` if you want to tune the feel.
