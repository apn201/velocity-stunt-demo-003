"""Stack HUD stills over beauty stills and tile them into one contact sheet.

    blender -b --python tools/contact.py -- [--dir output/stills] [--cols 3] [--out sheet.png]
"""
import argparse
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(Path(__file__).resolve().parents[1] / "output" / "stills"))
ap.add_argument("--cols", type=int, default=3)
ap.add_argument("--out", default="")
ap.add_argument("--frames", default="")
ap.add_argument("--no-hud", action="store_true")
a = ap.parse_args(argv)
d = Path(a.dir).resolve()


def load(p):
    im = bpy.data.images.load(str(p))
    w, h = im.size
    px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(im)
    return px


hud = sorted((d / "beauty").glob("*.png"))
if a.frames:
    keep = {int(x) for x in a.frames.split(",")}
    hud = [p for p in hud if int(p.stem) in keep]
tiles = []
for hp in hud:
    bp = hp
    b = load(bp)
    h = load(d / "hud" / hp.name) if (d / "hud" / hp.name).exists() and not a.no_hud else np.zeros_like(b)
    if b.shape != h.shape:
        # scale HUD to beauty size by nearest sampling
        ys = (np.arange(b.shape[0]) * h.shape[0] / b.shape[0]).astype(int)
        xs = (np.arange(b.shape[1]) * h.shape[1] / b.shape[1]).astype(int)
        h = h[ys][:, xs]
    al = h[..., 3:4]
    tiles.append(b[..., :3] * (1 - al) + h[..., :3] * al)
H, W = tiles[0].shape[:2]
cols = a.cols
rows = (len(tiles) + cols - 1) // cols
sheet = np.zeros((rows * H, cols * W, 4), dtype=np.float32)
sheet[..., 3] = 1
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    y0 = (rows - 1 - r) * H
    sheet[y0:y0 + H, c * W:(c + 1) * W, :3] = t
out = Path(a.out).resolve() if a.out else d / "contact.png"
img = bpy.data.images.new("sheet", cols * W, rows * H, alpha=False)
img.pixels[:] = sheet.ravel()
img.filepath_raw = str(out)
img.file_format = "PNG"
img.save()
print(f"[contact] {len(tiles)} tiles -> {out}")
