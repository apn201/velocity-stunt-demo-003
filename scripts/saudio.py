"""Generated soundtrack from the same simulation: no samples, no recordings.

Light contactors clunk on, the LEDs buzz, the motor whines with road speed, every
nozzle hisses with its own thrust, the lift jets roar on the floor, the landing
thumps and the launch booms. Car sounds fall off with the active camera's distance.
"""
import math
import wave

import numpy as np

import stimeline as T
from sconfig import END_CARD, FPS, N

SR = 48000


def _band(x, lo, hi, tilt=0.0):
    """shape white noise in the frequency domain (fast, zero phase)"""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.where((f >= lo) & (f <= hi), 1.0, 0.0)
    edge = 0.15
    g = np.clip((f - lo * (1 - edge)) / (lo * edge + 1e-9), 0, 1) * np.clip(((hi * (1 + edge)) - f) / (hi * edge), 0, 1)
    if tilt:
        g = g * np.power(np.maximum(f, 1.0) / 1000.0, tilt)
    y = np.fft.irfft(X * g, n=len(x))
    return y / (np.std(y) + 1e-12)


def _env(times, values, n):
    t = np.arange(n) / SR
    return np.interp(t, times, values)


def write(sim, vfx, cams, env, path):
    n = int(N / FPS * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(3)
    L = np.zeros(n)
    Rt = np.zeros(n)

    def add(sig, pan=0.0, gain=1.0):
        nonlocal L, Rt
        L += sig * gain * math.sqrt(0.5 * (1 - pan))
        Rt += sig * gain * math.sqrt(0.5 * (1 + pan))

    def hit(t0, freq, amp, decay, dur=1.5, pan=0.0, noise=0.0):
        i0 = int(t0 * SR)
        m = min(int(dur * SR), n - i0)
        if m <= 0:
            return
        tt = np.arange(m) / SR
        s = amp * np.sin(2 * math.pi * freq * tt * (1 + 0.6 * np.exp(-tt * 30))) * np.exp(-tt * decay)
        if noise:
            s += noise * rng.standard_normal(m) * np.exp(-tt * decay * 6)
        sig = np.zeros(n)
        sig[i0:i0 + m] = s
        add(sig, pan)

    # per-frame quantities at 48 kHz
    ft = np.array([(f - 1) / FPS for f in range(1, N + 2)])
    samples = [sim.frame(f) for f in range(1, N + 2)]
    speed = np.array([s["speed"] for s in samples])
    driven = np.array([1.0 if (s["mode"] == "track" and s["t"] >= T.T_GO) or (s["mode"] == "ground" and s["t"] >= T.T_LAUNCH)
                       else 0.0 for s in samples])
    from scams import SHOTS
    dist = []
    for f in range(1, N + 2):
        tt = (f - 1) / FPS
        d = 12.0
        for name, t0, t1, lens, fstop, kind in SHOTS:
            if t0 <= tt < t1:
                loc, _, _ = cams.rig(kind, tt, t0, t1)
                d = (cams.car_center(tt) - loc).length
        dist.append(d)
    dist = np.array(dist)
    near = 1.0 / (1.0 + dist / 10.0)
    k_near = _env(ft, near, n)
    k_speed = _env(ft, speed, n)
    k_drive = _env(ft, driven, n)
    live = (t < END_CARD).astype(float)

    # room tone
    add(_band(rng.standard_normal(n), 30, 400, -0.5) * 0.006)
    # uplight contactors, left to right across the stereo field
    for ld, lens, t_on, energy in env.lights:
        if lens is None:
            continue
        x = lens.parent.location.x
        pan = max(-0.8, min(0.8, (x + 25) / 40))
        hit(t_on, 52.0, 0.22, 14.0, 0.8, pan, noise=0.12)
    # LED buzz
    buzz = (np.sin(2 * math.pi * 100 * t) + 0.4 * np.sin(2 * math.pi * 200 * t) + 0.2 * np.sin(2 * math.pi * 300 * t))
    add(buzz * 0.006 * np.clip((t - 1.75) / 0.4, 0, 1) * live)
    # motor whine follows road speed while the wheels are driven; tyre roar with speed
    f_m = 120.0 + 52.0 * k_speed
    ph = 2 * math.pi * np.cumsum(f_m) / SR
    whine = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3.01 * ph)
    add(whine * 0.05 * k_drive * k_near * np.clip(k_speed / 3, 0, 1) * live)
    roar = _band(rng.standard_normal(n), 60, 900, -0.3)
    onfloor = _env(ft, np.array([1.0 if s["mode"] in ("track", "ground") else 0.0 for s in samples]), n)
    add(roar * 0.05 * np.clip(k_speed / 20, 0, 1) * onfloor * k_near * live)
    # thrusters: each nozzle's smoothed thrust drives a hiss; lift adds a floor roar
    hiss_l = _band(rng.standard_normal(n), 600, 14000, 0.2)
    hiss_r = _band(rng.standard_normal(n), 600, 14000, 0.2)
    rumble = _band(rng.standard_normal(n), 25, 260, -0.6)
    vt = np.array(vfx.ts)
    tot_l = np.zeros(len(vt))
    tot_r = np.zeros(len(vt))
    lift = np.zeros(len(vt))
    for name, nz in vfx.cars.nozzles.items():
        sig = np.array(vfx.sig[name])
        w = {"lift": 0.25, "retro": 0.35, "rear": 0.6, "side": 0.55}[nz["group"]]
        if name.endswith("L"):
            tot_l += w * sig
            tot_r += 0.6 * w * sig
        else:
            tot_r += w * sig
            tot_l += 0.6 * w * sig
        if nz["group"] == "lift":
            lift += sig / 4
    el = _env(vt, tot_l, n) * k_near * live
    er = _env(vt, tot_r, n) * k_near * live
    L += hiss_l * 0.11 * el
    Rt += hiss_r * 0.11 * er
    add(rumble * 0.16 * _env(vt, lift, n) * k_near * live)
    # landing and launch
    hit(sim.t_land, 42.0, 0.35, 7.0, 1.5, noise=0.05)
    hit(T.T_LAUNCH, 34.0, 0.7, 3.5, 2.5, noise=0.25)
    hit(T.T_LAUNCH + 0.02, 70.0, 0.25, 9.0, 1.0)
    # end card: a low note and one blip per stat row
    hit(END_CARD + 0.2, 55.0, 0.3, 1.2, 3.0)
    hit(END_CARD + 0.2, 82.4, 0.15, 1.4, 3.0)
    for i in range(5):
        hit(END_CARD + 0.45 + 0.12 * i, 880.0 + 60 * i, 0.06, 60.0, 0.2)

    st = np.stack([L, Rt], axis=1)
    peak = np.max(np.abs(st))
    st = st * (0.85 / peak if peak > 0.85 else 1.0)
    # gentle soft clip
    st = np.tanh(st * 1.1) / math.tanh(1.1)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return n / SR
