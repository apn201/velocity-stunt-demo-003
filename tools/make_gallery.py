"""Submission images: final frames (beauty + HUD) padded to 3:2 for Devpost, and a
16:9 YouTube thumbnail with a title rendered by Blender's own text objects.

    blender -b --python tools/make_gallery.py
"""
import os
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "output"
OUT = ROOT / "submission"
PICKS = [(480, "01_thumbnail_hover"), (205, "02_suction_climb"), (228, "03_inverted_lip"),
         (266, "04_kickflip"), (300, "05_lift_columns"), (360, "06_front_low_hover"),
         (595, "07_launch_blur"), (700, "08_end_card")]
THUMB_FRAME = 480


def load(p):
    im = bpy.data.images.load(str(p))
    im.colorspace_settings.name = "Non-Color"      # copy pixel values as they are
    w, h = im.size
    px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(im)
    return px


def frame(f):
    hud = load(SRC / "hud" / f"{f:04d}.png")
    bp = SRC / "beauty" / f"{f:04d}.png"
    base = load(bp)[..., :3] if bp.exists() else np.zeros(hud.shape[:2] + (3,), np.float32)
    a = hud[..., 3:4]
    return base * (1 - a) + hud[..., :3] * a


def save(rgb, path, quality=92):
    h, w = rgb.shape[:2]
    img = bpy.data.images.new(path.stem, w, h)
    img.colorspace_settings.name = "Non-Color"
    px = np.ones((h, w, 4), np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    img.pixels[:] = px.ravel()
    sc = bpy.context.scene
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = quality
    sc.view_settings.view_transform = "Standard"
    img.save_render(str(path), scene=sc)
    bpy.data.images.remove(img)
    print(f"[gallery] {path.name}")


def title_layer(lines, W=1920, H=1080):
    """render text with Inter on a transparent film; lines: (text, x, y_from_top, size, alpha)"""
    sc = bpy.data.scenes.new("thumb_text")
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    cd = bpy.data.cameras.new("tc")
    cd.type = "ORTHO"
    cd.ortho_scale = W
    cam = bpy.data.objects.new("tc", cd)
    cam.location = (0, 0, 10)
    sc.collection.objects.link(cam)
    sc.camera = cam
    font = bpy.data.fonts.load(os.path.join(os.path.dirname(bpy.app.binary_path),
                                            f"{bpy.app.version[0]}.{bpy.app.version[1]}", "datafiles", "fonts", "Inter.woff2"))
    for i, (txt, x, y, size, col) in enumerate(lines):
        m = bpy.data.materials.new(f"tm{i}")
        nt = m.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*col, 1)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        cu = bpy.data.curves.new(f"t{i}", "FONT")
        cu.body = txt
        cu.font = font
        cu.size = size
        cu.align_y = "TOP"
        cu.materials.append(m)
        ob = bpy.data.objects.new(f"t{i}", cu)
        ob.location = (x - W / 2, H / 2 - y, 0)
        sc.collection.objects.link(ob)
    tmp = OUT / "_title.png"
    sc.render.filepath = str(tmp)
    bpy.ops.render.render(write_still=True, scene=sc.name)
    px = load(tmp)
    tmp.unlink()
    return px


def main():
    OUT.mkdir(exist_ok=True)
    W, H = 1920, 1280
    for f, name in PICKS:
        rgb = frame(f)
        canvas = np.zeros((H, W, 3), np.float32)
        y0 = (H - rgb.shape[0]) // 2
        canvas[y0:y0 + rgb.shape[0]] = rgb
        save(canvas, OUT / f"{name}.jpg")
    # YouTube thumbnail: the beauty pass only, darkened on the left for the title
    rgb = load(SRC / "beauty" / f"{THUMB_FRAME:04d}.png")[..., :3]
    h, w = rgb.shape[:2]
    ramp = np.clip(1.0 - np.linspace(0, 1, w) * 1.6, 0, 1)[None, :, None] * 0.65
    rgb = rgb * (1 - ramp)
    red = (1.0, 0.0, 0.2)
    txt = title_layer([("ONE TEXT PROMPT.", 90, 70, 128, (1, 1, 1)),
                       ("100% AI-written Blender code. No assets.", 96, 238, 50, (1, 1, 1)),
                       ("VELOCITY // STUNT DEMO 003", 96, 960, 34, red)])
    a = txt[::-1][::-1][..., 3:4]
    rgb = rgb * (1 - a) + txt[..., :3] * a
    save(rgb, OUT / "youtube_thumbnail.jpg", quality=94)


main()
