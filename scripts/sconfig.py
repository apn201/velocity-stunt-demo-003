"""VELOCITY // STUNT DEMO 003: paths, format, palette, quality profiles. Pure Python, no bpy."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "output"

FPS = 24
SECONDS = 30.0
N = int(SECONDS * FPS)          # 720 frames
RES = (1920, 1080)
SEED = 3

# beauty is rendered up to the end card; the end card is HUD over black
END_CARD = 27.2                 # seconds


def hex_lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


PAL = {
    "red": hex_lin("#FF0033"),
    "cold": hex_lin("#E6F2FF"),
    "white": (1.0, 1.0, 1.0),
    "teal": hex_lin("#A5D8EB"),
    "paint": hex_lin("#E4E6E8"),
    "carbon": hex_lin("#141518"),
    "tarmac": hex_lin("#0B0B0C"),
    "concrete": hex_lin("#9C9D9B"),
    "steel": hex_lin("#3A3D40"),
    "sedan": hex_lin("#0E1A3A"),
    "crossover": hex_lin("#7A0A12"),
    "semi": hex_lin("#D8D8D6"),
    "stainless": hex_lin("#9A9C9E"),
}

PROFILES = {
    # engine, % resolution, samples
    "preview": {"engine": "EEVEE", "scale": 50, "samples": 16, "out": OUT / "preview"},
    # the final film is EEVEE: one Cycles frame with these volumes takes >10 min on a GTX 1660 Ti
    "final": {"engine": "EEVEE", "scale": 100, "samples": 96, "out": OUT / "beauty"},
    "cycles": {"engine": "CYCLES", "scale": 100, "samples": 96, "out": OUT / "beauty_cycles"},
    "cycles_preview": {"engine": "CYCLES", "scale": 50, "samples": 32, "out": OUT / "preview"},
}

MPH = 0.44704
FT = 0.3048
G = 9.81
