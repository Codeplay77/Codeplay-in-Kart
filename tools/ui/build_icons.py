"""Package Godot's rasterized icon as a Windows multi-resolution ICO.
Requires Pillow. Run rasterize_icon.gd first (see docs/UI_ART.md).
"""
from pathlib import Path
from PIL import Image

folder = Path(__file__).resolve().parents[2] / "assets/ui"
with Image.open(folder / "app_icon.png") as icon:
    icon.save(folder / "app_icon.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
print("Windows icon generated.")
