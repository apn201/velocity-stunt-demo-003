"""Cold-gas thruster effects as shader volumes. No simulation cache, no particles.

Plumes ride on the car, one per nozzle, scaled and fed by the simulated thrust.
Bursts leave detached puffs behind in world space; lift thrust near the floor
spawns expanding radial rings of ground fog. Every object's motion is analytic
and baked per frame from the stunt simulation.
"""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Quaternion, Vector

import sbl
import stimeline as T
from sconfig import FPS, N, SEED


def _cone(name, c):
    bm = bmesh.new()
    seg, rings = 24, 12
    vs = []
    for k in range(rings + 1):
        z = k / rings
        r = 0.08 + 0.92 * z
        vs.append([bm.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z))
                   for i in range(seg)])
    for k in range(rings):
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((vs[k][i], vs[k][j], vs[k + 1][j], vs[k + 1][i]))
    bm.faces.new(list(reversed(vs[0])))
    bm.faces.new(vs[-1])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _sphere(name):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _cyl(name):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=1.0, radius2=1.0, depth=1.0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


class Pose:
    """world transforms of body-local points from a simulation sample"""

    def __init__(self, s):
        self.p = Vector(s["pos"])
        self.q = Quaternion(s["q"])
        self.bq = Quaternion((0, 1, 0), s["pitch_s"])
        self.bz = s["susp"]

    def point(self, v):
        return self.p + self.q @ (self.bq @ Vector(v) + Vector((0, 0, self.bz)))

    def dir(self, d):
        return self.q @ (self.bq @ Vector(d))


def smooth_series(raw, attack=0.03, release=0.2):
    """asymmetric one-pole on a 240 Hz grid"""
    out = []
    y = 0.0
    for x in raw:
        tau = attack if x > y else release
        y += (x - y) * (1 - math.exp(-(1 / 240) / tau))
        out.append(y)
    return out


