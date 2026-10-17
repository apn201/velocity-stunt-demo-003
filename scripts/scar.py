"""Vehicles from lofted cross-sections: the demo car (with nozzles and lights) and the static fleet.

A body is a list of stations along X; each station is a half cross-section from the
bottom centre round the side to the top centre. Stations are joined into a closed
shell, mirrored in Y, subdivided with creased character lines, and the wheel arches
are cut with boolean cylinders. Materials are assigned per face from the row a face
sits in, so glass, paint and carbon come out of the same loft.
"""
import math

import bmesh
import bpy
from mathutils import Vector

import sbl
import stimeline as T

WHEEL_X = T.WB / 2
WHEEL_Y = T.TRACK / 2
WR = T.WHEEL_R

# demo car stations: x, underbody, beltline, roof, half width, roof-edge half width
CAR = [
    (-2.25, 0.25, 0.80, 0.835, 0.925, 0.84),
    (-2.12, 0.19, 0.82, 0.875, 0.965, 0.885),
    (-1.72, 0.15, 0.82, 0.915, 0.985, 0.895),
    (-1.20, 0.14, 0.80, 0.965, 0.99, 0.83),
    (-0.80, 0.14, 0.775, 1.075, 0.99, 0.665),
    (-0.30, 0.14, 0.745, 1.12, 0.99, 0.635),
    (0.30, 0.14, 0.715, 1.055, 0.99, 0.64),
    (0.90, 0.14, 0.675, 0.86, 0.985, 0.71),
    (1.40, 0.14, 0.625, 0.72, 0.98, 0.86),
    (1.90, 0.13, 0.555, 0.60, 0.96, 0.885),
    (2.15, 0.15, 0.48, 0.515, 0.925, 0.845),
    (2.25, 0.20, 0.42, 0.445, 0.865, 0.78),
]
CABIN = (4, 7)            # station range that is glass above the shoulder

# nozzles in body coordinates: name, position, direction, group, plume length, plume radius
NOZZLES = []
for sy in (1, -1):
    s = "L" if sy > 0 else "R"
    NOZZLES += [
        (f"lift_F{s}", (0.78, 0.52 * sy, 0.13), (0, 0, -1), "lift", 7.5, 1.35),
        (f"lift_R{s}", (-0.78, 0.52 * sy, 0.13), (0, 0, -1), "lift", 7.5, 1.35),
        (f"retro_{s}", (2.02, 0.78 * sy, 0.30), (0.85, 0.53 * sy, 0.0), "retro", 3.8, 1.15),
        (f"rear_{s}", (-2.255, 0.42 * sy, 0.32), (-1, 0, 0), "rear", 5.5, 1.35),
        (f"side_F{s}", (1.93, 0.965 * sy, 0.40), (0, sy, 0.12), "side", 2.6, 0.85),
        (f"side_R{s}", (-1.93, 0.975 * sy, 0.45), (0, sy, 0.12), "side", 2.6, 0.85),
    ]


def half_ring(zb, zbelt, zroof, w, wr):
    return [(0.0, zb), (w - 0.12, zb), (w - 0.012, zb + 0.07), (w, zb + 0.19), (w, zbelt),
            (w - 0.05, zbelt + 0.025), (wr, zroof - 0.035), (wr * 0.55, zroof), (0.0, zroof + 0.004)]


