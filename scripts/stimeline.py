"""The stunt as a deterministic simulation. Pure Python, no bpy.

One integration at 480 Hz produces everything that moves: the car's pose, its
suspension and wheels, the thrust of every nozzle group, and the telemetry the HUD
shows. The car is driven along the ramp by arc length; after it leaves the inverted
lip it is a point mass under gravity plus thrust, flown by two PD controllers
(altitude and position) with saturated thrust, so the G numbers on screen are the
numbers that moved the car.
"""
import math

from sconfig import FPS, G, MPH, FT, N

# ----------------------------------------------------------------- set design
R = 8.0                 # quarter-pipe inner radius; the inverted lip is at 2R = 16 m (52.5 ft)
ROOF_L = 5.0            # inverted roof section past the top of the arc
RAMP_W = 5.2            # driving surface width
X_START = -28.0         # start line
WB = 2.62               # wheelbase
TRACK = 1.70            # wheel centre to wheel centre, across
WHEEL_R = 0.355

# ----------------------------------------------------------------- the run
T_GO = 4.2              # launch from the start line
A_DRIVE = 6.2           # m/s^2 on the approach
V_ENTRY = 14.0          # m/s into the curve (3.5 G at the bottom of the pipe)
V_TOP = 10.0            # m/s on the inverted lip (suction keeps it there)
ROLL_DELAY = 0.12       # s after leaving the lip
ROLL_DUR = 0.95         # s for 540 degrees (inverted -> upright, plus one full kickflip)
ROLL_TOTAL = 3 * math.pi
Z_HOVER = 6.5           # m (21.3 ft)
LIFT_MAX = 3.3 * G      # four underbody nozzles together
RETRO = 5.0             # m/s^2 horizontal braking in the air
T_DESC = 19.4
T_TOUCH = 22.0
T_LAUNCH = 24.4
A_LAUNCH = 31.0         # m/s^2: 0-60 mph in under a second

PHASES = [
    (0.0, "SYSTEMS CHECK"),
    (T_GO, "PHASE 1   RAMP DRIVE  /  SUCTION"),
    (None, "PHASE 2   INVERTED EJECTION  /  KICKFLIP"),   # start filled in at the lip exit
    (None, "PHASE 3   HOVER"),
    (T_DESC, "PHASE 3   CUSHION LANDING"),
    (T_LAUNCH - 1.2, "PHASE 4   LAUNCH"),
]

# side attitude bursts relative to the lip exit: (dt, duration, side +1 left / -1 right, amplitude)
SIDE_BURSTS = [(0.06, 0.16, 1, 1.0), (0.48, 0.10, 1, 0.8), (ROLL_DELAY + ROLL_DUR - 0.02, 0.14, -1, 1.0),
               (ROLL_DELAY + ROLL_DUR + 0.22, 0.08, -1, 0.5)]
# small trim puffs while hovering (absolute seconds)
TRIM_PUFFS = [(13.9, 0.07, 1, 0.45), (15.3, 0.06, -1, 0.4), (16.6, 0.08, 1, 0.5), (17.8, 0.06, -1, 0.35),
              (20.3, 0.06, 1, 0.35)]

DT = 1.0 / 480.0


# ----------------------------------------------------------------- small maths
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(u):
    u = clamp(u)
    return u * u * (3 - 2 * u)


def smoother(u):
    u = clamp(u)
    return u * u * u * (u * (6 * u - 15) + 10)


def q_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def q_axis(axis, ang):
    s = math.sin(ang / 2)
    return (math.cos(ang / 2), axis[0] * s, axis[1] * s, axis[2] * s)


def q_rot(q, v):
    w, x, y, z = q
    vx, vy, vz = v
    # v + 2w(q x v) + 2 q x (q x v)
    cx, cy, cz = y * vz - z * vy, z * vx - x * vz, x * vy - y * vx
    cx2, cy2, cz2 = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (vx + 2 * (w * cx + cx2), vy + 2 * (w * cy + cy2), vz + 2 * (w * cz + cz2))


def q_conj(q):
    return (q[0], -q[1], -q[2], -q[3])


def q_dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def q_slerp(a, b, u):
    d = q_dot(a, b)
    if d < 0:
        b = tuple(-x for x in b)
        d = -d
    if d > 0.9995:
        r = tuple(x + (y - x) * u for x, y in zip(a, b))
    else:
        th = math.acos(d)
        s = math.sin(th)
        r = tuple((math.sin((1 - u) * th) * x + math.sin(u * th) * y) / s for x, y in zip(a, b))
    n = math.sqrt(q_dot(r, r))
    return tuple(x / n for x in r)


