"""
Generates assets/icon.ico (+ icon.png) used by the app window, system tray,
PyInstaller exe, and the Inno Setup installer.

Run once before building:   python tools/generate_icon.py

Icon assets are generated rather than committed as binary files so the
whole project stays diffable/reviewable as plain text in git.
"""
import os

from PIL import Image, ImageDraw

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")


def build_icon():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=48, fill=(20, 22, 28, 255))
    d.rounded_rectangle(
        [44, 60, size - 44, size - 96], radius=18,
        outline=(91, 140, 255, 255), width=10, fill=(12, 13, 18, 255),
    )
    d.rectangle([size // 2 - 10, size - 96, size // 2 + 10, size - 70],
                fill=(91, 140, 255, 255))
    d.rectangle([size // 2 - 34, size - 74, size // 2 + 34, size - 58],
                fill=(91, 140, 255, 255))
    d.ellipse([size // 2 - 26, 94, size // 2 + 26, 146], fill=(229, 72, 77, 255))
    return img


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    img = build_icon()
    sizes = [16, 24, 32, 48, 64, 128, 256]
    img.save(os.path.join(ASSETS_DIR, "icon.ico"), format="ICO",
              sizes=[(s, s) for s in sizes])
    img.save(os.path.join(ASSETS_DIR, "icon.png"))
    print(f"Wrote icon.ico and icon.png to {os.path.abspath(ASSETS_DIR)}")


if __name__ == "__main__":
    main()
