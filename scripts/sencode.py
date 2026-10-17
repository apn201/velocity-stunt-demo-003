"""Stack the beauty and HUD sequences over black, add the generated audio, encode H.264 with Blender's FFmpeg.

    blender -b --python scripts/sencode.py -- [--beauty output/beauty] [--hud output/hud]
            [--audio output/audio/stunt_demo_003.wav] [--out output/final/velocity_stunt_demo_003.mp4]
"""
import argparse
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--beauty", default=str(ROOT / "output" / "beauty"))
ap.add_argument("--hud", default=str(ROOT / "output" / "hud"))
ap.add_argument("--audio", default=str(ROOT / "output" / "audio" / "stunt_demo_003.wav"))
ap.add_argument("--out", default=str(ROOT / "output" / "final" / "velocity_stunt_demo_003.mp4"))
ap.add_argument("--frames", type=int, default=720)
a = ap.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 24
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
sc.frame_start, sc.frame_end = 1, a.frames
ed = sc.sequence_editor_create()
seqs = ed.strips if hasattr(ed, "strips") else ed.sequences


def image_seq(name, folder, channel):
    files = sorted(Path(folder).resolve().glob("*.png"))
    if not files:
        sys.exit(f"no PNGs in {folder}")
    first = int(files[0].stem)
    st = seqs.new_image(name, str(files[0]), channel, first)
    for f in files[1:]:
        st.elements.append(f.name)
    return st, len(files)


bg = seqs.new_effect("black", "COLOR", 1, frame_start=1, length=a.frames)
bg.color = (0, 0, 0)
beauty, nb = image_seq("beauty", a.beauty, 2)
hud, nh = image_seq("hud", a.hud, 3)
hud.blend_type = "ALPHA_OVER"
audio = Path(a.audio).resolve()
if audio.exists():
    seqs.new_sound("audio", str(audio), 4, 1)
r = sc.render
if hasattr(r.image_settings, "media_type"):
    r.image_settings.media_type = "VIDEO"
r.image_settings.file_format = "FFMPEG"
r.ffmpeg.format = "MPEG4"
r.ffmpeg.codec = "H264"
r.ffmpeg.constant_rate_factor = "HIGH"
r.ffmpeg.ffmpeg_preset = "GOOD"
r.ffmpeg.gopsize = 24
r.ffmpeg.audio_codec = "AAC" if audio.exists() else "NONE"
r.ffmpeg.audio_channels = "STEREO"
r.ffmpeg.audio_mixrate = 48000
r.ffmpeg.audio_bitrate = 192
out = Path(a.out).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
r.filepath = str(out)
bpy.ops.render.render(animation=True)
print(f"[encode] beauty {nb} + hud {nh} frames, audio {'yes' if audio.exists() else 'no'} -> {out}")
