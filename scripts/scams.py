"""Five shots plus the establishing wide. One camera object per shot, bound to timeline markers,
so a cut never smears motion blur across two set-ups."""
import math

import bpy
from mathutils import Vector

import sbl
import stimeline as T
from sconfig import FPS, N, END_CARD

# name, start s, end s, lens mm, f-stop, rig
SHOTS = [
    ("S0_establish", 0.0, 4.0, 24, 8.0, "establish"),
    ("S1_track", 4.0, 9.8, 26, 5.6, "track"),
    ("S2_profile", 9.8, 13.4, 32, 8.0, "profile"),
    ("S3_front_low", 13.4, 19.2, 24, 2.8, "front_low"),
    ("S4_landing", 19.2, 22.8, 45, 2.8, "landing"),
    ("S5_launch", 22.8, END_CARD, 32, 8.0, "launch"),
]


def lerp(a, b, u):
    return a + (b - a) * u


def vlerp(a, b, u):
    return Vector(a).lerp(Vector(b), u)


def shake(t, amp, seed=0.0):
    fs = (1.7, 2.9, 4.3, 7.1)
    return Vector((sum(math.sin(t * f * 2.1 + seed + i) for i, f in enumerate(fs)),
                   sum(math.sin(t * f * 1.7 + seed * 2 + i * 1.3) for i, f in enumerate(fs)),
                   sum(math.sin(t * f * 1.9 + seed * 3 + i * 0.7) for i, f in enumerate(fs)))) * (amp / 4)


class Cams:
    def __init__(self, sim, scene):
        self.sim = sim
        self.scene = scene
        self.c = sbl.coll("Cameras")
        self.cams = []

    def car_center(self, t):
        s = self.sim.at(max(t, 0))
        from svfx import Pose
        return Pose(s).point((0, 0, 0.55))

    def rig(self, kind, t, t0, t1):
        u = (t - t0) / (t1 - t0)
        car = self.car_center(t)
        if kind == "establish":
            loc = vlerp((-50.0, -15.5, 2.3), (-47.8, -14.6, 2.05), T.smooth(u))
            aim = vlerp((-26.0, 9.0, 4.2), (-25.0, 8.0, 3.6), T.smooth(u))
            return loc, aim, 0.0
        if kind == "track":
            # ground-level tracking: the dolly follows the car, then brakes and tilts up the pipe
            cx = min(car.x - 3.5, -9.5) if t > T.T_GO else car.x - 3.5
            loc = Vector((cx, -13.0, 0.75)) + shake(t, 0.018, 1.0)
            aim = car.copy()
            return loc, aim, 0.0
        if kind == "profile":
            loc = vlerp((-11.0, -34.0, 6.8), (-13.5, -33.2, 6.2), T.smooth(u))
            aim = car * 0.55 + Vector((-9.0, 0.0, 10.0)) * 0.45
            return loc, aim, 0.0
        if kind == "front_low":
            loc = vlerp((-33.0, -5.2, 1.0), (-30.5, -4.2, 0.9), T.smooth(u)) + shake(t, 0.01, 4.0)
            aim = Vector((-17.8, 0.0, 2.6)) * 0.6 + car * 0.4
            return loc, aim, 0.0
        if kind == "landing":
            loc = vlerp((-20.2, -10.8, 2.1), (-19.6, -10.2, 1.3), T.smooth(u))
            aim = Vector((car.x, car.y, car.z * 0.9 + 0.1))
            return loc, aim, 0.0
        if kind == "launch":
            k = max(0.0, t - T.T_LAUNCH)
            jolt = shake(t * 3, 0.045 * math.exp(-k / 0.35), 7.0) if t > T.T_LAUNCH else Vector()
            loc = Vector((-21.5, -13.2, 0.75)) + jolt
            aim = Vector((-22.0, 0.0, 1.25))
            return loc, aim, 0.0
        raise ValueError(kind)

    def build(self):
        sc = self.scene
        frames = list(range(0, N + 2))
        for name, t0, t1, lens, fstop, kind in SHOTS:
            cd = bpy.data.cameras.new(name)
            cd.lens = lens
            cd.sensor_width = 36.0
            cd.clip_start = 0.1
            cd.clip_end = 600.0
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            cam = bpy.data.objects.new(name, cd)
            sbl.link(cam, self.c)
            cam.rotation_mode = "QUATERNION"
            f0 = int(round(t0 * FPS)) + 1
            f1 = int(round(t1 * FPS))
            fr = [f for f in frames if f0 - 1 <= f <= f1 + 1]
            locs, rots, focus = [], [], []
            prev_aim = None
            for f in fr:
                t = (f - 1) / FPS
                loc, aim, roll = self.rig(kind, min(max(t, t0), t1), t0, t1)
                # critically damped aim so the operator lags a little behind fast moves
                if prev_aim is None:
                    sm = aim
                else:
                    sm = prev_aim.lerp(aim, 0.35 if kind in ("track", "profile") else 0.6)
                prev_aim = sm
                d = sm - loc
                q = d.to_track_quat("-Z", "Y")
                locs.append(tuple(loc))
                rots.append(tuple(q))
                focus.append((self.car_center(t) - loc).length)
            sbl.bake_vec(cam, "location", fr, locs)
            sbl.bake_vec(cam, "rotation_quaternion", fr, rots)
            sbl.bake(cd, "dof.focus_distance", fr, focus)
            m = sc.timeline_markers.new(name, frame=f0)
            m.camera = cam
            self.cams.append(cam)
        sc.camera = self.cams[0]
        # extreme shutter for the launch shot
        sh = [1.0 if (f - 1) / FPS >= SHOTS[5][1] else 0.5 for f in frames]
        sbl.bake(sc, "render.motion_blur_shutter", frames, sh, interp="CONSTANT")
