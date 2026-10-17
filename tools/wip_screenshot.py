"""Blender UI screenshot for the WIP image: the Scripting workspace with the stunt
simulation in the text editor and the viewport on the kickflip shot. Run with the interface (not -b):

    blender output/stunt_demo_003.blend --python tools/wip_screenshot.py
"""
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission" / "wip_blender.png"
SCRIPT = ROOT / "scripts" / "stimeline.py"
FRAME = 290
LINE = 225         # the altitude controller after the kickflip


def setup():
    win = bpy.context.window_manager.windows[0]
    win.workspace = bpy.data.workspaces["Scripting"]
    return None


def arrange():
    win = bpy.context.window_manager.windows[0]
    scr = win.screen
    sc = bpy.data.scenes["Stunt"]
    win.scene = sc
    sc.frame_set(FRAME)
    txt = bpy.data.texts.load(str(SCRIPT))
    car = bpy.data.objects["car_body"]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    car.select_set(True)
    bpy.context.view_layer.objects.active = car
    for a in scr.areas:
        s = a.spaces.active
        if a.type == "TEXT_EDITOR":
            s.text = txt
            s.show_line_numbers = True
            s.show_syntax_highlight = True
            s.top = LINE - 4
            txt.current_line_index = LINE
        elif a.type == "VIEW_3D":
            s.region_3d.view_perspective = "CAMERA"
            s.shading.type = "RENDERED"
            s.overlay.show_overlays = False
            s.show_region_ui = False
            s.show_region_toolbar = False
            for r in a.regions:
                if r.type == "WINDOW":
                    with bpy.context.temp_override(window=win, screen=scr, area=a, region=r):
                        bpy.ops.view3d.view_center_camera()
        elif a.type == "CONSOLE":
            for r in a.regions:
                if r.type == "WINDOW":
                    with bpy.context.temp_override(window=win, screen=scr, area=a, region=r):
                        bpy.ops.console.insert(text=f"import sys; sys.path.insert(0, r'{SCRIPT.parent}'); "
                                                    "import stimeline; stimeline.Sim().summary()")
                        bpy.ops.console.execute()
    return None


def shoot():
    win = bpy.context.window_manager.windows[0]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with bpy.context.temp_override(window=win, screen=win.screen):
        bpy.ops.screen.screenshot(filepath=str(OUT))
    print(f"[wip] {OUT}")
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(setup, first_interval=2.0)
bpy.app.timers.register(arrange, first_interval=4.0)
bpy.app.timers.register(shoot, first_interval=16.0)