def q_euler_zyx(q):
    """yaw, pitch, roll (Z, Y, X intrinsic) in radians"""
    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(clamp(2 * (w * y - z * x), -1, 1))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return yaw, pitch, roll


# ----------------------------------------------------------------- the ramp path
S0 = -X_START                       # arc length at the foot of the curve
S_ARC = S0 + math.pi * R
S_END = S_ARC + ROOF_L              # rear wheels leave the lip here


def path(s):
    """(x, z) on the driving surface at arc length s"""
    if s <= S0:
        return (X_START + s, 0.0)
    if s <= S_ARC:
        th = (s - S0) / R
        return (R * math.sin(th), R * (1 - math.cos(th)))
    return (-(s - S_ARC), 2 * R)


def track_pose(s):
    """car origin (contact plane, centred between axles) and orientation on the ramp"""
    xr, zr = path(s - WB / 2)
    xf, zf = path(s + WB / 2)
    fx, fz = xf - xr, zf - zr
    n = math.hypot(fx, fz)
    fx, fz = fx / n, fz / n
    ang = math.atan2(fz, fx)            # pitch of the forward vector in the XZ plane
    q = q_axis((0, 1, 0), -ang)
    return ((xr + xf) / 2, 0.0, (zr + zf) / 2), q


# ----------------------------------------------------------------- simulation
class Sim:
    def __init__(self):
        self.samples = []
        self._run()
        self._telemetry()

    def _run(self):
        t = 0.0
        s, v = 0.0, 0.0
        mode = "track"
        wheel = 0.0
        wheel_w = 0.0
        p = [0.0, 0.0, 0.0]
        vel = [0.0, 0.0, 0.0]
        susp, susp_v = 0.0, 0.0
        pitch_s, pitch_sv = 0.0, 0.0
        x_hold = None
        flare0 = None
        lift_prev = 0.0
        self.t_exit = None
        self.t_land = None
        self.t_060 = None
        self.max_alt = 0.0
        self.launch_x = None
        t_end = N / FPS + 0.5
        while t <= t_end:
            lift = retro = rear = 0.0
            onground = False
            if mode == "track":
                if t >= T_GO:
                    x_now, z_now = path(s)
                    if s < S0 - 3:
                        a = A_DRIVE * smooth((t - T_GO) / 0.35) * clamp((V_ENTRY - v) / 2.0)
                    else:
                        vt = V_ENTRY + (V_TOP - V_ENTRY) * (z_now / (2 * R))
                        a = 4.0 * (vt - v)
                    v += a * DT
                    s += v * DT
                pos, q = track_pose(s)
                vel = [0, 0, 0] if not self.samples else [(pos[i] - p[i]) / DT for i in range(3)]
                p = list(pos)
                wheel_w = v / WHEEL_R
                onground = True
                if s - WB / 2 >= S_END:
                    mode = "flight"
                    self.t_exit = t
                    vel = [-v, 0.0, 0.0]
                    q0 = q
            elif mode == "flight":
                te = t - self.t_exit
                # roll: eased 540 degrees with a small overshoot the side thrusters snap back
                u = (te - ROLL_DELAY) / ROLL_DUR
                phi = ROLL_TOTAL * smoother(u)
                if u > 1:
                    k = te - ROLL_DELAY - ROLL_DUR
                    phi += 0.14 * math.sin(k * 14) * math.exp(-k * 9)
                rolled = u >= 1
                yaw = pitch = wob = 0.0
                if rolled:
                    k = te - ROLL_DELAY - ROLL_DUR
                    fade = smooth(k / 1.5) * (1 - smooth((t - T_TOUCH + 1.6) / 1.2))   # level before touchdown
                    yaw = fade * (0.035 * math.sin(t * 0.9) + 0.015 * math.sin(t * 2.3 + 1))
                    pitch = fade * (0.020 * math.sin(t * 1.3 + 0.4) + 0.008 * math.sin(t * 3.1))
                    wob = fade * 0.012 * math.sin(t * 1.7 + 2)
                    q = q_mul(q_axis((0, 0, 1), math.pi + yaw), q_mul(q_axis((0, 1, 0), pitch), q_axis((1, 0, 0), wob + (phi - ROLL_TOTAL))))
                else:
                    q = q_mul(q0, q_axis((1, 0, 0), phi))
                up = q_rot(q, (0, 0, 1))
                # altitude: free fall until upright, then PD on a reference trajectory
                acc_z = -G
                if rolled:
                    zr, vzr, azr = self._zref(t)
                    cmd = G + azr + 16.0 * (zr - p[2]) + 8.0 * (vzr - vel[2])
                    lift = clamp(cmd / max(up[2], 0.3), 0.0, LIFT_MAX)
                    if p[2] <= 0.0 and t > T_DESC:
                        # touchdown
                        mode = "ground"
                        self.t_land = t
                        flare0 = lift_prev
                        susp_v = vel[2]
                        p[2] = 0.0
                        vel = [0.0, 0.0, 0.0]
                        x_land = p[0]
                        q_land = q
                        lift = flare0
                    lift_prev = lift
                if mode == "flight":
                    # horizontal: brake with the retro nozzles, then hold position
                    if te > 0.15:
                        if x_hold is None and vel[0] > -0.15:
                            x_hold = p[0]
                        if x_hold is None:
                            ax = RETRO
                        else:
                            ax = clamp(2.0 * (x_hold - p[0]) + 2.5 * (0 - vel[0]), -1.5, RETRO)
                        if ax >= 0:
                            retro = ax
                        else:
                            rear = -ax
                        vel[0] += ax * DT
                    acc_z += lift * up[2]
                    vel[2] += acc_z * DT
                    for i in range(3):
                        p[i] += vel[i] * DT
                    wheel_w *= math.exp(-DT / 2.5)
            elif mode == "ground":
                onground = True
                tl = t - self.t_land
                lift = flare0 * (1 - smooth(tl / 0.35))       # flare out the lift as the springs take the weight
                q = q_land
                if t >= T_LAUNCH:
                    tt = t - T_LAUNCH
                    if self.launch_x is None:
                        self.launch_x = p[0]
                    a = A_LAUNCH * smooth(tt / 0.06) * (1 - 0.35 * smooth((tt - 0.9) / 1.2))
                    rear = a
                    v = math.hypot(vel[0], vel[1])
                    v += a * DT
                    vel = [-v, 0.0, 0.0]
                    p[0] += vel[0] * DT
                    wheel_w = v / WHEEL_R
                    if self.t_060 is None and v >= 60 * MPH:
                        self.t_060 = tt
                    # squat
                    pitch_target = -0.022 * a / A_LAUNCH
                else:
                    pitch_target = 0.0
                    wheel_w = 0.0
                # suspension: damped springs on body heave and pitch
                f_load = (1 - lift / max(flare0, 1e-6)) if flare0 else 1.0
                susp_a = -150.0 * susp - 12.0 * susp_v - 0.025 * 150.0 * f_load
                susp_v += susp_a * DT
                susp += susp_v * DT
                pitch_sv += (-260.0 * (pitch_s - pitch_target) - 22.0 * pitch_sv) * DT
                pitch_s += pitch_sv * DT
            wheel += wheel_w * DT
            self.max_alt = max(self.max_alt, p[2])
            self.samples.append({
                "t": t, "pos": tuple(p), "q": q, "vel": tuple(vel), "wheel": wheel,
                "susp": (susp + 0.025 if mode == "ground" else
                         0.025 * smooth((t - self.t_exit) / 0.3) if mode == "flight" else 0.0),   # 0 = static ride height
                "pitch_s": pitch_s, "lift": lift / LIFT_MAX, "retro": retro / RETRO,
                "rear": rear / A_LAUNCH if mode == "ground" else rear / 1.5 * 0.25,
                "onground": onground, "mode": mode, "speed": math.sqrt(sum(c * c for c in vel)),
            })
            t += DT
        self.t_roll_end = self.t_exit + ROLL_DELAY + ROLL_DUR
        self.side_bursts = [(self.t_exit + dt, d, side, a) for dt, d, side, a in SIDE_BURSTS] + TRIM_PUFFS

    def _zref(self, t):
        """altitude reference (z, z', z'') after the roll"""
        if t < T_DESC:
            b = 0.10 * math.sin((t - T_DESC) * 1.1)
            bv = 0.11 * math.cos((t - T_DESC) * 1.1)
            return Z_HOVER + b, bv, 0.0
        D = T_TOUCH - T_DESC
        if t < T_TOUCH:
            u = (t - T_DESC) / D
            h00, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - u ** 2
            d00, d11 = (6 * u ** 2 - 6 * u) / D, (3 * u ** 2 - 2 * u) / D
            a00, a11 = (12 * u - 6) / D ** 2, (6 * u - 2) / D ** 2
            vt = -0.45
            return h00 * Z_HOVER + h11 * D * vt, d00 * Z_HOVER + d11 * D * vt, a00 * Z_HOVER + a11 * D * vt
        return -0.45 * (t - T_TOUCH), -0.45, 0.0

    # ------------------------------------------------------------- telemetry
    def _telemetry(self):
        sm = self.samples
        n = len(sm)
        gx = [0.0] * n
        gz = [0.0] * n
        for i in range(1, n - 1):
            a = [(sm[i + 1]["vel"][k] - sm[i - 1]["vel"][k]) / (2 * DT) for k in range(3)]
            # positions on the track give velocity by differencing; use positions there
            if sm[i]["mode"] == "track":
                a = [(sm[i + 1]["pos"][k] - 2 * sm[i]["pos"][k] + sm[i - 1]["pos"][k]) / DT ** 2 for k in range(3)]
            a[2] += G                               # proper acceleration (what an accelerometer reads)
            qc = q_conj(sm[i]["q"])
            al = q_rot(qc, a)
            gx[i] = al[0] / G
            gz[i] = al[2] / G
        gx[0], gz[0] = gx[1], gz[1] = 0.0, 1.0
        gx[-1], gz[-1] = gx[-2], gz[-2]
        # 12 Hz sensor filter
        k = 1 - math.exp(-DT * 2 * math.pi * 6)
        fx, fz = 0.0, 1.0
        self.peak_g = 0.0
        for i in range(n):
            fx += (gx[i] - fx) * k
            fz += (gz[i] - fz) * k
            sm[i]["g_long"] = fx
            sm[i]["g_norm"] = fz
            sm[i]["g"] = math.hypot(fx, fz)
            self.peak_g = max(self.peak_g, sm[i]["g"])

    # ------------------------------------------------------------- sampling
    def at(self, t):
        i = clamp(t / DT, 0, len(self.samples) - 1.001)
        i0 = int(i)
        u = i - i0
        a, b = self.samples[i0], self.samples[i0 + 1]
        out = {}
        for key, va in a.items():
            vb = b[key]
            if key == "q":
                out[key] = q_slerp(va, vb, u)
            elif isinstance(va, tuple):
                out[key] = tuple(x + (y - x) * u for x, y in zip(va, vb))
            elif isinstance(va, (bool, str)):
                out[key] = va
            else:
                out[key] = va + (vb - va) * u
        return out

    def frame(self, f):
        return self.at((f - 1) / FPS)

    def phase(self, t):
        starts = [p[0] for p in PHASES]
        starts[2] = self.t_exit
        starts[3] = self.t_roll_end + 0.9
        idx = 0
        for i, s0 in enumerate(starts):
            if t >= s0:
                idx = i
        return idx

    def phase_starts(self):
        starts = [p[0] for p in PHASES]
        starts[2] = self.t_exit
        starts[3] = self.t_roll_end + 0.9
        return starts

    def side(self, t):
        """side attitude thrust per side (+1 left, -1 right), 0..1"""
        left = right = 0.0
        for t0, d, side, a in self.side_bursts:
            if t0 <= t < t0 + d:
                env = a * smooth((t - t0) / 0.02) * (1 - smooth((t - t0 - d + 0.03) / 0.03))
                if side > 0:
                    left = max(left, env)
                else:
                    right = max(right, env)
        return left, right

    def summary(self):
        return {"t_exit": self.t_exit, "t_roll_end": self.t_roll_end, "t_land": self.t_land,
                "t_060": self.t_060, "peak_g": self.peak_g, "max_alt_ft": self.max_alt / FT,
                "hover_ft": Z_HOVER / FT, "launch_x": self.launch_x}


if __name__ == "__main__":
    sim = Sim()
    print(sim.summary())
    for tt in (0, 4.2, 6, 7.5, 8.5, 9.5, 10, 10.5, 11, 11.5, 12, 13, 15, 19.4, 21, 22, 23, 24.4, 25, 26):
        s = sim.at(tt)
        print(f"t={tt:5.2f} {s['mode']:6s} pos=({s['pos'][0]:7.2f},{s['pos'][2]:6.2f}) v={s['speed']:5.1f} "
              f"g={s['g']:4.2f} lift={s['lift']:.2f} retro={s['retro']:.2f} rear={s['rear']:.2f} "
              f"susp={s['susp']:.3f} ypr={[round(math.degrees(a), 1) for a in q_euler_zyx(s['q'])]}")