def loft(name, stations, c, parent, mats, face_mat, crease_rows, crease_end=1.0, crease_stations=(),
         subsurf=3):
    """stations: [(x, [(y, z) half ring])]; face_mat(i_station, row, z) -> material index"""
    bm = bmesh.new()
    M = len(stations[0][1])
    rings = []
    for x, half in stations:
        pos = [bm.verts.new((x, y, z)) for y, z in half]
        neg = [bm.verts.new((x, -y, z)) for y, z in half[1:-1]]
        rings.append(pos + list(reversed(neg)))   # closed loop, length 2M-2
    L = 2 * M - 2

    faces_info = []
    for i in range(len(rings) - 1):
        for j in range(L):
            j2 = (j + 1) % L
            f = bm.faces.new((rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]))
            row = j if j < M - 1 else L - 1 - j
            zc = sum(v.co.z for v in f.verts) / 4
            f.material_index = face_mat(i, row, zc)
            faces_info.append(f)
    # end caps as quad strips between mirrored pairs
    for idx, rev in ((0, True), (len(rings) - 1, False)):
        ring = rings[idx]
        for j in range(M - 1):
            a, b = ring[j], ring[j + 1]
            mb = ring[(L - (j + 1)) % L]
            ma = ring[(L - j) % L]
            vs = [a, b, mb, ma]
            uniq = []
            for v in vs:
                if v not in uniq:
                    uniq.append(v)
            if len(uniq) < 3:
                continue
            f = bm.faces.new(uniq[::-1] if rev else uniq)
            zc = sum(v.co.z for v in f.verts) / len(f.verts)
            f.material_index = face_mat(-1 if rev else len(rings), j, zc)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    # creases: character lines along rows, ends, chosen stations
    cl = bm.edges.layers.float.get("crease_edge") or bm.edges.layers.float.new("crease_edge")
    rowset = {}
    for r, w in crease_rows.items():
        rowset[r] = w
    for i, ring in enumerate(rings):
        for j, v in enumerate(ring):
            row = j if j < M else L - j
            for e in v.link_edges:
                o = e.other_vert(v)
                # longitudinal edge: joins the same ring index on the next station
                if i + 1 < len(rings) and o is rings[i + 1][j] and row in rowset:
                    e[cl] = rowset[row]
        if i in (0, len(rings) - 1) or i in crease_stations:
            for j in range(L):
                a, b = ring[j], ring[(j + 1) % L]
                for e in a.link_edges:
                    if e.other_vert(a) is b:
                        e[cl] = crease_end if i in (0, len(rings) - 1) else max(e[cl], 0.9)
    ob = sbl.from_bmesh(name, bm, c, parent, mats=mats, smooth=True)
    if subsurf:
        ss = ob.modifiers.new("subsurf", "SUBSURF")
        ss.levels = ss.render_levels = subsurf
    return ob