class Vfx:
    def __init__(self, mats, sim, cars):
        self.m = mats
        self.sim = sim
        self.cars = cars
        self.c = sbl.coll("VFX")
        self.rng = random.Random(SEED * 31 + 5)
        self.frames = list(range(0, N + 2))
        self.count = {"plume": 0, "puff": 0, "ring": 0}
        self._signals()

    # ------------------------------------------------------------ thrust per nozzle, smoothed
    def _signals(self):
        sim = self.sim
        n = int((N + 2) / FPS * 240) + 2
        ts = [i / 240 - 1 / FPS for i in range(n)]
        raw = {k: [] for k in self.cars.nozzles}
        for t in ts:
            s = sim.at(max(t, 0.0))
            left, right = sim.side(t)
            for name, nz in self.cars.nozzles.items():
                g = nz["group"]
                if g == "lift":
                    v = min(1.45, s["lift"] * 3.0)
                elif g == "retro":
                    v = s["retro"]
                elif g == "rear":
                    v = min(1.3, s["rear"] * 1.15)
                else:
                    v = left if name.endswith("L") else right
                raw[name].append(v)
        self.ts = ts
        self.sig = {k: smooth_series(v) for k, v in raw.items()}
        self.raw = raw

    def level(self, name, t):
        i = int(round((t + 1 / FPS) * 240))
        i = max(0, min(i, len(self.ts) - 1))
        return self.sig[name][i]

    def raw_level(self, name, t):
        i = int(round((t + 1 / FPS) * 240))
        i = max(0, min(i, len(self.ts) - 1))
        return self.raw[name][i]

    # ------------------------------------------------------------ build
    def build(self):
        self.cone_me = _cone("plume_cone", self.c)
        self.sphere_me = _sphere("puff_sphere")
        self.cyl_me = _cyl("ring_cyl")
        for me in (self.cone_me,):
            me.materials.append(self.m.plume)
        self.sphere_me.materials.append(self.m.puff)
        self.cyl_me.materials.append(self.m.ring)
        self.plumes()
        self.puffs()
        self.rings()

    def plumes(self):
        for k, (name, nz) in enumerate(self.cars.nozzles.items()):
            ob = bpy.data.objects.new(f"plume_{name}", self.cone_me)
            sbl.link(ob, self.c, self.cars.body)
            d = nz["dir"]
            ob.location = nz["pos"] + d * 0.004
            ob.rotation_mode = "QUATERNION"
            ob.rotation_quaternion = d.to_track_quat("Z", "Y")
            ob["thrust"] = 0.0
            ob["flow"] = 0.0
            ob["seed"] = 3.7 * k + 1.3
            vis, sc, th, fl = [], [], [], []
            for f in self.frames:
                t = (f - 1) / FPS
                v = self.level(name, t)
                L = nz["L"] * (0.3 + 0.7 * min(v, 1.0))
                W = nz["W"] * (0.55 + 0.45 * min(v, 1.0))
                vis.append(v > 0.015)
                sc.append((W, W, L))
                th.append(v)
                fl.append(t * 9.0)
            sbl.bake_visibility(ob, self.frames, vis)
            sbl.bake_vec(ob, "scale", self.frames, sc)
            sbl.bake(ob, '["thrust"]', self.frames, th)
            sbl.bake(ob, '["flow"]', self.frames, fl)
            self.count["plume"] += 1

    def _spawn_puff(self, t0, p0, v0, r0, r1, dens, life, drag=0.35, grow=0.6, sink=0.25, rise=0.0):
        k = self.count["puff"]
        ob = bpy.data.objects.new(f"puff_{k:03d}", self.sphere_me)
        sbl.link(ob, self.c)
        ob["dens"] = 0.0
        ob["flow"] = 0.0
        ob["seed"] = self.rng.uniform(0, 100)
        vis, loc, sc, de, fl = [], [], [], [], []
        stretch = Vector((self.rng.uniform(0.8, 1.2), self.rng.uniform(0.8, 1.2), self.rng.uniform(0.6, 0.9)))
        for f in self.frames:
            t = (f - 1) / FPS
            a = t - t0
            alive = 0 <= a <= life
            vis.append(alive)
            a = max(a, 0.0)
            e = 1 - math.exp(-a / drag)
            p = p0 + v0 * (drag * e) + Vector((0, 0, (rise - sink) * a))
            p.z = max(p.z, (r0 + (r1 - r0) * (1 - math.exp(-a / grow))) * 0.35)
            r = r0 + (r1 - r0) * (1 - math.exp(-a / grow))
            loc.append(tuple(p))
            sc.append(tuple(r * s for s in stretch))
            fade = T.smooth(a / 0.05) * math.exp(-a / (life * 0.35)) * (1 - T.smooth((a - life * 0.8) / (life * 0.2)))
            de.append(dens * fade)
            fl.append(a * 1.2)
        sbl.bake_visibility(ob, self.frames, vis)
        sbl.bake_vec(ob, "location", self.frames, loc)
        sbl.bake_vec(ob, "scale", self.frames, sc)
        sbl.bake(ob, '["dens"]', self.frames, de)
        sbl.bake(ob, '["flow"]', self.frames, fl)
        self.count["puff"] += 1

    def puffs(self):
        sim = self.sim
        nzs = self.cars.nozzles
        # side attitude bursts: one cloud per nozzle per burst
        for t0, d, side, amp in sim.side_bursts:
            s = sim.at(t0 + 0.04)
            P = Pose(s)
            for name, nz in nzs.items():
                if nz["group"] != "side" or (name.endswith("L") != (side > 0)):
                    continue
                dw = P.dir(nz["dir"])
                p0 = P.point(nz["pos"]) + dw * 0.5
                v0 = Vector(s["vel"]) * 0.55 + dw * (9.0 * amp)
                self._spawn_puff(t0 + 0.03, p0, v0, 0.25, 1.1 + 0.9 * amp, 0.9 * amp, 2.6, drag=0.3)
        # retro braking in the air: a cloud shed every 0.1 s from each retro nozzle
        t = sim.t_exit
        while t < sim.t_exit + 3.2:
            for name, nz in nzs.items():
                if nz["group"] != "retro":
                    continue
                lv = self.raw_level(name, t)
                if lv < 0.2:
                    continue
                s = sim.at(t)
                P = Pose(s)
                dw = P.dir(nz["dir"])
                p0 = P.point(nz["pos"]) + dw * 2.2
                v0 = Vector(s["vel"]) * 0.35 + dw * 4.0
                self._spawn_puff(t, p0, v0, 0.6, 2.4, 0.35 * lv, 2.4, drag=0.5, grow=0.9)
            t += 0.1
        # launch purge: dense clouds blasted back along the floor
        t = T.T_LAUNCH
        while t < T.T_LAUNCH + 0.62:
            for name, nz in nzs.items():
                if nz["group"] != "rear":
                    continue
                s = sim.at(t)
                P = Pose(s)
                dw = P.dir(nz["dir"])
                p0 = P.point(nz["pos"]) + dw * 1.2
                v0 = dw * 11.0 + Vector((0, self.rng.uniform(-1.5, 1.5), 0.6))
                self._spawn_puff(t, p0, v0, 0.45, 2.6, 0.8, 3.6, drag=0.45, grow=0.8, sink=0.05, rise=0.25)
            t += 0.045
        # lift arrest at altitude: shed clouds under the car
        t = sim.t_roll_end
        while t < sim.t_roll_end + 0.8:
            s = sim.at(t)
            P = Pose(s)
            for name, nz in nzs.items():
                if nz["group"] != "lift":
                    continue
                lv = self.raw_level(name, t)
                dw = P.dir(nz["dir"])
                p0 = P.point(nz["pos"]) + dw * 3.0
                v0 = dw * 7.0 + Vector(s["vel"]) * 0.3
                self._spawn_puff(t, p0, v0, 0.5, 1.8, 0.35 * min(lv, 1.0), 1.8, drag=0.4)
            t += 0.12

    def rings(self):
        """radial ground fog: waves while the lift jets reach the floor, and a pool under the car"""
        sim = self.sim
        t = sim.t_roll_end + 0.2
        t_stop = sim.t_land + 0.25
        while t < t_stop:
            s = sim.at(t)
            alt = s["pos"][2]
            lv = min(1.4, s["lift"] * 3.0)
            reach = math.exp(-max(0.0, alt - 5.0) / 3.0)
            if lv > 0.2 and reach > 0.15:
                self._ring(t, s["pos"][0], s["pos"][1], lv * reach)
            t += 0.42
        self._pool()

    def _ring(self, t0, x, y, strength):
        k = self.count["ring"]
        ob = bpy.data.objects.new(f"ring_{k:03d}", self.cyl_me)
        sbl.link(ob, self.c)
        ob["dens"] = 0.0
        ob["inner"] = 0.55
        ob["flow"] = 0.0
        ob["seed"] = self.rng.uniform(0, 100)
        life = 4.0
        rot = self.rng.uniform(0, 2 * math.pi)
        ob.rotation_euler = (0, 0, rot)
        vis, sc, de, fl, inner = [], [], [], [], []
        for f in self.frames:
            t = (f - 1) / FPS
            a = t - t0
            vis.append(0 <= a <= life)
            a = max(a, 0.0)
            r = 1.2 + 11.0 * (1 - math.exp(-a / 1.7))
            h = 0.4 + 0.9 * (1 - math.exp(-a / 1.4))
            sc.append((r, r, h))
            de.append(0.4 * strength * T.smooth(a / 0.15) * math.exp(-a / 1.3) * (1 - T.smooth((a - life + 1) / 1)))
            fl.append(a * 0.6)
            inner.append(0.62 - 0.25 * (1 - math.exp(-a / 2.5)))
        ob.location = (x, y, -0.02)
        sbl.bake_visibility(ob, self.frames, vis)
        sbl.bake_vec(ob, "scale", self.frames, sc)
        sbl.bake(ob, '["dens"]', self.frames, de)
        sbl.bake(ob, '["flow"]', self.frames, fl)
        sbl.bake(ob, '["inner"]', self.frames, inner)
        self.count["ring"] += 1

    def _pool(self):
        """the churning disc where the four jets hit the floor; follows the car, lingers after landing"""
        ob = bpy.data.objects.new("ground_pool", self.cyl_me)
        sbl.link(ob, self.c)
        ob["dens"] = 0.0
        ob["inner"] = 0.0
        ob["flow"] = 0.0
        ob["seed"] = 42.0
        vis, loc, sc, de, fl = [], [], [], [], []
        acc = 0.0
        for f in self.frames:
            t = (f - 1) / FPS
            s = self.sim.at(max(t, 0))
            alt = s["pos"][2]
            lv = self.level("lift_FL", t)
            reach = math.exp(-max(0.0, alt - 4.0) / 3.0) if s["mode"] != "track" else 0.0
            target = min(1.3, lv) * reach
            acc += (target - acc) * (1 - math.exp(-(1 / FPS) / (0.25 if target > acc else 0.8)))
            vis.append(acc > 0.01)
            loc.append((s["pos"][0], s["pos"][1], -0.02))
            r = 3.2 + 1.2 * acc
            sc.append((r, r, 1.0 + 0.8 * acc))
            de.append(0.9 * acc)
            fl.append(t * 0.9)
        sbl.bake_visibility(ob, self.frames, vis)
        sbl.bake_vec(ob, "location", self.frames, loc)
        sbl.bake_vec(ob, "scale", self.frames, sc)
        sbl.bake(ob, '["dens"]', self.frames, de)
        sbl.bake(ob, '["flow"]', self.frames, fl)
