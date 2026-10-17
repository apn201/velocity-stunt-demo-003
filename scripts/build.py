"""VELOCITY // STUNT DEMO 003: build the whole film from an empty scene, then render.

    blender -b --python scripts/build.py -- [--profile preview|final|cycles|cycles_preview]
            [--layer beauty|hud|both] [--stills 60,200] [--start N --end M] [--validate]
            [--save-blend path] [--no-render]

Beauty (photoreal, motion blur, volumes) and HUD (flat, transparent) are separate
scenes rendered to separate PNG sequences; sencode.py stacks them with the audio.
"""
import argparse
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import bpy  # noqa: E402

import saudio  # noqa: E402
import sbl  # noqa: E402
import stimeline as T  # noqa: E402
from sconfig import END_CARD, FPS, N, OUT, PROFILES, RES  # noqa: E402
from scams import Cams  # noqa: E402
from scar import Cars  # noqa: E402
from senv import Env  # noqa: E402
from shud import Hud  # noqa: E402
from smat import Mats  # noqa: E402
from svfx import Vfx  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--profile", default="preview", choices=sorted(PROFILES))
ap.add_argument("--layer", default="both", choices=("beauty", "hud", "both"))
ap.add_argument("--stills", default="")
ap.add_argument("--start", type=int, default=1)
ap.add_argument("--end", type=int, default=N)
ap.add_argument("--validate", action="store_true")
ap.add_argument("--save-blend", default="")
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--no-audio", action="store_true")
args = ap.parse_args(argv)

LAST_BEAUTY = int(END_CARD * FPS)          # frames after this are the end card (HUD over black)


def bake_car(cars, sim):
    frames = list(range(0, N + 2))
    ss = [sim.frame(max(f, 1)) for f in frames]
    locs = [s["pos"] for s in ss]
    qs = []
    for s in ss:
        q = s["q"]
        if qs and sum(a * b for a, b in zip(q, qs[-1])) < 0:
            q = tuple(-c for c in q)
        qs.append(q)
    n = sbl.bake_vec(cars.root, "location", frames, locs)
    n += sbl.bake_vec(cars.root, "rotation_quaternion", frames, qs)
    n += sbl.bake_vec(cars.body, "location", frames, [(0, 0, s["susp"]) for s in ss])
    n += sbl.bake_vec(cars.body, "rotation_euler", frames, [(0, s["pitch_s"], 0) for s in ss])
    for spin, left in cars.wheels:
        n += sbl.bake_vec(spin, "rotation_euler", frames, [(0, s["wheel"] * (1 if left else -1), 0) for s in ss])
    on = [T.smooth(((f - 1) / FPS - 2.7) / 0.15) for f in frames]
    for ld in cars.headlights:
        n += sbl.bake(ld, "energy", frames, [220.0 * v for v in on])
    n += sbl.bake(cars.tail_glow, "energy", frames, [6.0 * v for v in on])
    return n


def world(scene):
    w = bpy.data.worlds.new("void")
    n = sbl.Nodes(w.node_tree)
    bg = n.node("ShaderNodeBackground", {"Color": (0, 0, 0, 1), "Strength": 0.0})
    o = n.node("ShaderNodeOutputWorld")
    n.set(o.inputs["Surface"], bg)
    scene.world = w


def setup_render(scene, prof):
    p = PROFILES[prof]
    r = scene.render
    r.resolution_x, r.resolution_y = RES
    r.resolution_percentage = p["scale"]
    r.fps = FPS
    r.use_motion_blur = True
    r.motion_blur_shutter = 0.5
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    vs = scene.view_settings
    vs.view_transform = "AgX"
    looks = [i.identifier for i in vs.bl_rna.properties["look"].enum_items]
    for want in ("AgX - Punchy", "Punchy", "AgX - High Contrast"):
        if want in looks:
            vs.look = want
            break
    vs.exposure = 0.0
    if p["engine"] == "CYCLES":
        r.engine = "CYCLES"
        cy = scene.cycles
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dev
                prefs.get_devices()
                ok = False
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                    ok = ok or d.use
                if ok:
                    break
            except TypeError:
                continue
        cy.device = "GPU"
        cy.samples = p["samples"]
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = 0.02
        cy.use_denoising = True
        cy.denoiser = "OPENIMAGEDENOISE"
        cy.denoising_use_gpu = True
        cy.max_bounces = 6
        cy.diffuse_bounces = 2
        cy.glossy_bounces = 3
        cy.transmission_bounces = 2
        cy.volume_bounces = 1
        cy.transparent_max_bounces = 8
        cy.volume_step_rate = 1.0
        cy.volume_max_steps = 256
        cy.sample_clamp_indirect = 8.0
        cy.use_light_tree = True
        cy.seed = 3
        cy.use_animated_seed = True
        cy.film_exposure = 1.0
    else:
        r.engine = "BLENDER_EEVEE"
        ee = scene.eevee
        ee.taa_render_samples = p["samples"]
        ee.use_raytracing = True
        ee.use_shadows = True
        ee.use_volumetric_shadows = True
        ee.volumetric_start = 0.2
        ee.volumetric_end = 160.0
        ee.volumetric_tile_size = "4" if p["scale"] >= 100 else "8"
        ee.volumetric_samples = 96
        ee.volumetric_sample_distribution = 0.85
        ee.volumetric_shadow_samples = 16
        ee.volumetric_light_clamp = 0.0
        ee.motion_blur_steps = 4
        ee.shadow_pool_size = "1024"
        ee.use_fast_gi = True
        ee.fast_gi_method = "GLOBAL_ILLUMINATION"
        try:
            ee.ray_tracing_options.resolution_scale = "1"
            ee.ray_tracing_options.use_denoise = True
        except Exception:
            pass