def cut_arches(ob, wheels, radius, inner, mat, depth=0.6):
    """boolean cylinders through the sides at each wheel (not through the cabin)"""
    cutters = bpy.data.collections.new(f"{ob.name}_cutters")
    for x, y, z in wheels:
        bm = bmesh.new()
        sy = 1 if y > 0 else -1
        y0, y1 = sy * inner, sy * (inner + depth)
        sbl.tube(bm, (x, y0, z), (x, y1, z), radius, 48)
        me = bpy.data.meshes.new("cut")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        co = bpy.data.objects.new("cut", me)
        cutters.objects.link(co)
    mod = ob.modifiers.new("arches", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.operand_type = "COLLECTION"
    mod.collection = cutters
    mod.solver = "EXACT"
    mod.use_self = False
    mod.material_mode = "TRANSFER"
    # cutters must be in the view layer to evaluate; link temporarily
    bpy.context.scene.collection.children.link(cutters)
    for co in cutters.objects:
        co.parent = ob.parent
    bpy.context.view_layer.update()
    sbl.apply_modifiers(ob)
    bpy.context.scene.collection.children.unlink(cutters)
    for co in list(cutters.objects):
        bpy.data.objects.remove(co)
    bpy.data.collections.remove(cutters)


def wheel(name, c, parent, mats, loc, radius=WR, width=0.27, left=True, cover=True):
    """tyre + aerocover + rim lip; spins about local Y"""
    k = radius / WR
    hw = width / 2
    rr = 0.25 * k
    prof = [(rr, -hw + 0.005), (rr + 0.05 * k, -hw - 0.008), (radius - 0.02 * k, -hw - 0.004), (radius - 0.003, -hw + 0.03),
            (radius, -hw + 0.06), (radius, hw - 0.06), (radius - 0.003, hw - 0.03), (radius - 0.02 * k, hw + 0.004),
            (rr + 0.05 * k, hw + 0.008), (rr, hw - 0.005)]
    root = sbl.empty(name, c, parent, loc=loc)
    if not left:
        root.rotation_euler = (0, 0, math.pi)
    spin = sbl.empty(f"{name}_spin", c, root)
    sbl.lathe(f"{name}_tyre", prof, c, spin, mats=[mats.tire], seg=72)
    if cover:
        sbl.lathe(f"{name}_cover", [(0.0, hw - 0.012), (0.12 * k, hw - 0.014), (rr - 0.02 * k, hw - 0.02),
                                    (rr - 0.004, hw - 0.012)], c, spin, mats=[mats.cover], seg=72)
    sbl.lathe(f"{name}_rim", [(rr - 0.012, hw - 0.012), (rr + 0.004, hw - 0.004), (rr + 0.012, hw - 0.012),
                              (rr + 0.006, -hw + 0.01)], c, spin, mats=[mats.rim], seg=72)
    sbl.lathe(f"{name}_inner", [(0.0, -hw + 0.02), (rr, -hw + 0.02)], c, spin, mats=[mats.well], seg=32)
    return root, spin


class Cars:
    def __init__(self, mats):
        self.m = mats
        self.c = sbl.coll("Car")
        self.nozzles = {}

    # ------------------------------------------------------------ demo car
    def build(self):
        m = self.m
        self.root = sbl.empty("car_root", self.c)
        self.root.rotation_mode = "QUATERNION"
        self.body = sbl.empty("car_body", self.c, self.root)
        stations = [(x, half_ring(zb, zbl, zr, w, wr)) for x, zb, zbl, zr, w, wr in CAR]

        def face_mat(i, row, z):
            if i < 0 or i >= len(CAR):        # end caps
                if z < 0.27:
                    return 1
                return 0
            if row <= 2:
                return 1
            if row >= 5 and CABIN[0] <= i < CABIN[1]:
                return 2
            return 0

        shell = loft("car_shell", stations, self.c, self.body, [m.paint, m.carbon, m.glass], face_mat,
                     crease_rows={1: 0.7, 3: 1.0, 4: 1.0, 5: 0.85, 6: 1.0}, crease_end=0.85,
                     crease_stations=CABIN, subsurf=3)
        arches = [(sx * WHEEL_X, sy * WHEEL_Y, WR) for sx in (1, -1) for sy in (1, -1)]
        cut_arches(shell, arches, 0.415, 0.58, m.well)
        self.shell = shell
        self._details()
        self._lights()
        self._nozzles()
        self.wheels = []
        for sx, nm in ((1, "F"), (-1, "R")):
            for sy, side in ((1, "L"), (-1, "R")):
                r, s = wheel(f"wheel_{nm}{side}", self.c, self.root, m, (sx * WHEEL_X, sy * WHEEL_Y, WR), left=sy > 0)
                self.wheels.append((s, sy > 0))

    def _details(self):
        m = self.m
        bm = bmesh.new()
        sbl.box(bm, (2.205, 0, 0.115), (0.16, 1.78, 0.022))          # front splitter
        for y in (-0.6, -0.2, 0.2, 0.6):                                 # diffuser strakes
            sbl.box(bm, (-2.05, y, 0.17), (0.42, 0.018, 0.08))
        sbl.box(bm, (0.0, 0.0, 0.135), (3.2, 1.3, 0.01))                # flat underbody panel
        sbl.from_bmesh("car_aero", bm, self.c, self.body, mats=[m.carbon], smooth=False)
        # access hatches on the underbody: dark recessed rectangles
        bm = bmesh.new()
        for x, y in ((0.0, 0.0), (-0.4, 0.3), (0.4, -0.3)):
            sbl.box(bm, (x, y, 0.128), (0.42, 0.28, 0.004))
        sbl.from_bmesh("car_hatches", bm, self.c, self.body, mats=[m.well], smooth=False)

    def _lights(self):
        m = self.m
        # front: ultra-thin bar on the leading edge of the hood, two projector clusters
        bm = bmesh.new()
        sbl.box(bm, (2.236, 0, 0.432), (0.016, 1.44, 0.009))
        sbl.from_bmesh("lightbar", bm, self.c, self.body, mats=[m.lightbar], smooth=False)
        bm = bmesh.new()
        for sy in (1, -1):
            sbl.box(bm, (2.215, sy * 0.70, 0.395), (0.05, 0.16, 0.05))
        sbl.from_bmesh("headlamp_housing", bm, self.c, self.body, mats=[m.lamp_housing], smooth=False)
        bm = bmesh.new()
        for sy in (1, -1):
            for k in range(3):
                sbl.box(bm, (2.242, sy * (0.65 + 0.05 * k), 0.395), (0.008, 0.026, 0.026))
        sbl.from_bmesh("headlamps", bm, self.c, self.body, mats=[m.headlamp], smooth=False)
        # rear: full-width thin red bar
        bm = bmesh.new()
        sbl.box(bm, (-2.258, 0, 0.785), (0.012, 1.70, 0.014))
        sbl.from_bmesh("taillight", bm, self.c, self.body, mats=[m.taillamp], smooth=False)
        self.headlights = []
        for sy in (1, -1):
            ld = bpy.data.lights.new(f"headlight_{sy}", "SPOT")
            ld.energy = 0.0
            ld.color = (0.9, 0.95, 1.0)
            ld.spot_size = math.radians(48)
            ld.spot_blend = 0.6
            ld.shadow_soft_size = 0.03
            lo = bpy.data.objects.new(f"headlight_{sy}", ld)
            lo.location = (2.26, sy * 0.68, 0.40)
            lo.rotation_euler = (0, math.radians(-90 - 6), 0)     # -Z of the light points along +X, slightly down
            sbl.link(lo, self.c, self.body)
            self.headlights.append(ld)
        ld = bpy.data.lights.new("tail_glow", "AREA")
        ld.energy = 0.0
        ld.color = (1.0, 0.0, 0.03)
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = 1.6, 0.03
        lo = bpy.data.objects.new("tail_glow", ld)
        lo.location = (-2.28, 0, 0.785)
        lo.rotation_euler = (0, math.radians(-90), 0)
        sbl.link(lo, self.c, self.body)
        self.tail_glow = ld

    def _nozzles(self):
        m = self.m
        bm = bmesh.new()
        bm_in = bmesh.new()
        for name, pos, d, grp, L, W in NOZZLES:
            d = Vector(d).normalized()
            p = Vector(pos)
            r = 0.07 if grp in ("lift", "rear") else 0.05
            sbl.tube(bm, p - d * 0.06, p + d * 0.004, r, 20)
            sbl.tube(bm_in, p - d * 0.05, p + d * 0.006, r * 0.72, 20)
            self.nozzles[name] = {"pos": p, "dir": d, "group": grp, "L": L, "W": W}
        sbl.from_bmesh("nozzle_rings", bm, self.c, self.body, mats=[m.nozzle], smooth=True)
        sbl.from_bmesh("nozzle_throats", bm_in, self.c, self.body, mats=[m.well], smooth=True)

    # ------------------------------------------------------------ fleet
    def fleet_vehicle(self, kind, root, c):
        m = self.m
        if kind == "sedan":
            st = [(-2.35, 0.30, 0.78, 0.86, 0.90, 0.80), (-2.15, 0.22, 0.82, 0.96, 0.92, 0.80),
                  (-1.6, 0.18, 0.84, 1.08, 0.93, 0.74), (-0.9, 0.17, 0.84, 1.40, 0.93, 0.64),
                  (0.0, 0.17, 0.82, 1.44, 0.93, 0.64), (0.75, 0.17, 0.78, 1.12, 0.93, 0.74),
                  (1.5, 0.17, 0.74, 0.86, 0.92, 0.84), (2.2, 0.20, 0.66, 0.72, 0.88, 0.80),
                  (2.35, 0.28, 0.56, 0.62, 0.82, 0.70)]
            cab, paint, wr, wb = (3, 6), m.sedan, 0.335, 1.45
        elif kind == "crossover":
            st = [(-2.38, 0.36, 0.86, 1.10, 0.93, 0.80), (-2.2, 0.26, 0.92, 1.30, 0.95, 0.76),
                  (-1.5, 0.22, 0.94, 1.56, 0.96, 0.70), (-0.8, 0.21, 0.94, 1.62, 0.96, 0.68),
                  (0.2, 0.21, 0.92, 1.60, 0.96, 0.68), (0.85, 0.21, 0.88, 1.30, 0.96, 0.76),
                  (1.6, 0.22, 0.84, 1.00, 0.95, 0.86), (2.25, 0.26, 0.76, 0.84, 0.90, 0.80),
                  (2.38, 0.34, 0.66, 0.74, 0.84, 0.70)]
            cab, paint, wr, wb = (2, 6), m.crossover, 0.37, 1.45
        elif kind == "semi":
            st = [(-0.6, 1.05, 2.0, 3.35, 1.22, 1.05), (-0.3, 0.95, 2.0, 3.55, 1.25, 1.08),
                  (1.0, 0.95, 2.0, 3.55, 1.25, 1.06), (1.85, 0.75, 1.95, 3.3, 1.25, 1.00),
                  (2.45, 0.60, 1.7, 2.6, 1.24, 1.02), (2.9, 0.55, 1.4, 1.85, 1.20, 1.0),
                  (3.15, 0.55, 1.0, 1.25, 1.10, 0.95)]
            cab, paint, wr, wb = (2, 4), m.semi, 0.52, None
        else:   # wedge truck: flat facets, no subdivision
            st = [(-2.85, 0.55, 1.20, 1.30, 1.0, 0.95), (-1.2, 0.48, 1.25, 1.60, 1.0, 0.80),
                  (0.25, 0.48, 1.30, 1.92, 1.0, 0.66), (2.3, 0.48, 1.16, 1.20, 1.0, 0.92),
                  (2.85, 0.55, 1.05, 1.08, 0.98, 0.92)]
            cab, paint, wr, wb = (1, 3), m.stainless, 0.43, 1.85
        stations = [(x, half_ring(zb, zbl, zr, w, wrr)) for x, zb, zbl, zr, w, wrr in st]

        def face_mat(i, row, z):
            if i < 0 or i >= len(st):
                return 1 if z < st[0][1] + 0.12 else 0
            if row <= 2:
                return 1
            if row >= 5 and cab[0] <= i < cab[1]:
                return 2
            return 0

        mats = [paint, m.carbon if kind != "wedge" else m.rim, m.glass]
        ob = loft(f"{kind}_body", stations, c, root, mats, face_mat,
                  crease_rows={1: 0.6, 3: 1.0, 4: 1.0, 6: 1.0} if kind != "wedge" else {},
                  crease_stations=cab, subsurf=2 if kind != "wedge" else 0)
        if kind == "semi":
            axles = [2.25, -1.75, -3.05]
            bm = bmesh.new()
            sbl.box(bm, (-1.9, 0.0, 1.0), (2.8, 0.9, 0.25))             # frame rails
            sbl.box(bm, (-2.3, 0.0, 1.17), (1.0, 1.0, 0.08))            # fifth wheel
            for sy in (1, -1):
                sbl.box(bm, (-0.2, sy * 0.95, 0.75), (1.0, 0.45, 0.55))  # tanks
            sbl.from_bmesh(f"{kind}_chassis", bm, c, root, mats=[m.rim], smooth=False)
            track = 1.0
        else:
            axles = [wb, -wb] if kind != "wedge" else [1.85, -1.75]
            track = 0.80 if kind != "wedge" else 0.86
        cut_arches(ob, [(x, sy * track, wr) for x in axles for sy in (1, -1)], wr + 0.06, track - 0.25, m.well)
        for x in axles:
            for sy in (1, -1):
                wheel(f"{kind}_wheel_{x}_{sy}", c, root, m, (x, sy * track, wr), radius=wr, width=0.3 if kind == "semi" else 0.25,
                      left=sy > 0, cover=kind not in ("semi", "wedge"))
        # lamps
        bm = bmesh.new()
        xf = st[-1][0]
        sbl.box(bm, (xf + 0.005, 0, st[-1][2] - 0.04), (0.012, 2 * st[-1][4] * 0.8, 0.012))
        sbl.from_bmesh(f"{kind}_front_lamp", bm, c, root, mats=[m.headlamp], smooth=False)
        if kind != "semi":
            bm = bmesh.new()
            sbl.box(bm, (st[0][0] - 0.005, 0, st[0][2] - 0.03), (0.012, 2 * st[0][4] * 0.85, 0.014))
            sbl.from_bmesh(f"{kind}_tail_lamp", bm, c, root, mats=[m.taillamp], smooth=False)
