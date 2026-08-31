"""Test-Show fuer ZWEI Varytec Hero Spot 90 (David, 26.08.2026).

Zweck: Bewegung, Optik und vor allem das ZIELEN am echten Geraet pruefen —
und zwar den Unterschied, um den es wirklich geht:

    PARALLEL  = beide Koepfe bekommen DIESELBEN Pan/Tilt-Werte.
                Die Strahlen laufen parallel, treffen also NICHT denselben Punkt.
    ABSOLUT   = beide zeigen auf denselben PUNKT IM RAUM.
                Weil die Koepfe 4 m auseinander haengen, braucht jeder dafuer
                ANDERE Werte — ausgerechnet mit src/core/stage/aim.py.

Genau dieser Vergleich ist der Test: stehen die Lichtflecken bei "absolut"
uebereinander und bei "parallel" nebeneinander, stimmt die Kinematik. Das ist
zugleich die Hardware-Verifikation, die als HW-1/HW-4 seit Wochen aussteht.

Aufruf (isoliert, ruehrt data/current_show.db NICHT an — _gen_env sorgt dafuer):
    venv/bin/python tools/build_spot90_testshow.py
Ergebnis: shows/Spot90_Testshow.lshow
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter VOR app_state
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.models import PatchedFixture
from src.core.engine.function_manager import get_function_manager
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.stage.aim import aim_pan_tilt
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_xypad import VCXYPad

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Spot90_Testshow.lshow")

# ── Geraet ───────────────────────────────────────────────────────────────────
# Profil 1698 = Varytec "Hero Spot 90" (Quelle qlcplus). Bewusst der GROESSTE
# Modus: 16-Bit-Pan/Tilt zahlt sich beim Zielen unmittelbar aus.
PROFIL, MODUS, N_KANAELE = 1698, "16 Channel", 16
# Physischer Bewegungsbereich. 540/270 ist der uebliche Wert dieser Klasse und
# zugleich der Repo-Default (app_state: pan_range_deg=540). Stimmt er am Geraet
# nicht, sieht man es SOFORT an dieser Show — die absoluten Ziele treffen dann
# gemeinsam daneben statt auseinander. Das ist ein Feature dieses Tests.
PAN_RANGE, TILT_RANGE = 330.0, 260.0   # EINGEMESSEN (nicht 540/270!)

# ── Davids echte Aufstellung (gemessen 26.08.2026) ───────────────────────────
# Beide Geraete STEHEN vor einer Wand, Linse ~0,50 m ueber dem Boden, 2,50 m von
# der Wand entfernt, 0,60 m auseinander, beide in dieselbe Richtung.
#
# Nullpunkt: Boden, MITTIG zwischen den beiden Koepfen. x nach rechts, y nach
# oben, z zur Wand. So muss nur Abstand und Hoehe gemessen werden, nichts
# absolut eingemessen.
KOPF_ABSTAND = 0.64          # nachgemessen, Linsenmitte zu Linsenmitte
LINSEN_HOEHE = 0.50
WAND_Z       = 2.50

# ★★ EINGEMESSEN AM ECHTEN RIG (26.08.2026, drei Zielpunkte, 12 Messwerte).
# fid 1 ("MH Links") steht PHYSISCH RECHTS — die Zuordnung war vertauscht. Das
# ist nicht geraten: die Ausgleichsrechnung ueber alle drei Punkte liefert fuer
# die vertauschte Variante RMS 2.87 DMX gegen 5.91 fuer die nicht vertauschte.
# Hoehenversatz aus der Tilt-Differenz: fid 1 steht 14 cm TIEFER.
HOEHEN_VERSATZ = 0.14
POS = {1: ( KOPF_ABSTAND / 2, LINSEN_HOEHE - HOEHEN_VERSATZ / 2, 0.0),
       2: (-KOPF_ABSTAND / 2, LINSEN_HOEHE + HOEHEN_VERSATZ / 2, 0.0)}

# ★ STEHEND, nicht haengend — das ist der Unterschied, an dem die ganze
# Rechnung haengt. aim.py nimmt als Ruhelage (pan=tilt=128) "Strahl senkrecht
# NACH UNTEN" an, also ein haengendes Geraet. Ein stehendes ist demgegenueber um
# 180 Grad gekippt. Nachgerechnet: haengend ergaebe fuer die Wandmitte
# pan 53/203 und tilt 233 (weit auseinander, nahe am Anschlag), stehend
# pan 118/138 und tilt 194 — leicht zur Mitte geneigt und symmetrisch um 128.
ROT = {1: (180.0, 0.0, 0.0), 2: (180.0, 0.0, 0.0)}

# ★★ Die Nullpunkte waren der eigentliche Fehler, nicht die Bereiche.
# Angenommen war jeweils 128 (Mitte des DMX-Bereichs). Gemessen:
#   Pan-Null  168  und Pan INVERTIERT
#   Tilt-Null 144
# Die Bereiche 540/270 haben sich dagegen bestaetigt: eine freie Anpassung
# ergab 580/250 bei RMS 2.73 gegen 2.82 mit 540/270 — der Unterschied liegt im
# Rauschen, also bleiben die Datenblatt-Werte stehen statt einer erfundenen Zahl.
PAN_ZERO, TILT_ZERO = 167.5, 141.0
INVERT_PAN, INVERT_TILT = True, False

# Zielpunkte AN DER WAND (nicht am Boden): bei 0,50 m Aufbauhoehe sieht man
# dort ungleich mehr, und der Versatz zwischen "parallel" und "gleicher Punkt"
# entspricht genau dem Kopfabstand von 0,60 m.
# Zielpunkte an der Wand. "Mitte" und "hoch" sind genau die Punkte, die David
# beim Einmessen angefahren hat — damit ist sofort pruefbar, ob die Kalibrierung
# stimmt: der Strahl muss wieder dorthin treffen.
# "Mitte" ist der live eingemessene Punkt — er MUSS sitzen. Die anderen drei
# sind die eigentliche Pruefung: sie stammen aus derselben Rechnung, wurden
# aber nie angefahren. Treffen sie, ist das Modell richtig und nicht nur an
# einen Punkt angepasst.
ZIELE = [
    ("Wand Mitte",  (0.0, 1.10, WAND_Z)),
    ("Wand hoch",   (0.0, 1.85, WAND_Z)),
    ("Wand links",  (-1.50, 1.10, WAND_Z)),
    ("Wand rechts", (1.50, 1.10, WAND_Z)),
]

state = get_state()
fm = get_function_manager()

# ── 1) Patch ─────────────────────────────────────────────────────────────────
# ★ Das Universum wird ABGELEITET, nicht geraten. Beim ersten Lauf lag der
# Patch auf Universum 1, waehrend der Enttec auf 3 konfiguriert war — die Koepfe
# blieben stumm, obwohl Adapter, Rechte und Geraeteauswahl alle stimmten. Ein
# Patch auf einem Universum ohne Ausgang sieht in der App voellig normal aus;
# man merkt es erst am schweigenden Rig. Deshalb nimmt der Bauer das erste
# Universum, das in data/universes.json wirklich einen Ausgang hat.
def _universum_mit_ausgang(vorgabe: int = 1) -> int:
    import json as _j
    pfad = os.path.join(_ROOT, "data", "universes.json")
    try:
        with open(pfad, encoding="utf-8") as fh:
            mit = [int(u["num"]) for u in (_j.load(fh) or []) if u.get("output")]
        if mit:
            return sorted(mit)[0]
        print(f"[warnung] {pfad}: kein Universum mit Ausgang — nehme {vorgabe}")
    except FileNotFoundError:
        print(f"[warnung] {pfad} fehlt — nehme Universum {vorgabe}")
    except Exception as e:
        print(f"[warnung] {pfad} nicht lesbar ({e}) — nehme Universum {vorgabe}")
    return vorgabe


UNIVERSUM = _universum_mit_ausgang()
print(f"Universum mit Ausgang: {UNIVERSUM}")

adr = 1
for fid, name in ((1, "MH Links"), (2, "MH Rechts")):
    state.add_fixture(PatchedFixture(
        fid=fid, label=name, fixture_profile_id=PROFIL, mode_name=MODUS,
        universe=UNIVERSUM, address=adr, channel_count=N_KANAELE,
        manufacturer_name="Varytec", fixture_name="Hero Spot 90",
        fixture_type="moving_head",
        pan_range_deg=int(PAN_RANGE), tilt_range_deg=int(TILT_RANGE),
        pan_zero_dmx=int(PAN_ZERO), tilt_zero_dmx=int(TILT_ZERO),
        invert_pan=INVERT_PAN, invert_tilt=INVERT_TILT,
    ), undoable=False)
    adr += N_KANAELE

fixtures = state.get_patched_fixtures()
fids = [f.fid for f in fixtures]
kanal = {f.fid: {c.attribute: c.channel_number for c in get_channels_for_patched(f)}
         for f in fixtures}

# ── 2) Positionen im Raum ────────────────────────────────────────────────────
# ★ Einzeln zuweisen, NICHT das ganze Dict setzen: der Setter von
# visualizer_positions macht view.clear() und wuerde Knoten verlieren
# (VIZ-LIVEVIEW-FOOTGUN). Und live_view_positions bewusst NICHT setzen — das
# 2D-Raster wuerde die 3D-x/z ableiten und die echten Werte ueberschreiben.
for fid, p in POS.items():
    state.visualizer_positions[fid] = p
for fid, r in ROT.items():
    state.visualizer_rotations[fid] = r

# ── 3) Grundzustand: die Koepfe muessen ueberhaupt hell werden ───────────────
# ★ Shutter 251-255 = "Open" (Bereich aus dem Profil). Steht er falsch, bleibt
# das Geraet dunkel, egal was der Dimmer macht — daran sind hier schon einmal
# sechs Geraete einer Testshow gescheitert (RIG-DUNKEL). Deshalb ausdruecklich.
state.base_levels = {fid: {"shutter": 255, "intensity": 180} for fid in fids}
state._rebuild_render_plan()


def _pt(fid, wert_pan, wert_tilt, szene):
    k = kanal[fid]
    szene.set_value(fid, k["pan"], int(wert_pan))
    szene.set_value(fid, k["tilt"], int(wert_tilt))
    # 16-Bit-Feinkanaele ausdruecklich auf 0: aim_pan_tilt liefert ganze
    # DMX-Schritte. Ein Rest aus einer vorigen Szene wuerde das Ziel sonst um
    # bis zu 1/256 Schritt verschieben — sichtbar bei 5 m Wurf.
    if "pan_fine" in k:
        szene.set_value(fid, k["pan_fine"], 0)
    if "tilt_fine" in k:
        szene.set_value(fid, k["tilt_fine"], 0)
    szene.set_value(fid, k["shutter"], 255)
    szene.set_value(fid, k["intensity"], 220)


# ── 4a) ABSOLUT: beide auf denselben Punkt (jeder Kopf eigene Werte) ─────────
abs_szenen = []
print("Absolute Ziele (aim_pan_tilt):")
for name, ziel in ZIELE:
    s = fm.new_scene(f"Absolut · {name}")
    s.fade_in = s.fade_out = 0.4
    zeile = []
    for fid in fids:
        # VIZ-55: aim_pan_tilt liefert MODELL-Werte. invert/swap dreht die
        # Ausgabestufe beim Rendern der Szene (apply_pan_tilt_orientation) —
        # sie hier mitzugeben hiesse, sie zweimal anzuwenden. Genau daran
        # zeigten die absoluten Ziele dieser Show bis zum 2026-08-30 nach
        # hinten statt an die Wand (INVERT_PAN ist True).
        pan, tilt = aim_pan_tilt(POS[fid], ziel, ROT[fid],
                                 pan_range_deg=PAN_RANGE, tilt_range_deg=TILT_RANGE,
                                 pan_zero_dmx=PAN_ZERO, tilt_zero_dmx=TILT_ZERO)
        _pt(fid, pan, tilt, s)
        zeile.append(f"fid{fid} pan={pan:3d} tilt={tilt:3d}")
    print(f"  {name:8s} -> {ziel}   " + " | ".join(zeile))
    abs_szenen.append(s)

# ── 4b) PARALLEL: beide dieselben Werte ──────────────────────────────────────
# ★ Bewusst NICHT irgendwelche runden Werte, sondern exakt die Werte, die der
# LINKE Kopf fuer das jeweilige Ziel braucht — auf BEIDE gelegt. Damit trifft
# Kopf 1 den Punkt und Kopf 2 verfehlt ihn um genau den Kopfabstand. Der
# Vergleich "gleiche Taste absolut vs. parallel" wird so zur Messung statt zur
# Anschauung: der Versatz an der Wand MUSS 0,60 m betragen.
par_szenen = []
for name, ziel in ZIELE:
    pan, tilt = aim_pan_tilt(POS[1], ziel, ROT[1],
                             pan_range_deg=PAN_RANGE, tilt_range_deg=TILT_RANGE,
                             pan_zero_dmx=PAN_ZERO, tilt_zero_dmx=TILT_ZERO)
    s = fm.new_scene(f"Parallel · {name}")
    s.fade_in = s.fade_out = 0.4
    for fid in fids:
        _pt(fid, pan, tilt, s)
    par_szenen.append(s)

# ── 4c) Optik-Szenen (alles im 16er-Modus vorhanden) ─────────────────────────
def optik(name, **attrs):
    s = fm.new_scene(name)
    s.fade_in = s.fade_out = 0.0
    for fid in fids:
        k = kanal[fid]
        for attr, val in attrs.items():
            if attr in k:
                s.set_value(fid, k[attr], val)
    return s

optik_szenen = [
    optik("Farbe Weiss",   color_wheel=0),
    optik("Farbe Rot",     color_wheel=18),
    optik("Farbe Gruen",   color_wheel=54),
    optik("Farbe Blau",    color_wheel=72),
    optik("Gobo aus",      gobo_wheel=0),
    optik("Gobo 3",        gobo_wheel=45),
    optik("Gobo dreht",    gobo_wheel=45, gobo_rotation=60),
    optik("Prisma an",     prism=60),
    optik("Prisma aus",    prism=0),
    optik("Strobe",        shutter=120),
    optik("Strobe aus",    shutter=255),
]

# ── 4d) Bewegung: EFX-Figuren ────────────────────────────────────────────────
efx_funcs = []
for name, algo, breite, versatz in (("Kreis gleich",   EfxAlgorithm.CIRCLE, 60.0, 0.0),
                                    ("Kreis versetzt", EfxAlgorithm.CIRCLE, 60.0, 0.5),
                                    ("Acht",           EfxAlgorithm.EIGHT,  80.0, 0.0),
                                    ("Linie",          EfxAlgorithm.LINE,   90.0, 0.5)):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.width = e.height = breite
    e.fixtures = [EfxFixture(fid=fid, start_offset=(versatz * i))
                  for i, fid in enumerate(fids)]
    efx_funcs.append(e)

# ── 5) Virtuelle Konsole ─────────────────────────────────────────────────────
widgets: list[dict] = []


def add(w, x, y, ww, hh):
    # ★ setGeometry, NICHT die Attribute setzen. to_dict() liest
    # ``self.geometry()`` — ein echtes Qt-Geometry. Ein ``w.x = 20`` legt nur ein
    # gleichnamiges Instanz-Attribut daneben, das niemand liest; ``w.width`` und
    # ``w.height`` sind sogar METHODEN von QWidget und werden dadurch
    # ueberschrieben. Ergebnis der ersten Fassung: jedes Element blieb auf (0,0)
    # und die ganze Konsole lag als ein Stapel uebereinander.
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def beschriftung(text, x, y, ww=420, hh=24):
    add(VCLabel(text), x, y, ww, hh)


def taste(fn, x, y, farbe, ww=150, hh=42):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b._bg_color.setNamedColor(farbe)
    add(b, x, y, ww, hh)


beschriftung("Varytec Hero Spot 90 — Test-Show (2 Koepfe, 16-Kanal-Modus)", 20, 14, 760, 28)

# Spalte 1: ABSOLUT
beschriftung("ABSOLUT — beide auf denselben PUNKT im Raum", 20, 56, 420, 22)
beschriftung("(jeder Kopf bekommt eigene Pan/Tilt-Werte)", 20, 78, 420, 18)
for i, s in enumerate(abs_szenen):
    taste(s, 20, 104 + i * 50, "#14532d")

# Spalte 2: PARALLEL
beschriftung("PARALLEL — beide dieselben Werte", 200, 56, 420, 22)
beschriftung("(Strahlen laufen parallel, treffen NICHT denselben Punkt)", 200, 78, 460, 18)
for i, s in enumerate(par_szenen):
    taste(s, 200, 104 + i * 50, "#4a2a11")

# Spalte 3: Bewegung
beschriftung("BEWEGUNG", 380, 56, 300, 22)
for i, e in enumerate(efx_funcs):
    taste(e, 380, 104 + i * 50, "#3a2150")

# Spalte 4: Optik
beschriftung("OPTIK", 560, 56, 300, 22)
for i, s in enumerate(optik_szenen):
    taste(s, 560 + (i // 6) * 160, 104 + (i % 6) * 50, "#11304a", ww=150)

# XY-Pads
beschriftung("Pan / Tilt von Hand", 20, 330, 420, 22)
pad_beide = VCXYPad("Beide (parallel)")
pad_beide._fixture_ids = list(fids)
add(pad_beide, 20, 356, 190, 190)

pad_l = VCXYPad("Nur Links")
pad_l._fixture_ids = [1]
add(pad_l, 224, 356, 150, 150)

pad_r = VCXYPad("Nur Rechts")
pad_r._fixture_ids = [2]
add(pad_r, 388, 356, 150, 150)

# Fader
dim = VCSlider("Dimmer")
dim.mode = SliderMode.PROGRAMMER
dim.programmer_attr = "intensity"
dim.fixture_ids = list(fids)
add(dim, 560, 356, 70, 190)

gm = VCSlider("Grand Master")
gm.mode = SliderMode.GRANDMASTER
add(gm, 644, 356, 70, 190)

blackout = VCButton("Blackout")
blackout.action = ButtonAction.BLACKOUT
blackout._bg_color.setNamedColor("#5a1111")
add(blackout, 728, 356, 150, 42)

stop = VCButton("Alles stoppen")
stop.action = ButtonAction.STOP_ALL
stop._bg_color.setNamedColor("#333a44")
add(stop, 728, 406, 150, 42)

clear = VCButton("Programmer leeren")
clear.action = ButtonAction.CLEAR
clear._bg_color.setNamedColor("#333a44")
add(clear, 728, 456, 150, 42)

beschriftung("Test: 'Absolut' -> beide Flecken UEBEREINANDER an der Wand. "
             "'Parallel' -> exakt 0,60 m auseinander (= Kopfabstand). "
             "Weicht es ab, stimmt Aufstellung oder Pan/Tilt-Bereich nicht.",
             20, 556, 900, 40)

state.programmer = {}
state._vc_layout = {"widgets": widgets}
state.show_name = "Spot90 Testshow"

from src.core.show.show_file import save_show, load_show
save_show(OUT)
print(f"\nGespeichert: {OUT}")

# ── 6) Selbst-Verifikation: frisch laden und nachzaehlen ─────────────────────
ok, msg = load_show(OUT)
print("Laden:", ok, msg)
st2 = get_state()
patch2 = st2.get_patched_fixtures()
vc2 = (getattr(st2, "_vc_layout", {}) or {}).get("widgets", [])
print(f"  Geraete: {len(patch2)}  (erwartet 2)")
print(f"  Funktionen: {len(get_function_manager().all())} "
      f"(erwartet {len(abs_szenen)+len(par_szenen)+len(optik_szenen)+len(efx_funcs)})")
print(f"  VC-Widgets: {len(vc2)}")
print(f"  3D-Positionen: {dict(st2.visualizer_positions)}")
# ★ Nicht nur ZAEHLEN, sondern nachsehen, WO die Elemente liegen. Die erste
# Fassung meldete "40 VC-Widgets" und war zufrieden — dabei lagen alle auf
# (0,0) uebereinander, weil add() Attribute statt setGeometry gesetzt hatte.
# Eine Zaehlung haette diesen Fehler nie gefunden.
plaetze = {(w.get("x", 0), w.get("y", 0)) for w in vc2}
groessen = {(w.get("w", 0), w.get("h", 0)) for w in vc2}
print(f"  VC-Positionen: {len(plaetze)} verschiedene, "
      f"x {min((w.get('x',0) for w in vc2), default=0)}..{max((w.get('x',0) for w in vc2), default=0)}, "
      f"y {min((w.get('y',0) for w in vc2), default=0)}..{max((w.get('y',0) for w in vc2), default=0)}")

# ★ Universum gegen die ECHTE Ausgabe-Konfiguration halten. Ein Patch auf einem
# Universum ohne Ausgang sieht in der App voellig normal aus — nur am Rig
# passiert nichts.
import json as _json
_konf = os.path.join(_ROOT, "data", "universes.json")
_ausgaenge = []
try:
    with open(_konf, encoding="utf-8") as fh:
        _ausgaenge = [int(u.get("num")) for u in (_json.load(fh) or [])
                      if u.get("output")]
except Exception as e:
    print(f"  (universes.json nicht lesbar: {e})")
print(f"  Universen mit Ausgang: {_ausgaenge or 'keine'} — Patch liegt auf {UNIVERSUM}")

fehler = []
if _ausgaenge and UNIVERSUM not in _ausgaenge:
    fehler.append(f"Universum {UNIVERSUM} hat KEINEN Ausgang "
                  f"(konfiguriert: {_ausgaenge}) — am Geraet passiert nichts")
if len(vc2) and len(plaetze) < len(vc2) * 0.8:
    fehler.append(f"nur {len(plaetze)} verschiedene Positionen fuer {len(vc2)} "
                  f"Elemente — die Konsole liegt uebereinander")
if any(b <= 0 or h <= 0 for b, h in groessen):
    fehler.append("Element mit Breite/Hoehe 0")
if len(patch2) != 2:
    fehler.append("Patch unvollstaendig")
if not st2.visualizer_positions:
    fehler.append("3D-Positionen fehlen -> Zielen kann nicht stimmen")
for f in patch2:
    if getattr(f, "channel_count", 0) != N_KANAELE:
        fehler.append(f"fid{f.fid}: {f.channel_count} statt {N_KANAELE} Kanaelen")
print("FEHLER: " + "; ".join(fehler) if fehler else "OK — Show ist vollstaendig.")