def render_frames(scene, frames, out, label):
    out.mkdir(parents=True, exist_ok=True)
    times = []
    for f in frames:
        for sc in bpy.data.scenes:          # a second scene renders at the window scene's frame
            sc.frame_set(f)
        scene.render.filepath = str(out / f"{f:04d}.png")
        t = time.time()
        bpy.ops.render.render(write_still=True, scene=scene.name)
        times.append(time.time() - t)
        if len(times) == 1 or f % 24 == 0 or f == frames[-1]:
            print(f"[{label}] frame {f} {times[-1]:.1f} s (avg {sum(times) / len(times):.1f} s)", flush=True)
    if times:
        print(f"[{label}] {len(times)} frames, {sum(times) / 60:.1f} min -> {out}")


def validate(sim, vfx, hud):
    s = sim.summary()
    print("[validate] sim:", {k: round(v, 3) if isinstance(v, float) else v for k, v in s.items()})
    ok = True
    if not (s["t_060"] and s["t_060"] < 1.0):
        print("[validate] FAIL 0-60 mph is not under one second"); ok = False
    if not (15 / 3.281 <= T.Z_HOVER <= 25 / 3.281):
        print("[validate] FAIL hover height outside 15-25 ft"); ok = False
    imgs = [i.name for i in bpy.data.images if i.source not in ("VIEWER", "GENERATED") and i.type != "RENDER_RESULT"]
    if imgs:
        print("[validate] FAIL image files in the scene:", imgs); ok = False
    if bpy.data.texts or any(o.type == "IMAGE" for o in bpy.data.objects if hasattr(o, "type")):
        pass
    print(f"[validate] vfx objects: {vfx.count}")
    print(f"[validate] objects: {len(bpy.data.objects)}, meshes: {len(bpy.data.meshes)}, materials: {len(bpy.data.materials)}")
    for f in (1, 100, 250, 300, 400, 540, 600):
        smp = sim.frame(f)
        print(f"[validate] f{f:3d} t={smp['t']:5.2f} {smp['mode']:6s} z={smp['pos'][2]:5.2f} G={smp['g']:.2f}")
    print("[validate]", "OK" if ok else "FAILED")
    return ok


def main():
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Stunt"
    scene.frame_start, scene.frame_end = 1, N
    scene.render.fps = FPS
    sim = T.Sim()
    print("[build] sim", {k: round(v, 3) if isinstance(v, float) else v for k, v in sim.summary().items()})
    mats = Mats()
    cars = Cars(mats)
    cars.build()
    env = Env(mats, cars)
    env.build()
    env.animate()
    vfx = Vfx(mats, sim, cars)
    vfx.build()
    nk = bake_car(cars, sim)
    cams = Cams(sim, scene)
    cams.build()
    world(scene)
    setup_render(scene, args.profile)
    hud = Hud(sim, mats)
    hud.vfx = vfx
    hud.setup(FPS)
    hud.build()
    hud.sc.render.resolution_percentage = PROFILES[args.profile]["scale"]
    print(f"[build] scene built in {time.time() - t0:.1f} s, car keys {nk}")
    ok = validate(sim, vfx, hud)
    if not args.no_audio:
        d = saudio.write(sim, vfx, cams, env, OUT / "audio" / "stunt_demo_003.wav")
        print(f"[build] audio {d:.1f} s -> {OUT / 'audio'}")
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save_blend).resolve()))
    if args.validate or args.no_render:
        return ok
    prof = PROFILES[args.profile]
    if args.stills:
        frames = [int(x) for x in args.stills.split(",") if x.strip()]
        base = OUT / "stills"
    else:
        frames = list(range(args.start, args.end + 1))
        base = None
    if args.layer in ("beauty", "both"):
        bf = [f for f in frames if f <= LAST_BEAUTY]
        render_frames(scene, bf, (base / "beauty") if base else prof["out"], "beauty")
    if args.layer in ("hud", "both"):
        render_frames(hud.sc, frames, (base / "hud") if base else OUT / "hud", "hud")
    return ok


main()
