"""Every material, built from shader nodes. No image textures anywhere."""
from sbl import material
from sconfig import PAL


def _bsdf(n, **kw):
    names = {"base": "Base Color", "metal": "Metallic", "rough": "Roughness", "coat": "Coat Weight",
             "coat_rough": "Coat Roughness", "aniso": "Anisotropic", "aniso_rot": "Anisotropic Rotation",
             "spec": "Specular IOR Level", "normal": "Normal", "coat_normal": "Coat Normal",
             "emit": "Emission Color", "emit_s": "Emission Strength", "alpha": "Alpha",
             "film": "Thin Film Thickness", "sheen": "Sheen Weight", "ior": "IOR",
             "transmission": "Transmission Weight", "coat_tint": "Coat Tint"}
    inputs = {}
    for k, v in kw.items():
        if isinstance(v, tuple) and len(v) == 3:
            v = (*v, 1.0)
        inputs[names[k]] = v
    return n.node("ShaderNodeBsdfPrincipled", inputs)


def _bump(n, height, strength, dist=1.0, normal=None):
    inputs = {"Height": height, "Strength": strength, "Distance": dist}
    if normal is not None:
        inputs["Normal"] = normal
    return n.node("ShaderNodeBump", inputs).outputs["Normal"]


class Mats:
    def __init__(self):
        self.paint = self.car_paint("paint", PAL["paint"], rough=0.30, metal=0.45, film=180.0)
        self.carbon = self.carbon_mat()
        self.glass = self.glass_mat()
        self.tire = self.rubber()
        self.cover = self.aerocover()
        self.rim = self.simple("rim_black", (0.012, 0.012, 0.013), metal=0.6, rough=0.28)
        self.nozzle = self.simple("nozzle_metal", (0.05, 0.05, 0.055), metal=1.0, rough=0.35)
        self.well = self.simple("wheel_well", (0.006, 0.006, 0.006), rough=0.9)
        self.headlamp = self.emit("headlamp", PAL["cold"], 60.0)
        self.lightbar = self.emit("lightbar", PAL["cold"], 90.0)
        self.taillamp = self.emit("taillamp", PAL["red"], 40.0)
        self.lamp_housing = self.simple("lamp_housing", (0.01, 0.01, 0.012), metal=0.9, rough=0.12)
        self.tarmac = self.tarmac_mat()
        self.concrete = self.concrete_mat()
        self.steel = self.steel_mat()
        self.ramp_edge = self.simple("ramp_edge", (0.03, 0.03, 0.032), metal=0.8, rough=0.4)
        self.led = self.emit_prop("led_red", PAL["red"], 28.0, "on")
        self.lens = self.emit_prop("uplight_lens", PAL["cold"], 400.0, "on")
        self.fixture = self.simple("fixture", (0.02, 0.02, 0.022), metal=0.7, rough=0.45)
        self.platform = self.simple("platform", (0.012, 0.012, 0.013), metal=0.0, rough=0.18, coat=1.0)
        self.footing = self.concrete_plain()
        self.sedan = self.car_paint("paint_sedan", PAL["sedan"], rough=0.22, metal=0.7)
        self.crossover = self.car_paint("paint_crossover", PAL["crossover"], rough=0.22, metal=0.6)
        self.semi = self.car_paint("paint_semi", PAL["semi"], rough=0.25, metal=0.2)
        self.stainless = self.brushed("stainless", PAL["stainless"])
        self.softbox = self.emit("softbox", PAL["cold"], 6.0)
        self.plume = self.plume_mat()
        self.puff = self.puff_mat()
        self.ring = self.ring_mat()
        self.fog = self.fog_mat()

    # ------------------------------------------------------------ surfaces
    def simple(self, name, col, metal=0.0, rough=0.5, coat=0.0):
        m, n = material(name)
        n.out(_bsdf(n, base=col, metal=metal, rough=rough, coat=coat))
        return m

    def car_paint(self, name, col, rough=0.3, metal=0.4, film=0.0):
        """satin pearl: metallic base with anisotropic highlights under a soft clear coat"""
        m, n = material(name)
        co = n.coords("Object")
        flake = n.noise(co, 900.0, detail=1.0, rough=0.5)
        nrm = _bump(n, flake, 0.025, 0.002)
        tint = n.ramp(n.noise(co, 1.6, detail=2.0), [(0.3, tuple(c * 0.96 for c in col)), (0.7, col)])
        kw = dict(base=tint, metal=metal, rough=rough, aniso=0.55, aniso_rot=0.25, coat=0.85,
                  coat_rough=0.11, normal=nrm, spec=0.55)
        if film:
            kw["film"] = film
        n.out(_bsdf(n, **kw))
        return m

    def carbon_mat(self):
        m, n = material("carbon")
        uv = n.coords("Object")
        weave = n.node("ShaderNodeTexChecker", {"Vector": uv, "Scale": 160.0,
                                                "Color1": (1, 1, 1, 1), "Color2": (0, 0, 0, 1)}).outputs["Fac"]
        rough = n.maprange(weave, 0, 1, 0.42, 0.56)
        n.out(_bsdf(n, base=PAL["carbon"], metal=0.15, rough=rough, coat=0.25, coat_rough=0.35,
                    aniso=0.6, normal=_bump(n, weave, 0.05, 0.001)))
        return m

    def glass_mat(self):
        m, n = material("glass_flush")
        n.out(_bsdf(n, base=(0.004, 0.0045, 0.005), metal=0.0, rough=0.025, coat=1.0, coat_rough=0.0, spec=0.7))
        return m

    def rubber(self):
        m, n = material("tire")
        co = n.coords("Object")
        rough = n.maprange(n.noise(co, 60.0), 0.3, 0.7, 0.62, 0.85)
        n.out(_bsdf(n, base=(0.018, 0.018, 0.019), rough=rough, normal=_bump(n, n.noise(co, 300.0), 0.08, 0.002)))
        return m

    def aerocover(self):
        """matte silver disc; five thin dark slots so the spin reads on camera"""
        m, n = material("aerocover")
        co = n.coords("Object")
        x, _, z = n.xyz(co)
        ang = n.math("ARCTAN2", z, x)
        slot = n.math("FRACT", n.math("MULTIPLY", ang, 5 / 6.28318))
        r = n.vmath("LENGTH", n.combine(x, 0.0, z))
        band = n.math("MULTIPLY", n.maprange(r, 0.10, 0.11), n.maprange(r, 0.26, 0.25))
        line = n.math("MULTIPLY", n.maprange(slot, 0.0, 0.025, 1.0, 0.0), band)
        hub = n.maprange(r, 0.045, 0.05, 1.0, 0.0)
        dark = n.math("MAXIMUM", line, hub)
        col = n.ramp(dark, [(0.0, (0.55, 0.56, 0.57)), (1.0, (0.015, 0.015, 0.016))])
        rough = n.maprange(dark, 0, 1, 0.38, 0.3)
        n.out(_bsdf(n, base=col, metal=1.0, rough=rough))
        return m

    def brushed(self, name, col):
        m, n = material(name)
        co = n.coords("Object")
        x, y, z = n.xyz(co)
        streak = n.noise(n.combine(n.math("MULTIPLY", x, 2.0), n.math("MULTIPLY", y, 400.0),
                                   n.math("MULTIPLY", z, 400.0)), 1.0, detail=3.0)
        rough = n.maprange(streak, 0.3, 0.7, 0.22, 0.34)
        n.out(_bsdf(n, base=col, metal=1.0, rough=rough, aniso=0.8))
        return m

    def emit(self, name, col, strength):
        m, n = material(name)
        n.out(n.node("ShaderNodeEmission", {"Color": (*col, 1.0), "Strength": strength}))
        return m

    def emit_prop(self, name, col, strength, prop):
        """emission scaled by an animated object property (lights booting up)"""
        m, n = material(name)
        s = n.math("MULTIPLY", n.attr(prop), strength)
        n.out(n.node("ShaderNodeEmission", {"Color": (*col, 1.0), "Strength": s}))
        return m

    def tarmac_mat(self):
        """black asphalt: aggregate bump, puddles where a large-scale noise dips (glossy, darker)"""
        m, n = material("tarmac")
        p = n.node("ShaderNodeNewGeometry").outputs["Position"]
        wet = n.maprange(n.noise(p, 0.045, detail=5.0, rough=0.6), 0.57, 0.62)
        grain = n.node("ShaderNodeTexVoronoi", {"Vector": p, "Scale": 140.0}).outputs["Distance"]
        fine = n.noise(p, 600.0, detail=2.0)
        h = n.math("ADD", n.math("MULTIPLY", grain, 0.6), n.math("MULTIPLY", fine, 0.4))
        dry_bump = n.math("MULTIPLY", h, n.math("SUBTRACT", 1.0, wet))
        nrm = _bump(n, dry_bump, 0.35, 0.003)
        rough = n.maprange(wet, 0, 1, 0.62, 0.04)
        rough = n.math("ADD", rough, n.math("MULTIPLY", fine, 0.12))
        col = n.ramp(n.math("ADD", n.math("MULTIPLY", grain, 0.5), n.math("MULTIPLY", wet, 0.6)),
                     [(0.0, (0.020, 0.020, 0.021)), (0.5, (0.011, 0.011, 0.012)), (1.0, (0.004, 0.004, 0.0045))])
        n.out(_bsdf(n, base=col, rough=rough, normal=nrm, spec=0.5))
        return m

    def concrete_mat(self):
        """modular panels from the UV (metres): 2.0 m along, 1.3 m across; painted centre lane line"""
        m, n = material("ramp_concrete")
        uv = n.coords("UV")
        u, v, _ = n.xyz(uv)
        fu = n.math("FRACT", n.math("DIVIDE", u, 2.0))
        fv = n.math("FRACT", n.math("DIVIDE", n.math("ADD", v, 2.6), 1.3))
        gu = n.math("MULTIPLY", n.maprange(fu, 0.0, 0.006, 1, 0), 1.0)
        gu = n.math("MAXIMUM", gu, n.maprange(fu, 0.994, 1.0, 0, 1))
        gv = n.math("MAXIMUM", n.maprange(fv, 0.0, 0.008, 1, 0), n.maprange(fv, 0.992, 1.0, 0, 1))
        grout = n.math("MAXIMUM", gu, gv)
        p = n.coords("Object")
        blotch = n.noise(p, 0.9, detail=6.0, rough=0.65)
        pores = n.noise(p, 180.0, detail=2.0)
        av = n.math("ABSOLUTE", v)
        wear = n.noise(p, 9.0, detail=4.0)
        lane = n.math("MULTIPLY", n.maprange(av, 0.085, 0.075), n.maprange(wear, 0.28, 0.4))
        # tyre polish along the two wheel paths
        track = n.maprange(n.math("ABSOLUTE", n.math("SUBTRACT", av, 0.85)), 0.28, 0.0)
        base = n.ramp(blotch, [(0.25, tuple(c * 0.72 for c in PAL["concrete"])), (0.75, PAL["concrete"])])
        col = n.node("ShaderNodeMix", data_type="RGBA")
        n.set(col.inputs[0], lane)
        n.set(col.inputs[6], base)
        n.set(col.inputs[7], (0.85, 0.85, 0.83, 1.0))
        col2 = n.node("ShaderNodeMix", data_type="RGBA")
        n.set(col2.inputs[0], n.math("MULTIPLY", grout, 0.85))
        n.set(col2.inputs[6], col.outputs[2])
        n.set(col2.inputs[7], (0.02, 0.02, 0.02, 1.0))
        rough = n.math("SUBTRACT", n.maprange(pores, 0.3, 0.7, 0.62, 0.82), n.math("MULTIPLY", track, 0.25))
        h = n.math("SUBTRACT", n.math("MULTIPLY", pores, 0.3), n.math("MULTIPLY", grout, 1.0))
        n.out(_bsdf(n, base=col2.outputs[2], rough=rough, normal=_bump(n, h, 0.4, 0.004)))
        return m

    def concrete_plain(self):
        m, n = material("footing")
        p = n.coords("Object")
        col = n.ramp(n.noise(p, 2.0, detail=6.0), [(0.3, (0.08, 0.08, 0.08)), (0.7, (0.14, 0.14, 0.135))])
        n.out(_bsdf(n, base=col, rough=0.8, normal=_bump(n, n.noise(p, 120.0), 0.3, 0.003)))
        return m

    def steel_mat(self):
        m, n = material("truss_steel")
        p = n.coords("Object")
        grime = n.noise(p, 3.0, detail=6.0, rough=0.6)
        col = n.ramp(grime, [(0.35, tuple(c * 0.6 for c in PAL["steel"])), (0.7, PAL["steel"])])
        rough = n.maprange(grime, 0.3, 0.7, 0.55, 0.35)
        n.out(_bsdf(n, base=col, metal=0.9, rough=rough))
        return m

    # ------------------------------------------------------------ volumes
    def plume_mat(self):
        """cold-gas plume on a unit cone (nozzle at z=0, r=0.08 -> 1 at z=1).
        Object props: thrust (0..1+), flow (advected noise offset), seed."""
        m, n = material("vfx_plume")
        co = n.coords("Object")
        x, y, z = n.xyz(co)
        r = n.vmath("LENGTH", n.combine(x, y, 0.0))
        rz = n.math("ADD", 0.08, n.math("MULTIPLY", z, 0.92))
        rr = n.math("DIVIDE", r, rz)
        flow = n.attr("flow")
        seed = n.attr("seed")
        adv = n.combine(n.math("MULTIPLY", x, 1.6), n.math("MULTIPLY", y, 1.6),
                        n.math("SUBTRACT", n.math("MULTIPLY", z, 6.0), flow))
        warp = n.noise(adv, 1.3, detail=2.0, w=seed, out="Color")
        adv2 = n.vmath("ADD", adv, n.vmath("SCALE", warp, scale=0.9))
        turb = n.noise(adv2, 2.4, detail=6.0, rough=0.62, w=seed)
        edge = n.math("ADD", 0.55, n.math("MULTIPLY", n.math("SUBTRACT", turb, 0.5), 1.1))
        prof = n.maprange(rr, edge, n.math("MULTIPLY", edge, 0.35), 0.0, 1.0, interp="SMOOTHSTEP")
        ax = n.math("MULTIPLY", n.maprange(z, 0.0, 0.03), n.maprange(z, 1.0, 0.45, 0.0, 1.0, interp="SMOOTHSTEP"))
        core = n.maprange(z, 0.25, 0.0, 1.0, 3.0)
        d = n.math("MULTIPLY", n.math("MULTIPLY", prof, ax), n.math("MULTIPLY", core, n.attr("thrust")))
        d = n.math("MULTIPLY", d, n.maprange(turb, 0.25, 0.75, 0.35, 1.6))
        dens = n.math("MULTIPLY", d, 22.0)
        col = n.ramp(n.maprange(z, 0.0, 0.3), [(0.0, PAL["teal"]), (1.0, (0.92, 0.94, 0.96))])
        emit_s = n.math("MULTIPLY", d, n.maprange(z, 0.6, 0.0, 0.25, 1.2))
        vol = n.node("ShaderNodeVolumePrincipled", {"Color": col, "Density": dens, "Anisotropy": 0.35,
                                                    "Emission Color": (*PAL["teal"], 1.0), "Emission Strength": emit_s})
        n.out(volume=vol)
        return m

    def puff_mat(self):
        """detached vapour cloud on a unit sphere; props dens, flow, seed"""
        m, n = material("vfx_puff")
        co = n.coords("Object")
        r = n.vmath("LENGTH", co)
        seed = n.attr("seed")
        flow = n.attr("flow")
        warp = n.noise(n.vmath("SCALE", co, scale=1.2), 1.0, detail=2.0, w=n.math("ADD", seed, flow), out="Color")
        p2 = n.vmath("ADD", co, n.vmath("SCALE", n.vmath("SUBTRACT", warp, (0.5, 0.5, 0.5)), scale=1.1))
        turb = n.noise(p2, 2.2, detail=6.0, rough=0.6, w=n.math("ADD", seed, n.math("MULTIPLY", flow, 0.5)))
        edge = n.math("ADD", 0.2, n.math("MULTIPLY", turb, 0.95))
        prof = n.maprange(r, edge, n.math("MULTIPLY", edge, 0.15), 0.0, 1.0, interp="SMOOTHSTEP")
        fine = n.noise(n.vmath("SCALE", p2, scale=3.0), 3.0, detail=4.0, w=seed)
        prof = n.math("MULTIPLY", prof, n.maprange(fine, 0.35, 0.65, 0.25, 1.0))
        dens = n.math("MULTIPLY", n.math("MULTIPLY", prof, n.attr("dens")), n.maprange(turb, 0.3, 0.7, 0.4, 1.5))
        vol = n.node("ShaderNodeVolumePrincipled", {"Color": (0.9, 0.92, 0.94, 1.0),
                                                    "Density": n.math("MULTIPLY", dens, 6.0), "Anisotropy": 0.3})
        n.out(volume=vol)
        return m

    def ring_mat(self):
        """ground-hugging radial fog on a unit cylinder (r<=1, 0<=z<=1); props dens, inner, flow, seed"""
        m, n = material("vfx_ring")
        co = n.coords("Object")
        x, y, z = n.xyz(co)
        r = n.vmath("LENGTH", n.combine(x, y, 0.0))
        seed = n.attr("seed")
        flow = n.attr("flow")
        inner = n.attr("inner")
        warp = n.noise(n.combine(x, y, n.math("MULTIPLY", z, 0.5)), 1.6, detail=2.0, w=seed, out="Color")
        p2 = n.vmath("ADD", co, n.vmath("SCALE", n.vmath("SUBTRACT", warp, (0.5, 0.5, 0.5)), scale=0.5))
        turb = n.noise(n.vmath("MULTIPLY", p2, (3.0, 3.0, 1.5)), 2.0, detail=6.0, rough=0.62,
                       w=n.math("ADD", seed, flow))
        rn = n.math("ADD", r, n.math("MULTIPLY", n.math("SUBTRACT", turb, 0.5), 0.35))
        band = n.math("MULTIPLY", n.maprange(rn, n.math("SUBTRACT", inner, 0.25), inner, 0.0, 1.0, interp="SMOOTHSTEP"),
                      n.maprange(rn, 1.0, 0.72, 0.0, 1.0, interp="SMOOTHSTEP"))
        roll = n.math("ADD", 0.25, n.math("MULTIPLY", n.math("SUBTRACT", rn, inner), 0.9))
        hgt = n.maprange(n.math("SUBTRACT", z, n.math("MULTIPLY", turb, 0.25)), roll, 0.0, 0.0, 1.0, interp="SMOOTHSTEP")
        dens = n.math("MULTIPLY", n.math("MULTIPLY", band, hgt), n.attr("dens"))
        dens = n.math("MULTIPLY", dens, n.maprange(turb, 0.3, 0.7, 0.3, 1.6))
        vol = n.node("ShaderNodeVolumePrincipled", {"Color": (0.9, 0.92, 0.94, 1.0),
                                                    "Density": n.math("MULTIPLY", dens, 5.0), "Anisotropy": 0.3})
        n.out(volume=vol)
        return m

    def fog_mat(self):
        """arena haze: thin everywhere (so the uplight beams show), thicker at shoe height"""
        m, n = material("vfx_haze")
        p = n.node("ShaderNodeNewGeometry").outputs["Position"]
        _, _, z = n.xyz(p)
        slow = n.noise(p, 0.06, detail=3.0)
        ground = n.math("MULTIPLY", n.math("EXPONENT", n.math("MULTIPLY", z, -7.0)),
                        n.maprange(n.noise(p, 0.25, detail=4.0), 0.35, 0.7, 0.0, 1.0))
        haze = n.math("MULTIPLY", n.maprange(slow, 0.3, 0.7, 0.5, 1.4), n.attr("haze"))
        dens = n.math("ADD", haze, n.math("MULTIPLY", ground, n.attr("ground")))
        vol = n.node("ShaderNodeVolumePrincipled", {"Color": (0.85, 0.88, 0.92, 1.0), "Density": dens,
                                                    "Anisotropy": 0.55})
        n.out(volume=vol)
        return m
