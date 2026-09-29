"""VIZ-64: Zielen nutzt auch den zweiten Weg (Pan+180, -Tilt) bzw. Pan+-360.

Frueher galt nur der erste Weg mit Pan in (-180, 180]; lag er ausserhalb
0..255, wurde abgeschnitten — der Strahl zeigte still daneben. Gemessen an
einem Geraet mit 330 Grad Pan und Nullpunkt 167,5: ueber ~+112 Grad
unerreichbar, obwohl der zweite Weg das Ziel trifft.

Treffer werden am AUFTREFFPUNKT gemessen: Vorwaertsrechnung mit derselben
Winkelformel wie das 3D (``einmessen._strahl``).
"""
import math
import random

from src.core.stage.aim import _aim_dmx, aim_pan_tilt, trace_pan_tilt, circle_points
from src.core.stage.einmessen import _strahl

ID = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _fehler_grad(pos, ziel, pan, tilt, kw):
    d = _strahl(ID, int(round(pan * 256)), int(round(tilt * 256)), kw)
    s = [ziel[i] - pos[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in s))
    cos = sum(d[i] * s[i] / n for i in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _alt(pos, ziel, kw):
    """Die Rechnung vor VIZ-64: nur der erste Weg, abgeschnitten."""
    dx, dy, dz = (ziel[i] - pos[i] for i in range(3))
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    lx, ly, lz = dx / n, dy / n, dz / n
    theta = math.acos(max(-1.0, min(1.0, -ly)))
    p = 0.0 if math.sin(theta) < 1e-6 else math.atan2(-lx, -lz)
    pan = kw["pan_zero_dmx"] + math.degrees(p) / (kw["pan_range_deg"] / 2) * 128
    tilt = kw["tilt_zero_dmx"] + math.degrees(theta) / (kw["tilt_range_deg"] / 2) * 128
    return (max(0.0, min(255.0, pan)), max(0.0, min(255.0, tilt)))


ASYM = dict(pan_range_deg=330.0, tilt_range_deg=270.0, pan_zero_dmx=167.5, tilt_zero_dmx=128.0)
SYM = dict(pan_range_deg=540.0, tilt_range_deg=270.0, pan_zero_dmx=128.0, tilt_zero_dmx=128.0)


def test_asymmetrischer_nullpunkt_trifft_jenseits_des_ersten_wegs():
    pos = (0.0, 5.0, 0.0)
    # Pan-Winkel ~150 Grad: auf dem ersten Weg DMX ~283 -> frueher auf 255 geklemmt
    ziel = (-5.0 * math.sin(math.radians(150)), 0.0, -5.0 * math.cos(math.radians(150)))
    alt = _alt(pos, ziel, ASYM)
    assert alt[0] == 255.0 and _fehler_grad(pos, ziel, *alt, ASYM) > 20, "Vorbedingung"
    pan, tilt = _aim_dmx(pos, ziel, **ASYM)
    assert 0.0 <= pan <= 255.0 and 0.0 <= tilt <= 255.0
    assert _fehler_grad(pos, ziel, pan, tilt, ASYM) < 0.01


def test_symmetrische_geraete_unveraendert():
    rnd = random.Random(64)
    pos = (0.0, 6.0, 0.0)
    for kw in (SYM, dict(SYM, pan_range_deg=360.0, tilt_range_deg=180.0)):
        for _ in range(400):
            ziel = (rnd.uniform(-10, 10), rnd.uniform(0, 5.5), rnd.uniform(-10, 10))
            assert _aim_dmx(pos, ziel, **kw) == _alt(pos, ziel, kw), (kw, ziel)


def test_ohne_aktuell_eindeutig():
    """Zielen und Einmessen rechnen den Soll unabhaengig — gleiche Eingabe,
    gleicher Weg."""
    pos, ziel = (0.0, 5.0, 0.0), (4.0, 0.0, 3.0)
    assert _aim_dmx(pos, ziel, **ASYM) == _aim_dmx(pos, ziel, **ASYM)


def test_nachfahren_schlaegt_nicht_um():
    """Kreis um den Kopf herum (kreuzt Pan +-180): 540-Grad-Geraet faehrt
    durch, statt mitten in der Figur um 360 Grad zurueckzuspringen."""
    pos = (0.0, 5.0, 0.0)
    pts = circle_points((0.0, 0.0, 0.0), 4.0, (0.0, 1.0, 0.0), count=72)
    folge = trace_pan_tilt(pos, pts, **SYM)
    spruenge = [abs(b[0] - a[0]) for a, b in zip(folge, folge[1:])]
    assert max(spruenge) <= 3, max(spruenge)
    for p, (pan, tilt) in zip(pts, folge):
        assert _fehler_grad(pos, p, pan, tilt, SYM) < 1.5   # 8-Bit-Rundung


def test_aktuell_waehlt_den_kuerzeren_weg():
    pos, ziel = (0.0, 5.0, 0.0), (0.0, 0.0, -4.0)   # vorn: Pan 0 Grad
    ohne = aim_pan_tilt(pos, ziel, **SYM)
    assert ohne[0] == 128
    # steht der Kopf schon bei +360 Grad (DMX ~213), bleibt er dort
    mit = aim_pan_tilt(pos, ziel, aktuell=(213, 180), **SYM)
    assert abs(mit[0] - 213) <= 1, mit
    assert _fehler_grad(pos, ziel, *mit, SYM) < 1.5
