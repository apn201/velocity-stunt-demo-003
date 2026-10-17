"""Telemetry overlay: a second scene, orthographic, 1 unit = 1 pixel, rendered with a transparent film.

Live numbers are Geometry Nodes text (Value to String -> String to Curves -> Fill),
driven by baked modifier inputs, so a readout changes every frame without a text
object per value. Gauges are curves; the wireframe car is the real car's loft
cage through a Wireframe modifier, turned with the car's pitch and roll.
"""
import math
import os

import bmesh
import bpy
from mathutils import Euler, Quaternion, Vector

import sbl
import stimeline as T
from sconfig import END_CARD, FPS, FT, MPH, N, RES

W, H = RES
WHITE = (1.0, 1.0, 1.0)
RED = (1.0, 0.0, 0.03)
LINE = 2.0


def P(x, y):
    """screen pixel (y down) -> HUD plane"""
    return (x - W / 2, H / 2 - y, 0.0)


def font(name="Inter.woff2"):
    p = os.path.join(os.path.dirname(bpy.app.binary_path), f"{bpy.app.version[0]}.{bpy.app.version[1]}",
                     "datafiles", "fonts", name)
    f = bpy.data.fonts.get(name) or bpy.data.fonts.load(p)
    return f


class Hud:
    def __init__(self, sim, mats):
        self.sim = sim
        sc = bpy.data.scenes.new("HUD")
        self.sc = sc
        self.c = sc.collection
        self.frames = list(range(0, N + 2))
        self.font = font()
        self.mono = font("DejaVuSansMono.woff2")
        self.mat = self._mat()
        self.num_tree = self._number_tree()
        self.boot = []            # (object, appear time)

    # ------------------------------------------------------------ scene
    def setup(self, fps):
        sc = self.sc
        sc.render.engine = "BLENDER_EEVEE"
        sc.render.resolution_x, sc.render.resolution_y = RES
        sc.render.film_transparent = True
        sc.render.fps = fps
        sc.frame_start, sc.frame_end = 1, N
        sc.view_settings.view_transform = "Standard"
        sc.eevee.taa_render_samples = 16
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGBA"
        cd = bpy.data.cameras.new("hud_cam")
        cd.type = "ORTHO"
        cd.ortho_scale = W
        cam = bpy.data.objects.new("hud_cam", cd)
        cam.location = (0, 0, 10)
        self.c.objects.link(cam)
        sc.camera = cam
        w = bpy.data.worlds.new("hud_world")
        sc.world = w

    def _mat(self):
        m = bpy.data.materials.new("hud_ink")
        n = sbl.Nodes(m.node_tree)
        info = n.node("ShaderNodeObjectInfo")
        em = n.node("ShaderNodeEmission", {"Color": info.outputs["Color"], "Strength": 1.0})
        tr = n.node("ShaderNodeBsdfTransparent")
        mix = n.node("ShaderNodeMixShader")
        n.set(mix.inputs[0], info.outputs["Alpha"])
        n.set(mix.inputs[1], tr)
        n.set(mix.inputs[2], em)
        n.out(mix)
        m.surface_render_method = "BLENDED"
        return m

    def _number_tree(self):
        ng = bpy.data.node_groups.new("hud_number", "GeometryNodeTree")
        ng.is_modifier = True
        it = ng.interface
        it.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        it.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        s_val = it.new_socket("Value", in_out="INPUT", socket_type="NodeSocketFloat")
        s_dec = it.new_socket("Decimals", in_out="INPUT", socket_type="NodeSocketInt")
        s_pre = it.new_socket("Prefix", in_out="INPUT", socket_type="NodeSocketString")
        s_suf = it.new_socket("Suffix", in_out="INPUT", socket_type="NodeSocketString")
        s_size = it.new_socket("Size", in_out="INPUT", socket_type="NodeSocketFloat")
        s_pad = it.new_socket("Padding", in_out="INPUT", socket_type="NodeSocketInt")
        n = sbl.Nodes(ng)
        gi = n.node("NodeGroupInput")
        go = n.node("NodeGroupOutput")
        vts = n.node("FunctionNodeValueToString")
        n.set(vts.inputs["Value"], gi.outputs["Value"])
        n.set(vts.inputs["Decimals"], gi.outputs["Decimals"])
        if "Padding" in vts.inputs:
            n.set(vts.inputs["Padding"], gi.outputs["Padding"])
        join = n.node("GeometryNodeStringJoin")
        for sock in (gi.outputs["Suffix"], vts.outputs["String"], gi.outputs["Prefix"]):
            ng.links.new(sock, join.inputs["Strings"])
        stc = n.node("GeometryNodeStringToCurves")
        n.set(stc.inputs["String"], join.outputs["String"])
        n.set(stc.inputs["Size"], gi.outputs["Size"])
        if "Font" in stc.inputs:
            stc.inputs["Font"].default_value = self.mono
        else:
            stc.font = self.mono
        self._align_sock = stc
        real = n.node("GeometryNodeRealizeInstances")
        n.set(real.inputs["Geometry"], stc.outputs["Curve Instances"])
        fill = n.node("GeometryNodeFillCurve")
        n.set(fill.inputs["Curve"], real.outputs["Geometry"])
        try:
            fill.inputs["Fill Rule"].default_value = "Even-Odd"
        except Exception:
            pass
        setm = n.node("GeometryNodeSetMaterial")
        n.set(setm.inputs["Geometry"], fill.outputs["Mesh"])
        setm.inputs["Material"].default_value = self.mat
        n.set(go.inputs["Geometry"], setm.outputs["Geometry"])
        self._sock_ids = {it.items_tree[k].name: it.items_tree[k].identifier for k in range(len(it.items_tree))}
        return ng

    # ------------------------------------------------------------ primitives
    def number(self, name, pos, size, values, decimals=1, prefix="", suffix="", pad=0, align="LEFT", alpha=1.0):
        me = bpy.data.meshes.new(name)
        ob = bpy.data.objects.new(name, me)
        self.c.objects.link(ob)
        ob.location = P(*pos)
        ob.color = (*WHITE, alpha)
        mod = ob.modifiers.new("num", "NODES")
        if align != "LEFT":
            # one tree per alignment so the menu socket stays a constant
            key = f"hud_number_{align}"
            ng = bpy.data.node_groups.get(key)
            if ng is None:
                ng = self.num_tree.copy()
                ng.name = key
                for nd in ng.nodes:
                    if nd.bl_idname == "GeometryNodeStringToCurves":
                        try:
                            nd.inputs["Align X"].default_value = {"RIGHT": "Right", "CENTER": "Center"}[align]
                        except Exception:
                            nd.align_x = align
            mod.node_group = ng
        else:
            mod.node_group = self.num_tree
        ids = self._sock_ids
        ins = mod.properties.inputs
        getattr(ins, ids["Decimals"]).value = decimals
        getattr(ins, ids["Prefix"]).value = prefix
        getattr(ins, ids["Suffix"]).value = suffix
        getattr(ins, ids["Size"]).value = float(size)
        getattr(ins, ids["Padding"]).value = pad
        getattr(ins, ids["Value"]).value = float(values[0])
        sbl.bake(ob, f'modifiers["num"].properties.inputs.{ids["Value"]}.value', self.frames, values)
        return ob

    def text(self, name, body, pos, size, align="LEFT", alpha=0.75, color=WHITE, mono=False):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = body
        cu.font = self.mono if mono else self.font
        cu.size = size
        cu.align_x = align
        cu.align_y = "BOTTOM_BASELINE"
        cu.materials.append(self.mat)
        ob = bpy.data.objects.new(name, cu)
        ob.location = P(*pos)
        ob.color = (*color, alpha)
        self.c.objects.link(ob)
        return ob

    def poly(self, name, pts, width=LINE, alpha=1.0, cyclic=False, color=WHITE, parent=None):
        cu = bpy.data.curves.new(name, "CURVE")
        cu.dimensions = "2D"
        cu.fill_mode = "BOTH"
        cu.extrude = 0.0
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for p, q in zip(sp.points, pts):
            p.co = (q[0], q[1], 0, 1)
        sp.use_cyclic_u = cyclic
        cu.bevel_depth = width / 2
        cu.bevel_resolution = 0
        cu.dimensions = "3D"
        cu.materials.append(self.mat)
        ob = bpy.data.objects.new(name, cu)
        ob.color = (*color, alpha)
        self.c.objects.link(ob)
        if parent is not None:
            ob.parent = parent
        return ob

    def circle(self, name, center, r, width=LINE, alpha=1.0, a0=0.0, a1=2 * math.pi, seg=160, color=WHITE):
        cx, cy, _ = P(*center)
        n = max(8, int(seg * (a1 - a0) / (2 * math.pi)))
        pts = [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
        full = abs(a1 - a0 - 2 * math.pi) < 1e-6
        return self.poly(name, pts[:-1] if full else pts, width, alpha, cyclic=full, color=color)

    def seg(self, name, a, b, width=LINE, alpha=1.0):
        pa, pb = P(*a), P(*b)
        return self.poly(name, [pa[:2], pb[:2]], width, alpha)

    def quad(self, name, x0, y0, x1, y1, alpha=1.0, color=WHITE):
        a, b = P(x0, y0), P(x1, y1)
        me = bpy.data.meshes.new(name)
        me.from_pydata([(a[0], b[1], 0), (b[0], b[1], 0), (b[0], a[1], 0), (a[0], a[1], 0)], [], [(0, 1, 2, 3)])
        me.materials.append(self.mat)
        ob = bpy.data.objects.new(name, me)
        ob.color = (*color, alpha)
        self.c.objects.link(ob)
        return ob

    def appear(self, ob, t, t_off=END_CARD - 0.4):
        self.boot.append((ob, t, t_off))

    # ------------------------------------------------------------ layout
    def build(self):
        sim = self.sim
        samples = [sim.frame(f) for f in self.frames]
        self.samples = samples
        tb = 3.0     # boot

        # corner brackets
        for i, (x, y, dx, dy) in enumerate(((60, 50, 1, 1), (W - 60, 50, -1, 1), (60, H - 50, 1, -1), (W - 60, H - 50, -1, -1))):
            ob = self.poly(f"bracket_{i}", [P(x + dx * 60, y)[:2], P(x, y)[:2], P(x, y + dy * 60)[:2]], 2.0, 0.6)
            self.appear(ob, tb + 0.05 * i)

        # top left: title and phase
        self.appear(self.text("title", "VELOCITY // STUNT DEMO 003", (92, 104), 22, alpha=0.9), tb)
        self.appear(self.text("subtitle", "COLD-GAS THRUSTER PACKAGE  /  LIVE TELEMETRY", (92, 134), 15, alpha=0.55), tb + 0.1)
        starts = sim.phase_starts()
        for i, (_, label) in enumerate(T.PHASES):
            ob = self.text(f"phase_{i}", label, (92, 176), 20, alpha=1.0, color=WHITE)
            t0 = max(starts[i], tb + 0.2)
            t1 = starts[i + 1] if i + 1 < len(starts) else END_CARD - 0.4
            self.boot.append((ob, t0, t1))
        self.appear(self.poly("phase_rule", [P(92, 190)[:2], P(560, 190)[:2]], 1.5, 0.45), tb + 0.2)

        # top right: clock and speed
        tvals = [max(0.0, (f - 1) / FPS - T.T_GO) for f in self.frames]
        self.appear(self.text("t_label", "T+", (W - 300, 104), 15, alpha=0.55), tb)
        self.appear(self.number("t_value", (W - 92, 106), 26, tvals, 2, suffix=" S", align="RIGHT"), tb)
        spd = [s["speed"] / MPH for s in samples]
        self.appear(self.text("spd_label", "SPEED", (W - 300, 150), 15, alpha=0.55), tb + 0.05)
        self.appear(self.number("spd_value", (W - 92, 152), 26, spd, 0, suffix=" MPH", align="RIGHT"), tb + 0.05)

        self.g_gauge(tb + 0.15)
        self.attitude(tb + 0.25)
        self.chassis(tb + 0.3)
        self.altitude(tb + 0.2)
        self.end_card()
        self.fader()
        self._bake_boot()

    def g_gauge(self, tb):
        cx, cy, R = 200, 880, 105
        px_per_g = R / 4.0
        self.appear(self.circle("g_ring", (cx, cy), R, 2.0, 0.9), tb)
        for g in (1, 2, 3):
            self.appear(self.circle(f"g_ring_{g}", (cx, cy), g * px_per_g, 1.2, 0.28), tb + 0.05)
        self.appear(self.seg("g_h", (cx - R, cy), (cx + R, cy), 1.2, 0.3), tb)
        self.appear(self.seg("g_v", (cx, cy - R), (cx, cy + R), 1.2, 0.3), tb)
        for k in range(24):
            a = 2 * math.pi * k / 24
            l0 = R - (10 if k % 6 == 0 else 5)
            self.appear(self.seg(f"g_tick_{k}", (cx + l0 * math.cos(a), cy + l0 * math.sin(a)),
                                 (cx + R * math.cos(a), cy + R * math.sin(a)), 1.6, 0.8), tb)
        # moving crosshair: longitudinal G across, load above 1 G up
        root = bpy.data.objects.new("g_dot", None)
        self.c.objects.link(root)
        locs = []
        for s in self.samples:
            dx = max(-4, min(4, s["g_long"])) * px_per_g
            dy = max(-4, min(4, s["g_norm"] - 1.0)) * px_per_g
            r = math.hypot(dx, dy)
            if r > R - 6:
                dx, dy = dx * (R - 6) / r, dy * (R - 6) / r
            x, y, _ = P(cx + dx, cy - dy)
            locs.append((x, y, 0.5))
        sbl.bake_vec(root, "location", self.frames, locs)
        for nm, pts in (("h", [(-14, 0), (14, 0)]), ("v", [(0, -14), (0, 14)])):
            self.appear(self.poly(f"g_cross_{nm}", pts, 2.2, 1.0, parent=root), tb + 0.1)
        ob = self.poly("g_cross_o", [(7 * math.cos(a * math.pi / 16), 7 * math.sin(a * math.pi / 16)) for a in range(32)],
                       1.8, 1.0, cyclic=True, parent=root)
        self.appear(ob, tb + 0.1)
        self.appear(self.text("g_label", "G-FORCE", (cx + R + 28, cy - 30), 15, alpha=0.55), tb)
        self.appear(self.number("g_value", (cx + R + 26, cy + 12), 40, [s["g"] for s in self.samples], 1, suffix=" G"), tb)
        self.appear(self.text("g_scale", "4 G FULL SCALE", (cx - R, cy + R + 34), 12, alpha=0.4), tb)

    def attitude(self, tb):
        """wireframe car turned by the real pitch and roll, seen from a fixed three-quarter view"""
        from scar import CAR, half_ring
        cx, cy, k = 590, 868, 34.0
        bm = bmesh.new()
        rings = []
        for x, zb, zbl, zr, w, wr in CAR[::2] + [CAR[-1]]:
            half = half_ring(zb, zbl, zr, w, wr)
            pts = [(x, y, z - 0.55) for y, z in half] + [(x, -y, z - 0.55) for y, z in reversed(half[1:-1])]
            rings.append([bm.verts.new(p) for p in pts])
        for i in range(len(rings) - 1):
            L = len(rings[i])
            for j in range(L):
                bm.faces.new((rings[i][j], rings[i][(j + 1) % L], rings[i + 1][(j + 1) % L], rings[i + 1][j]))
        me = bpy.data.meshes.new("att_car")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(self.mat)
        pivot = bpy.data.objects.new("att_pivot", None)
        self.c.objects.link(pivot)
        pivot.location = P(cx, cy)
        pivot.scale = (k, k, k)
        view = bpy.data.objects.new("att_view", None)
        self.c.objects.link(view)
        view.parent = pivot
        view.rotation_euler = (math.radians(-68), 0, math.radians(-35))
        car = bpy.data.objects.new("att_car", me)
        self.c.objects.link(car)
        car.parent = view
        car.rotation_mode = "QUATERNION"
        car.color = (*WHITE, 0.9)
        wf = car.modifiers.new("wire", "WIREFRAME")
        wf.thickness = 0.035
        wf.use_relative_offset = False
        rots = []
        for s in self.samples:
            # body attitude relative to heading: strip yaw so the icon only pitches and rolls
            yaw, pitch, roll = T.q_euler_zyx(s["q"])
            rots.append(tuple(Quaternion((0, 1, 0), pitch) @ Quaternion((1, 0, 0), roll)))
        for i in range(1, len(rots)):          # keep the quaternion track continuous
            if sum(a * b for a, b in zip(rots[i], rots[i - 1])) < 0:
                rots[i] = tuple(-c for c in rots[i])
        sbl.bake_vec(car, "rotation_quaternion", self.frames, rots)
        self.appear(car, tb)
        self.appear(self.circle("att_ring", (cx, cy), 98, 1.2, 0.3), tb)
        pitch, roll = [], []
        for s in self.samples:
            _, p, r = T.q_euler_zyx(s["q"])
            if s["mode"] == "track":
                # on the pipe, pitch is the climb angle along the path (0 to 180 over the top)
                fw = T.q_rot(s["q"], (1, 0, 0))
                p, r = math.atan2(fw[2], fw[0]), 0.0
            pitch.append(math.degrees(p))
            roll.append(math.degrees(r))
        self.appear(self.text("pitch_label", "PITCH", (cx + 120, cy - 30), 15, alpha=0.55), tb)
        self.appear(self.number("pitch_value", (cx + 120, cy + 2), 24, pitch, 1, suffix=" °"), tb)
        self.appear(self.text("roll_label", "ROLL", (cx + 120, cy + 40), 15, alpha=0.55), tb)
        self.appear(self.number("roll_value", (cx + 120, cy + 72), 24, roll, 0, suffix=" °"), tb)

    def chassis(self, tb):
        """top-down schematic: wheels, nozzles lit by their thrust, suction status"""
        from scar import NOZZLES
        cx, cy, k = 1430, 872, 44.0
        hw, hl = 0.99 * k, 2.25 * k

        def tp(x, y):          # car (x forward, y left) -> screen, nose up
            return (cx - y * k, cy - x * k)
        outline = [tp(2.25, 0.86), tp(2.25, -0.86), tp(1.9, -0.98), tp(-2.1, -0.98), tp(-2.25, -0.9),
                   tp(-2.25, 0.9), tp(-2.1, 0.98), tp(1.9, 0.98)]
        self.appear(self.poly("ch_outline", [P(*p)[:2] for p in outline], 2.0, 0.9, cyclic=True), tb)
        for sx in (1, -1):
            for sy in (1, -1):
                x0, y0 = tp(sx * T.WB / 2 + 0.36, sy * T.TRACK / 2 + 0.14)
                x1, y1 = tp(sx * T.WB / 2 - 0.36, sy * T.TRACK / 2 - 0.14)
                self.appear(self.poly(f"ch_wheel_{sx}_{sy}", [P(x0, y0)[:2], P(x1, y0)[:2], P(x1, y1)[:2], P(x0, y1)[:2]],
                                      1.6, 0.8, cyclic=True), tb)
        self.appear(self.poly("ch_cabin", [P(*tp(0.9, 0.62))[:2], P(*tp(0.9, -0.62))[:2], P(*tp(-0.8, -0.62))[:2],
                                           P(*tp(-0.8, 0.62))[:2]], 1.2, 0.35, cyclic=True), tb)
        for name, pos, d, grp, L, Wd in NOZZLES:
            x, y = tp(pos[0], pos[1])
            ring = self.circle(f"nz_ring_{name}", (x, y), 7.5, 1.4, 0.7)
            self.appear(ring, tb)
            dot = self.quad(f"nz_dot_{name}", x - 5, y - 5, x + 5, y + 5, alpha=0.0)
            self.nozzle_dots = getattr(self, "nozzle_dots", [])
            self.nozzle_dots.append((dot, name))
            if grp != "lift":
                dx, dy = -d[1] * 16, -d[0] * 16
                self.appear(self.seg(f"nz_dir_{name}", (x, y), (x + dx, y + dy), 1.2, 0.5), tb)
        self.appear(self.text("ch_label", "THRUSTERS", (cx - 120, cy - 128), 15, alpha=0.55), tb)
        # suction box: lit while the car is on the pipe
        self.appear(self.text("suc_label", "SUCTION", (cx - 120, cy + 140), 13, alpha=0.55), tb)
        box = self.quad("suc_box", cx - 40, cy + 128, cx + 30, cy + 142, alpha=0.0)
        self.suction_box = box
        self.appear(self.poly("suc_frame", [P(cx - 40, cy + 128)[:2], P(cx + 30, cy + 128)[:2], P(cx + 30, cy + 142)[:2],
                                            P(cx - 40, cy + 142)[:2]], 1.2, 0.6, cyclic=True), tb)

    def altitude(self, tb):
        cx, cy, R = 1720, 872, 105
        a0, a1 = math.radians(225), math.radians(-45)       # 270 degree sweep, clockwise
        self.appear(self.circle("alt_ring", (cx, cy), R, 2.0, 0.9), tb)
        for k in range(13):
            a = a0 + (a1 - a0) * k / 12
            l0 = R - (12 if k % 3 == 0 else 6)
            self.appear(self.seg(f"alt_tick_{k}", (cx + l0 * math.cos(a), cy - l0 * math.sin(a)),
                                 (cx + R * math.cos(a), cy - R * math.sin(a)), 1.6, 0.8), tb)
        # filled arc: a thick curve whose end is baked from the altitude
        x0, y0, _ = P(cx, cy)
        n = 120
        pts = [(x0 + (R - 18) * math.cos(a0 + (a1 - a0) * i / n), y0 + (R - 18) * math.sin(a0 + (a1 - a0) * i / n))
               for i in range(n + 1)]
        arc = self.poly("alt_arc", pts, 9.0, 0.95)
        arc.data.bevel_factor_mapping_end = "SPLINE"
        alts = [max(0.0, s["pos"][2]) / FT for s in self.samples]
        sbl.bake(arc.data, "bevel_factor_end", self.frames, [max(0.002, min(1.0, a / 60.0)) for a in alts])
        self.appear(arc, tb)
        self.appear(self.text("alt_label", "ALTITUDE", (cx, cy + 34), 14, align="CENTER", alpha=0.55), tb)
        self.appear(self.number("alt_value", (cx, cy + 10), 36, alts, 1, align="CENTER"), tb)
        self.appear(self.text("alt_unit", "FT", (cx, cy + 58), 14, align="CENTER", alpha=0.55), tb)
        self.appear(self.text("alt_scale", "0 - 60 FT", (cx - R, cy + R + 34), 12, alpha=0.4), tb)

    def end_card(self):
        s = self.sim.summary()
        t0 = END_CARD
        rows = [("0 - 60 MPH", f"{s['t_060']:.2f} S"), ("PEAK LOAD", f"{s['peak_g']:.1f} G"),
                ("LIP HEIGHT", f"{s['max_alt_ft']:.1f} FT"), ("KICKFLIP", "540 °"),
                ("HOVER", f"{s['hover_ft']:.1f} FT")]
        y = 430
        self.boot.append((self.text("end_title", "VELOCITY // STUNT DEMO 003", (W / 2, 330), 44, align="CENTER", alpha=1.0),
                          t0 + 0.2, 99))
        self.boot.append((self.poly("end_rule", [P(W / 2 - 300, 362)[:2], P(W / 2 + 300, 362)[:2]], 1.5, 0.5), t0 + 0.3, 99))
        for i, (a, b) in enumerate(rows):
            self.boot.append((self.text(f"end_k_{i}", a, (W / 2 - 280, y + 58 * i), 24, alpha=0.6), t0 + 0.45 + 0.12 * i, 99))
            self.boot.append((self.text(f"end_v_{i}", b, (W / 2 + 280, y + 58 * i), 30, align="RIGHT", alpha=1.0, mono=True),
                              t0 + 0.45 + 0.12 * i, 99))
        self.boot.append((self.text("end_note", "ONE PYTHON SCRIPT  /  BLENDER  /  NO ASSETS", (W / 2, 820), 16,
                                    align="CENTER", alpha=0.45), t0 + 1.2, 99))
        self.boot.append((self.poly("end_red", [P(W / 2 - 60, 860)[:2], P(W / 2 + 60, 860)[:2]], 3.0, 1.0, color=RED),
                          t0 + 1.2, 99))

    def fader(self):
        """full-frame black: fade up from black, and the end card's background"""
        ob = self.quad("black", -10, -10, W + 10, H + 10, alpha=1.0, color=(0, 0, 0))
        ob.location.z = -1.0
        vals = []
        for f in self.frames:
            t = (f - 1) / FPS
            a = 1 - T.smooth(t / 0.8)
            a = max(a, T.smooth((t - (END_CARD - 0.35)) / 0.35))
            vals.append(a)
        sbl.bake(ob, "color", self.frames, vals, index=3)
        sbl.bake_visibility(ob, self.frames, [v > 1e-3 for v in vals])

    def _bake_boot(self):
        for ob, t_on, t_off in self.boot:
            base = ob.color[3]
            vals, vis = [], []
            for f in self.frames:
                t = (f - 1) / FPS
                u = (t - t_on) / 0.25
                # boot flicker, then steady; fade out with the telemetry
                a = 0.0 if u < 0 else (base * (0.35 if int(u * 12) % 2 else 1.0) if u < 1 else base)
                if t >= t_off:
                    a *= 1 - T.smooth((t - t_off) / 0.3)
                vals.append(a)
                vis.append(a > 1e-3)
            sbl.bake(ob, "color", self.frames, vals, index=3)
            sbl.bake_visibility(ob, self.frames, vis)
        # nozzle dots lit by thrust, suction box lit on the pipe
        for dot, name in getattr(self, "nozzle_dots", []):
            vals = []
            for f in self.frames:
                t = (f - 1) / FPS
                on = 1.0 if 3.3 <= t < END_CARD - 0.4 else 0.0
                vals.append(on * min(1.0, self.vfx.level(name, t) * 1.2))
            sbl.bake(dot, "color", self.frames, vals, index=3)
            sbl.bake_visibility(dot, self.frames, [v > 0.02 for v in vals])
        vals = []
        for f, s in zip(self.frames, self.samples):
            t = (f - 1) / FPS
            on = s["mode"] == "track" and t > T.T_GO and s["pos"][0] > -3.5 and t < END_CARD - 0.4
            vals.append(0.95 if on else 0.0)
        sbl.bake(self.suction_box, "color", self.frames, vals, index=3, interp="CONSTANT")
        sbl.bake_visibility(self.suction_box, self.frames, [v > 0 for v in vals])
