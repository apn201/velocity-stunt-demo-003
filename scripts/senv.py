"""The arena: tarmac, quarter-pipe with truss and LED edges, uplights, fleet platform, haze."""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Vector

import sbl
import stimeline as T
from sconfig import FPS, N, PAL, SEED

THICK = 0.35          # concrete slab


class Env:
    def __init__(self, mats, car_builder):
        self.m = mats
        self.c = sbl.coll("Arena")
        self.cb = car_builder
        self.lights = []          # (light data, fixture object, switch-on time, energy)
        self.leds = []            # LED objects with an "on" prop
        self.rng = random.Random(SEED * 7 + 1)

    def build(self):
        self.floor()
        self.ramp()
        self.truss()
        self.ramp_leds()
        self.uplights()
        self.fleet()
        self.softboxes()
        self.stage_lights()
        self.haze()
        self.start_line()

    # ------------------------------------------------------------ floor
    def floor(self):
        s = 260.0
        sbl.mesh_obj("tarmac", [(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [(0, 1, 2, 3)], self.c,
                     mats=[self.m.tarmac], smooth=False)

    def start_line(self):
        bm = bmesh.new()
        for i in range(10):
            # chequer strip across the lane at the start line
            for j in range(2):
                if (i + j) % 2 == 0:
                    sbl.box(bm, (T.X_START + 2.6 + 0.2 * j, -2.0 + 0.4 * i + 0.2, 0.002), (0.2, 0.4, 0.004))
        sbl.from_bmesh("start_line", bm, self.c, mats=[self.m.simple("line_paint", (0.7, 0.7, 0.68), rough=0.6)],
                       smooth=False)

    # ------------------------------------------------------------ ramp
    def _stations(self):
        """(x, z, nx, nz, u) along the driving surface; n points into the slab"""
        st = []
        # kicker plate on the floor
        for i in range(7):
            x = -3.0 + 0.5 * i
            st.append((x, 0.0, 0.0, -1.0, x + 3.0))
        n_arc = 120
        for i in range(1, n_arc + 1):
            th = math.pi * i / n_arc
            x, z = T.R * math.sin(th), T.R * (1 - math.cos(th))
            st.append((x, z, math.sin(th), -math.cos(th), 3.0 + T.R * th))
        for i in range(1, 11):
            d = T.ROOF_L * i / 10
            st.append((-d, 2 * T.R, 0.0, 1.0, 3.0 + T.R * math.pi + d))
        return st

    def ramp(self):
        st = self._stations()
        hw = T.RAMP_W / 2
        verts, faces, uvs, mi = [], [], [], []
        k = len(st)
        ys = [-hw, -hw / 2, 0.0, hw / 2, hw]
        ny = len(ys)
        # driving surface (0..k*ny), back surface (k*ny..2k*ny)
        for x, z, nx, nz, u in st:
            plate = 0.006 if x <= 0 and z == 0 else None
            for y in ys:
                zz = z + (plate if plate is not None else 0.0)
                verts.append((x, y, zz))
                uvs.append((u, y))
        for x, z, nx, nz, u in st:
            t = 0.0 if (x <= 0 and z == 0) else THICK
            for y in ys:
                verts.append((x + nx * t, y, z + nz * t if not (x <= 0 and z == 0) else -0.01))
                uvs.append((u, y))
        back = k * ny
        for i in range(k - 1):
            for j in range(ny - 1):
                a, b = i * ny + j, i * ny + j + 1
                c, d = (i + 1) * ny + j + 1, (i + 1) * ny + j
                faces.append((a, b, c, d))
                mi.append(0)
                faces.append((back + d, back + c, back + b, back + a))
                mi.append(1)
        # side faces (the curved profile the LEDs outline)
        for i in range(k - 1):
            for j, flip in ((0, False), (ny - 1, True)):
                a, b = i * ny + j, (i + 1) * ny + j
                c, d = back + (i + 1) * ny + j, back + i * ny + j
                faces.append((a, b, c, d) if not flip else (d, c, b, a))
                mi.append(1)
        # end face at the lip
        i = k - 1
        for j in range(ny - 1):
            a, b = i * ny + j, i * ny + j + 1
            faces.append((a, b, back + i * ny + j + 1, back + i * ny + j)[::-1])
            mi.append(1)
        ob = sbl.mesh_obj("ramp", verts, faces, self.c, mats=[self.m.concrete, self.m.ramp_edge], mat_idx=mi,
                          uvs=uvs, smooth=True)
        bev = ob.modifiers.new("edges", "BEVEL")
        bev.width = 0.02
        bev.segments = 2
        bev.limit_method = "ANGLE"
        bev.angle_limit = math.radians(50)
        self.ramp_obj = ob

    def ramp_leds(self):
        """continuous red strips along both side profiles, inner and outer edge"""
        st = self._stations()
        hw = T.RAMP_W / 2 + 0.03
        for side in (-1, 1):
            for off, name in ((0.045, "inner"), (THICK - 0.045, "outer")):
                pts = []
                for x, z, nx, nz, u in st:
                    if x <= 0 and z == 0:
                        continue
                    pts.append((x + nx * off, side * hw, z + nz * off))
                ob = sbl.curve_obj(f"led_ramp_{name}_{'L' if side > 0 else 'R'}", pts, self.c, bevel=0.022,
                                   mat=self.m.led)
                ob["on"] = 0.0
                self.leds.append(ob)
        # LED strips along the floor at the foot of the ramp sides
        for side in (-1, 1):
            ob = sbl.curve_obj(f"led_foot_{side}", [(-3.0, side * hw, 0.03), (0.0, side * hw, 0.03)], self.c,
                               bevel=0.02, mat=self.m.led)
            ob["on"] = 0.0
            self.leds.append(ob)

    # ------------------------------------------------------------ truss
    def truss(self):
        bm = bmesh.new()
        R, T_ = T.R, THICK
        xc = R + 3.2
        top = 2 * R + T_ + 1.6
        hw = T.RAMP_W / 2 - 0.25
        planes = (-hw, 0.0, hw)
        rr = 0.085
        # columns
        for y in planes:
            sbl.tube(bm, (xc, y, 0), (xc, y, top), 0.13, 12)
            sbl.tube(bm, (xc - 1.6, y, 0), (xc - 1.6, y, R * 0.9), 0.11, 12)
        # ribs from the back of the slab to the columns, with diagonals between them
        prev = None
        for k in range(1, 13):
            th = math.pi * k / 13
            ox, oz = (R + T_) * math.sin(th), R - (R + T_) * math.cos(th)
            for y in planes:
                sbl.tube(bm, (ox, y, oz), (xc, y, oz), rr, 10)
                if prev is not None:
                    px, pz = prev
                    sbl.tube(bm, (ox, y, oz), (xc, y, pz), 0.055, 8)
                    sbl.tube(bm, (ox, y, oz), (px, y, pz), 0.06, 8)
            # cross ties between the planes
            sbl.tube(bm, (xc, -hw, oz), (xc, hw, oz), 0.06, 8)
            sbl.tube(bm, (ox, -hw, oz), (ox, hw, oz), 0.06, 8)
            if k % 2 == 0:
                sbl.tube(bm, (ox, -hw, oz), (ox, 0, prev[1] if prev else oz), 0.045, 8)
                sbl.tube(bm, (ox, hw, oz), (ox, 0, prev[1] if prev else oz), 0.045, 8)
            prev = (ox, oz)
        # top chords over the inverted roof, posts and diagonals down to the slab
        zt = 2 * R + T_
        for y in planes:
            sbl.tube(bm, (-T.ROOF_L + 0.2, y, top), (xc, y, top), 0.11, 12)
            xs = [-T.ROOF_L + 0.2 + i * (T.ROOF_L + xc - 0.2) / 8 for i in range(9)]
            for i, x in enumerate(xs):
                xa = min(x, R * 0.98)
                if x <= 0:
                    zs = zt
                else:
                    th = math.asin(min(1.0, x / (R + T_)))
                    zs = R + (R + T_) * math.cos(th)
                if x < xc - 0.3:
                    sbl.tube(bm, (x, y, zs), (x, y, top), 0.07, 8)
                if i > 0 and x < xc:
                    sbl.tube(bm, (xs[i - 1], y, top), (x, y, zs), 0.05, 8)
        for i in range(9):
            x = -T.ROOF_L + 0.2 + i * (T.ROOF_L + xc - 0.2) / 8
            sbl.tube(bm, (x, -hw, top), (x, hw, top), 0.06, 8)
        # footings
        bmf = bmesh.new()
        for y in planes:
            sbl.box(bmf, (xc, y, 0.15), (0.9, 0.9, 0.3))
            sbl.box(bmf, (xc - 1.6, y, 0.12), (0.7, 0.7, 0.24))
        sbl.from_bmesh("truss", bm, self.c, mats=[self.m.steel], smooth=True)
        sbl.from_bmesh("footings", bmf, self.c, mats=[self.m.footing], smooth=False)

    # ------------------------------------------------------------ uplights
    def uplights(self):
        """two rows on the floor, aimed up at 45 degrees over the stage; they switch on in sequence"""
        xs = [-62 + 7.5 * i for i in range(11)]
        k = 0
        for row, y0 in ((1, 21.0), (-1, -21.0)):
            for i, x in enumerate(xs):
                d = Vector((0.0, -row * 1.0, 1.0)).normalized()
                rot = d.to_track_quat("-Z", "Y").to_euler()
                ld = bpy.data.lights.new(f"uplight_{k}", "SPOT")
                ld.energy = 0.0
                ld.color = PAL["cold"]
                ld.spot_size = math.radians(16)
                ld.spot_blend = 0.25
                ld.shadow_soft_size = 0.12
                lo = bpy.data.objects.new(f"uplight_{k}", ld)
                lo.location = (x, y0, 0.55)
                lo.rotation_euler = rot
                sbl.link(lo, self.c)
                # fixture: a housing tilted with the beam and an emissive lens
                bm = bmesh.new()
                sbl.box(bm, (0, 0, 0.0), (0.5, 0.5, 0.42))
                fx = sbl.from_bmesh(f"fixture_{k}", bm, self.c, mats=[self.m.fixture], smooth=False)
                fx.location = (x, y0 + row * 0.12, 0.38)
                fx.rotation_euler = rot
                bm = bmesh.new()
                bmesh.ops.create_circle(bm, cap_ends=True, radius=0.2, segments=24)
                lens = sbl.from_bmesh(f"lens_{k}", bm, self.c, mats=[self.m.lens], smooth=False)
                lens.parent = fx
                lens.location = (0, 0, -0.215)
                lens.rotation_euler = (math.pi, 0, 0)
                lens["on"] = 0.0
                bm = bmesh.new()
                sbl.box(bm, (0, 0, 0.1), (0.8, 0.5, 0.2))
                sbl.from_bmesh(f"fixture_base_{k}", bm, self.c, mats=[self.m.fixture], smooth=False).location = (x, y0 + row * 0.1, 0.0)
                t_on = 0.35 + 0.11 * i + (0.05 if row < 0 else 0.0)
                self.lights.append((ld, lens, t_on, 9000.0))
                k += 1

    # ------------------------------------------------------------ fleet
    def fleet(self):
        """static lineup on a low red-edged platform behind the stage"""
        x0, x1, y0, y1, h = -60.0, -30.0, 11.5, 17.5, 0.32
        bm = bmesh.new()
        sbl.box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, h / 2), (x1 - x0, y1 - y0, h))
        sbl.from_bmesh("platform", bm, self.c, mats=[self.m.platform], smooth=False)
        for pts, nm in (([(x0, y0 - 0.02, h - 0.03), (x1, y0 - 0.02, h - 0.03)], "front"),
                        ([(x1 + 0.02, y0, h - 0.03), (x1 + 0.02, y1, h - 0.03)], "end"),
                        ([(x0 - 0.02, y0, h - 0.03), (x0 - 0.02, y1, h - 0.03)], "end2")):
            ob = sbl.curve_obj(f"led_platform_{nm}", pts, self.c, bevel=0.018, mat=self.m.led)
            ob["on"] = 0.0
            self.leds.append(ob)
        lineup = [("sedan", -55.5), ("crossover", -49.5), ("semi", -42.0), ("wedge", -34.0)]
        for kind, x in lineup:
            root = sbl.empty(f"fleet_{kind}", self.c, loc=(x, (y0 + y1) / 2 - 0.2, h))
            root.rotation_euler = (0, 0, math.radians(-90 + 28))
            self.cb.fleet_vehicle(kind, root, self.c)

    # ------------------------------------------------------------ studio cards
    def softboxes(self):
        """large emitters seen only in reflections, so the paint carries long highlights over a black void"""
        cards = [((-14, -6, 22), (34, 3.2), (math.radians(14), 0, 0)),
                 ((-14, 9, 22), (34, 2.0), (math.radians(-18), 0, 0)),
                 ((8, -2, 26), (6, 14), (0, math.radians(-25), 0))]
        for i, (loc, (w, h), rot) in enumerate(cards):
            ob = sbl.mesh_obj(f"softbox_{i}", [(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)],
                              [(3, 2, 1, 0)], self.c, mats=[self.m.softbox], smooth=False)
            ob.location = loc
            ob.rotation_euler = rot
            ob.visible_camera = False
            ob.visible_diffuse = False
            ob.visible_volume_scatter = False
            ob.visible_shadow = False

    def stage_lights(self):
        """overhead rig over the track and a backlight that makes the vapour glow"""
        rig = [((x, -3.0, 19.0), (5.0, 5.0), 2200.0) for x in (-44.0, -30.0, -17.0, -4.0)]
        for i, (loc, (sx, sy), e) in enumerate(rig):
            ld = bpy.data.lights.new(f"stage_key_{i}", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = sx, sy
            ld.energy = e
            ld.color = PAL["cold"]
            ld.spread = math.radians(32)
            lo = bpy.data.objects.new(f"stage_key_{i}", ld)
            lo.location = loc
            sbl.link(lo, self.c)
            self.lights.append((ld, None, 0.9 + 0.25 * i, e))
        for i, x in enumerate((-30.0, -8.0)):
            ld = bpy.data.lights.new(f"backlight_{i}", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = 12.0, 3.0
            ld.energy = 3500.0
            ld.color = PAL["cold"]
            ld.spread = math.radians(70)
            lo = bpy.data.objects.new(f"backlight_{i}", ld)
            lo.location = (x, 26.0, 9.0)
            lo.rotation_euler = Vector((0, -1.0, -0.25)).to_track_quat("-Z", "Y").to_euler()
            sbl.link(lo, self.c)
            self.lights.append((ld, None, 1.4 + 0.2 * i, 3500.0))

    # ------------------------------------------------------------ haze
    def haze(self):
        bm = bmesh.new()
        sbl.box(bm, (-50, -12, 8.75), (170, 66, 17.5))
        ob = sbl.from_bmesh("haze", bm, self.c, mats=[self.m.fog], smooth=False)
        ob["haze"] = 0.0011
        ob["ground"] = 0.035
        self.haze_obj = ob

    # ------------------------------------------------------------ boot sequence
    def animate(self):
        frames = list(range(0, N + 2))
        for ld, lens, t_on, energy in self.lights:
            vals_e, vals_l = [], []
            for f in frames:
                t = (f - 1) / FPS
                u = (t - t_on) / 0.12
                # filament-style: a quick overshoot then settle
                s = 0.0 if u < 0 else min(1.0, u) * (1.0 + 0.25 * math.exp(-max(0, u - 1) * 3))
                vals_e.append(energy * s)
                vals_l.append(s)
            sbl.bake(ld, "energy", frames, vals_e)
            if lens is not None:
                sbl.bake(lens, '["on"]', frames, vals_l)
        # LED strips flicker on together after the lights
        for i, ob in enumerate(self.leds):
            vals = []
            for f in frames:
                t = (f - 1) / FPS
                u = t - 1.75 - 0.03 * i
                if u < 0:
                    v = 0.0
                elif u < 0.35:
                    v = 1.0 if int(u * 40 + i) % 3 else 0.15
                else:
                    v = 1.0
                vals.append(v)
            sbl.bake(ob, '["on"]', frames, vals, interp="CONSTANT")
