"""bpy helpers: collections, meshes from lists, shader node wiring, per-frame baking."""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector


# ----------------------------------------------------------------- scene graph
def coll(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    p = parent or bpy.context.scene.collection
    if c.name not in p.children:
        p.children.link(c)
    return c


def link(ob, c, parent=None):
    c.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def empty(name, c, parent=None, loc=(0, 0, 0)):
    ob = bpy.data.objects.new(name, None)
    ob.location = loc
    ob.empty_display_size = 0.3
    return link(ob, c, parent)


def mesh_obj(name, verts, faces, c, parent=None, mats=(), mat_idx=None, uvs=None, smooth=True, creases=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li, vi in zip(poly.loop_indices, poly.vertices):
                uvl.data[li].uv = uvs[vi]
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set("material_index", mat_idx)
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    if creases:
        attr = me.attributes.new("crease_edge", "FLOAT", "EDGE")
        lut = {}
        for e in me.edges:
            lut[tuple(sorted(e.vertices))] = e.index
        for (a, b), w in creases.items():
            i = lut.get(tuple(sorted((a, b))))
            if i is not None:
                attr.data[i].value = w
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    return link(ob, c, parent)


def from_bmesh(name, bm, c, parent=None, mats=(), smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    me.update()
    ob = bpy.data.objects.new(name, me)
    return link(ob, c, parent)


def apply_modifiers(ob):
    """bake the modifier stack into the mesh so it is evaluated once, not per frame"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)


def tube(bm, a, b, r, sides=10):
    """a cylinder between points a and b into an existing bmesh"""
    a, b = Vector(a), Vector(b)
    d = b - a
    ln = d.length
    if ln < 1e-6:
        return
    q = d.normalized().to_track_quat("Z", "Y")
    m = Matrix.Translation(a) @ q.to_matrix().to_4x4()
    ring0, ring1 = [], []
    for i in range(sides):
        ang = 2 * math.pi * i / sides
        p = Vector((r * math.cos(ang), r * math.sin(ang), 0))
        ring0.append(bm.verts.new(m @ p))
        ring1.append(bm.verts.new(m @ (p + Vector((0, 0, ln)))))
    for i in range(sides):
        j = (i + 1) % sides
        bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
    bm.faces.new(list(reversed(ring0)))
    bm.faces.new(ring1)


def box(bm, center, size, rot=None):
    cx, cy, cz = center
    sx, sy, sz = (s / 2 for s in size)
    m = rot.to_4x4() if rot is not None else Matrix.Identity(4)
    vs = []
    for dx, dy, dz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
        p = m @ Vector((dx * sx, dy * sy, dz * sz))
        vs.append(bm.verts.new((p.x + cx, p.y + cy, p.z + cz)))
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([vs[i] for i in f])


def lathe(name, profile, c, parent=None, mats=(), seg=64, axis="Y", mat_idx_fn=None, smooth=True):
    """revolve a (r, h) profile about an axis; profile runs from one end to the other"""
    verts, faces, mi = [], [], []
    n = len(profile)
    for k in range(seg):
        a = 2 * math.pi * k / seg
        ca, sa = math.cos(a), math.sin(a)
        for r, h in profile:
            if axis == "Y":
                verts.append((r * ca, h, r * sa))
            else:
                verts.append((r * ca, r * sa, h))
    for k in range(seg):
        k2 = (k + 1) % seg
        for i in range(n - 1):
            a, b = k * n + i, k * n + i + 1
            c2, d = k2 * n + i + 1, k2 * n + i
            faces.append((a, d, c2, b) if axis == "Y" else (a, b, c2, d))
            mi.append(mat_idx_fn(i) if mat_idx_fn else 0)
    return mesh_obj(name, verts, faces, c, parent, mats=mats, mat_idx=mi, smooth=smooth)


def curve_obj(name, pts, c, parent=None, bevel=0.02, mat=None, cyclic=False, res=0):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = res
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts):
        p.co = (q[0], q[1], q[2], 1.0)
    sp.use_cyclic_u = cyclic
    if mat is not None:
        cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    return link(ob, c, parent)


# ----------------------------------------------------------------- shader nodes
class Nodes:
    """terse node wiring: n.node(type, inputs..., **props); values that are sockets are linked"""

    def __init__(self, tree, clear=True):
        self.t = tree
        if clear:
            tree.nodes.clear()
        self.x = 0

    def node(self, kind, inputs=None, **props):
        nd = self.t.nodes.new(kind)
        nd.location = (self.x, 0)
        self.x += 180
        for k, v in props.items():
            setattr(nd, k, v)
        for key, val in (inputs or {}).items():
            sock = nd.inputs[key]
            self.set(sock, val)
        return nd

    def set(self, sock, val):
        if isinstance(val, bpy.types.NodeSocket):
            self.t.links.new(val, sock)
        elif isinstance(val, bpy.types.Node):
            self.t.links.new(val.outputs[0], sock)
        else:
            sock.default_value = val

    def math(self, op, a, b=None, c=None, clamp=False):
        nd = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.set(nd.inputs[i], v)
        return nd.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        nd = self.node("ShaderNodeVectorMath", operation=op)
        self.set(nd.inputs[0], a)
        if b is not None:
            self.set(nd.inputs[1], b)
        if scale is not None:
            self.set(nd.inputs["Scale"], scale)
        return nd.outputs["Value"] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else nd.outputs["Vector"]

    def maprange(self, v, a, b, c=0.0, d=1.0, interp="LINEAR", clamp=True):
        nd = self.node("ShaderNodeMapRange", interpolation_type=interp, clamp=clamp)
        for k, x in (("Value", v), ("From Min", a), ("From Max", b), ("To Min", c), ("To Max", d)):
            self.set(nd.inputs[k], x)
        return nd.outputs["Result"]

    def ramp(self, fac, stops):
        nd = self.node("ShaderNodeValToRGB")
        self.set(nd.inputs["Fac"], fac)
        els = nd.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = (*col, 1.0) if len(col) == 3 else col
        return nd.outputs["Color"]

    def attr(self, name, kind="OBJECT"):
        return self.node("ShaderNodeAttribute", attribute_type=kind, attribute_name=name).outputs["Fac"]

    def coords(self, which="Object"):
        return self.node("ShaderNodeTexCoord").outputs[which]

    def xyz(self, v):
        nd = self.node("ShaderNodeSeparateXYZ")
        self.set(nd.inputs[0], v)
        return nd.outputs["X"], nd.outputs["Y"], nd.outputs["Z"]

    def combine(self, x, y, z):
        nd = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.set(nd.inputs[i], v)
        return nd.outputs[0]

    def noise(self, vec, scale, detail=4.0, rough=0.55, w=None, distortion=0.0, out="Fac"):
        nd = self.node("ShaderNodeTexNoise", noise_dimensions="4D" if w is not None else "3D")
        self.set(nd.inputs["Vector"], vec)
        self.set(nd.inputs["Scale"], scale)
        self.set(nd.inputs["Detail"], detail)
        self.set(nd.inputs["Roughness"], rough)
        self.set(nd.inputs["Distortion"], distortion)
        if w is not None:
            self.set(nd.inputs["W"], w)
        return nd.outputs[out]

    def out(self, surface=None, volume=None, displacement=None):
        o = self.node("ShaderNodeOutputMaterial", target="ALL")
        if surface is not None:
            self.set(o.inputs["Surface"], surface)
        if volume is not None:
            self.set(o.inputs["Volume"], volume)
        if displacement is not None:
            self.set(o.inputs["Displacement"], displacement)
        return o


def material(name):
    m = bpy.data.materials.new(name)
    if hasattr(m, "use_nodes") and not m.use_nodes:
        try:
            m.use_nodes = True
        except Exception:
            pass
    return m, Nodes(m.node_tree)


# ----------------------------------------------------------------- baking
def fcurve(idb, path, index=0):
    ad = idb.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(f"{idb.name}_act")
    return ad.action.fcurve_ensure_for_datablock(idb, path, index=index)


def bake(idb, path, frames, values, index=0, interp="LINEAR", eps=1e-6):
    """write one F-Curve from per-frame values, dropping keys a linear segment already reproduces"""
    pts = []
    k = len(frames)
    for i in range(k):
        if 0 < i < k - 1:
            a, b, c = values[i - 1], values[i], values[i + 1]
            if interp == "CONSTANT":
                if abs(b - a) < eps:
                    continue
            elif abs((a + c) / 2 - b) < eps and abs(c - a) < 1e3:
                fa, fb, fc = frames[i - 1], frames[i], frames[i + 1]
                if abs((fb - fa) - (fc - fb)) < 1e-9:
                    continue
        pts.append((frames[i], values[i]))
    fc = fcurve(idb, path, index)
    fc.keyframe_points.add(len(pts))
    fc.keyframe_points.foreach_set("co", [c for p in pts for c in p])
    code = {"LINEAR": 1, "CONSTANT": 0}[interp]
    fc.keyframe_points.foreach_set("interpolation", [code] * len(pts))
    fc.update()
    return len(pts)


def bake_vec(idb, path, frames, vecs, interp="LINEAR"):
    n = 0
    for i in range(len(vecs[0])):
        n += bake(idb, path, frames, [v[i] for v in vecs], i, interp)
    return n


def bake_visibility(ob, frames, visible):
    vals = [0.0 if v else 1.0 for v in visible]
    bake(ob, "hide_render", frames, vals, interp="CONSTANT")
    bake(ob, "hide_viewport", frames, vals, interp="CONSTANT")
