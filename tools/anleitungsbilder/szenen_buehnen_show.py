"""DOC-60: Bilder fuer ``docs/anleitung_buehnen_show/`` — die grosse Buehnen-Show
(40 PAR, 20 Moving Heads, 8 Strobes, 10 Laser, 2 Hazer auf einer 20-m-Buehne)
im 3D-Visualizer, mit langsamen Kamerafahrten waehrend die Effekte laufen.

Die Show baut ``tools/build_buehnen_show_2026.py`` — hier IN DER SANDBOX
(Generator-Aufruf mit Ziel im Sandbox-Ordner, Buehne im Sandbox-Datenordner),
danach wird sie wie von Hand geladen. Die Effekte startet jede Szene ueber die
echten VC-Knoepfe der Show (``VCButton._trigger`` wie ein Klick/MIDI-Pad).

Die 3D-Szenen brauchen WebGL und entstehen nur am echten Bildschirm::

    DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py buehnen_show --bildschirm

Das VC-Bild entsteht offscreen::

    venv/bin/python tools/anleitungsbilder.py buehnen_show

★ Zeit laeuft hier SIMULIERT: Das Werkzeug hat keinen Ausgabe-Thread. Jeder
Schritt rechnet eine feste Zahl Frames mit dem echten
``OutputManager._send_all`` (Funktionen, Grand Master, Blackout — ohne zu
senden) und haelt dann an, bis das Bild aufgenommen ist. Ein GIF-Frame mit
``dauer_s`` 0,12 zeigt deshalb genau 0,12 s Show — die GIFs laufen in
Echtzeit und sind bei jedem Lauf gleich, egal wie lange die Aufnahme dauert.

Kamerafahrten: Jeder GIF-Frame setzt die Kamera auf einen Zwischenstand
(theta/phi/radius/target, weich interpoliert) ueber die vorhandene
Visualizer-API ``window.__lightos.applyNamedCamera`` — dieselbe, mit der die
Toolbar gespeicherte Kameras anwendet.
"""
from __future__ import annotations

import json
import math
import os

from anleitungsbilder.runner import Frame, Szene, SzenenFehler

ZIEL = "docs/anleitung_buehnen_show/img"

_GROESSE = (1900, 1000)     # Visualizer-Fenster
_HINWEIS_H = 40             # unten: Bedienhinweis der 3D-Ansicht, kommt nicht ins Bild
_TAKT = 1.0 / 44.0          # ein DMX-Frame

# Darstellung: Strahlen bewusst zurueckhaltend (Deckkraft 22 %), Nebel an,
# Szene dunkel — die Buehne bleibt zwischen den Strahlen gut sichtbar.
STRAHL_DECKKRAFT = 22
HELLIGKEIT = 10

# Kameras wie camera/presets.js (theta/phi/radius/target); theta 0 = von vorn
# (aus dem Publikum), phi = Winkel von oben, radius = Abstand in Metern.
# Nah genug, dass die 20-m-Buehne gut die halbe Bildbreite fuellt, und eher
# flach (phi nahe 90 Grad) — von oben wirkt die Buehne klein.
KAM_TOTALE = {"name": "Doku", "mode": "3D", "theta": 0.0, "phi": 1.38,
              "radius": 25.0, "target": [0.0, 4.6, 0.0]}
KAM_SCHRAEG = {"name": "Doku", "mode": "3D", "theta": 0.55, "phi": 1.30,
               "radius": 25.0, "target": [0.0, 4.4, 0.0]}
KAM_PUBLIKUM = {"name": "Doku", "mode": "3D", "theta": -0.25, "phi": 1.47,
                "radius": 21.0, "target": [0.0, 5.2, 0.0]}
KAM_WEIT = {"name": "Doku", "mode": "3D", "theta": 0.0, "phi": 1.44,
            "radius": 38.0, "target": [0.0, 4.8, 1.0]}
KAM_NAH = {"name": "Doku", "mode": "3D", "theta": 0.0, "phi": 1.48,
           "radius": 21.0, "target": [0.0, 5.2, 0.0]}


# ── Show und Visualizer ─────────────────────────────────────────────────────

def show_laden(ui):
    """Buehnen-Show in der Sandbox bauen und laden (einmal je Prozess).

    Der Generator laeuft in einem eigenen Prozess mit der Umgebung dieses
    Werkzeugs (alle Datenpfade zeigen in die Sandbox). Im selben Prozess wie
    das offene Hauptfenster hat der eingebettete EFX-Editor die Geraeteliste
    der ersten neuen Bewegung mit der (leeren) Programmer-Auswahl ueberschrieben
    — er folgt der Auswahl, sobald er sichtbar ist."""
    if ui.info.get("buehnen_show"):
        return
    import subprocess
    import sys
    from src.core.paths import app_data_dir
    from src.core.show.show_file import load_show
    # Der Generator speichert die Buehne in den Datenordner — nur in der Sandbox.
    if "lightos_doku_" not in os.path.realpath(app_data_dir()):
        raise SzenenFehler("Buehnen-Show nur in der Sandbox bauen")
    pfad = os.path.join(os.getcwd(), "Buehnen_Show_2026.lshow")
    if os.path.exists(pfad):
        os.remove(pfad)
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    lauf = subprocess.run([sys.executable, os.path.join(tools, "build_buehnen_show_2026.py"),
                           "--out", pfad], env=env, cwd=os.getcwd(),
                          capture_output=True, text=True, timeout=600)
    if lauf.returncode != 0 or not os.path.exists(pfad):
        raise SzenenFehler("Generator scheiterte: " + (lauf.stdout + lauf.stderr)[-600:])
    ok, meldung = load_show(pfad)
    if not ok:
        raise SzenenFehler(f"Buehnen-Show laedt nicht: {meldung}")
    ui.win._refresh_all_views()
    ui.state.show_fixture_labels = False
    ui.state.set_selected_fids([])
    ui.info["buehnen_show"] = pfad
    ui.pump(0.5)


def _vc_canvas(ui):
    return ui.win._vc_view._canvas


def taste(ui, text):
    """VC-Knopf der Show mit dieser Beschriftung."""
    from src.ui.virtualconsole.vc_button import VCButton
    for w in _vc_canvas(ui).findChildren(VCButton):
        if (w.caption or "").replace("\n", " ") == text:
            return w
    raise SzenenFehler(f"VC-Knopf '{text}' fehlt in der Buehnen-Show")


def druecken(ui, text):
    """Kurzer Druck wie ein Klick/Pad: Druck + Loslassen ueber ``_trigger``."""
    w = taste(ui, text)
    w._pressed = True
    w._trigger(True)
    w._pressed = False
    w._trigger(False)
    w.update()


def alles_aus(ui):
    """Alle Funktionen stoppen, Blackout loesen, Grand Master voll."""
    from src.core.engine.function_manager import get_function_manager
    get_function_manager().stop_all()
    om = ui.state.output_manager
    # Die BLACKOUT-Taste ist ein Flash (dunkel, solange sie gehalten wird);
    # ein haengengebliebener Druck wird hier wie ein Loslassen geloest.
    if getattr(om, "_blackout", False):
        taste(ui, "BLACKOUT")._trigger(False)
    om.set_grand_master(1.0)
    ticks(ui, 3)


def ticks(ui, n: int):
    """``n`` DMX-Frames mit dem ECHTEN ``_send_all`` rechnen, ohne zu senden
    (die Sender-Tabellen sind waehrenddessen leer)."""
    om = ui.state.output_manager
    tabellen = (om._enttec_outputs, om._artnet_outputs, om._sacn_outputs)
    gemerkt = [dict(t) for t in tabellen]
    try:
        for t in tabellen:
            t.clear()
        for _ in range(max(1, int(n))):
            om._send_all()
    finally:
        for t, alt in zip(tabellen, gemerkt):
            t.clear()
            t.update(alt)


class Uhr:
    """Simulierte Show-Zeit: rechnet je Aufruf genau so viele DMX-Frames, dass
    die Summe der Frames der Summe der Sekunden entspricht (kein Drift, auch
    wenn ein Video-Frame 1/30 s und ein DMX-Frame 1/44 s lang ist)."""

    def __init__(self):
        self.zeit = 0.0
        self.frames = 0

    def weiter(self, ui, s: float):
        self.zeit += s
        soll = int(round(self.zeit / _TAKT))
        n = soll - self.frames
        if n > 0:
            ticks(ui, n)
            self.frames = soll


def sekunden(ui, s: float):
    ticks(ui, round(s / _TAKT))


def viz(ui):
    v = getattr(ui, "_doku_viz", None)
    if v is None:
        raise SzenenFehler("3D-Visualizer nicht offen")
    return v


def viz_auf(ui, *, stufe="max", groesse=_GROESSE):
    """Qualitaetsstufe setzen, Visualizer oeffnen (einmal), Seitenleiste
    zuklappen (mehr 3D-Flaeche), Strahlen + Nebel an."""
    from PySide6.QtCore import Qt
    from anleitungsbilder.szenen_vc_widgets import _viz_bereit
    from src.ui.views.programmer_view import _save_prefs
    from src.ui.visualizer.visualizer_window import VisualizerWindow
    show_laden(ui)
    if getattr(ui, "_doku_viz", None) is not None:
        return
    _save_prefs({"viz_quality_tier": stufe})      # Sandbox-Prefs
    v = ui.win._visualizer_window
    if v is None:
        v = VisualizerWindow(ui.win)
        v.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        ui.win._visualizer_window = v
    v.resize(*groesse)
    v.show()
    ui._doku_viz = v
    _viz_bereit(ui, v)
    seitenleiste_zu(ui)
    einstellung(ui)
    kamera(ui, KAM_TOTALE)


def seitenleiste_zu(ui):
    """Rechte Einstellungs-Leiste des Visualizers ausblenden: die 3D-Flaeche
    bekommt die ganze Fensterbreite."""
    v = viz(ui)
    split = v.centralWidget()
    try:
        split.widget(1).hide()
    except Exception:
        pass
    ui.pump(1.0)


def einstellung(ui, *, opacity=STRAHL_DECKKRAFT, helligkeit=HELLIGKEIT, nebel=True):
    v = viz(ui)
    v._sld_opacity.setValue(opacity)
    v._sld_brightness.setValue(helligkeit)
    v._on_brightness_changed(helligkeit)
    v._chk_cones.setChecked(True)
    v._chk_fog.setChecked(nebel)
    v._chk_floor.setChecked(True)
    v._bridge.push_settings(v._collect_settings())
    ui.pump(0.5)


def kamera(ui, kam):
    v = viz(ui)
    v._bridge.push_camera_preset("applycam:" + json.dumps(kam))
    ui.pump(1.0)


def kamera_sofort(ui, kam):
    """Kamera ohne Umweg ueber den Bridge-Poll setzen (fuer Kamerafahrten:
    jeder Frame bekommt genau seine Kamera)."""
    v = viz(ui)
    js = ("(function(){var L=window.__lightos;if(!L)return -1;"
          "L.applyNamedCamera(%s);if(L.requestRender)L.requestRender();return 1;})()"
          % json.dumps(kam))
    v._view.page().runJavaScript(js)


def _weich(t: float) -> float:
    """Ease-in-out (Kosinus): sanftes Anfahren und Abbremsen."""
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def kamera_zwischen(a: dict, b: dict, t: float, *, weich=True) -> dict:
    """Kamera zwischen ``a`` und ``b`` (t 0..1)."""
    u = _weich(t) if weich else t
    aus = dict(a)
    for key in ("theta", "phi", "radius"):
        aus[key] = a[key] + (b[key] - a[key]) * u
    aus["target"] = [a["target"][i] + (b["target"][i] - a["target"][i]) * u
                     for i in range(3)]
    return aus


def flaeche_pixmap(ui):
    """Nur die 3D-Flaeche (ohne Bedienhinweis unten) als QPixmap."""
    v = viz(ui)
    pix = v._view.grab()
    if pix.isNull() or pix.width() < 200:
        raise SzenenFehler("3D-Ansicht liess sich nicht aufnehmen")
    return pix.copy(0, 0, pix.width(), pix.height() - _HINWEIS_H)


def flaeche(ui):
    """Die 3D-Flaeche als Bild-Widget (fuer ``Szene.dialog``)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    pix = flaeche_pixmap(ui)
    lbl = QLabel()
    lbl.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    lbl.setFixedSize(pix.width(), pix.height())
    lbl.setPixmap(pix)
    return lbl


def _vorbereitung(knoepfe, kam, vorlauf_s=2.0, gm=1.0):
    """``vorher``: Visualizer offen, alles aus, Knoepfe druecken, Vorlauf.
    ``gm`` < 1 zieht den Grand Master zurueck (wie am Pult), damit der
    Buehnenboden unter vollen PARs nicht weiss ausbrennt."""
    def vorher(ui):
        viz_auf(ui)
        alles_aus(ui)
        for k in knoepfe:
            druecken(ui, k)
        ui.state.output_manager.set_grand_master(gm)
        sekunden(ui, vorlauf_s)
        kamera(ui, kam)
    return vorher


def _aufraeumen(ui):
    alles_aus(ui)


# ── Laser-Beleg (offscreen) ─────────────────────────────────────────────────

def _laser_kanal(ui, fid, attr):
    from src.core.app_state import get_channels_for_patched
    fx = next(f for f in ui.state.get_patched_fixtures() if f.fid == fid)
    for c in sorted(get_channels_for_patched(fx), key=lambda c: c.channel_number):
        if c.attribute == attr:
            return int(fx.universe), int(fx.address) - 1 + int(c.channel_number) - 1
    raise SzenenFehler(f"Gerät {fid} hat keinen Kanal {attr}")


def _laser_dmx(ui, fids, attr):
    werte = []
    for f in fids:
        u, i = _laser_kanal(ui, f, attr)
        werte.append(int(ui.state.output_manager.get_display_frame(u)[i]))
    return werte


def beleg_laser(ui):
    """Die Laser-Knöpfe der GELADENEN Show tun, was Übersicht und Anleitung
    sagen (Display-Frame, d. h. was die Ausgabe senden würde):

    * „Laser langsam"/„Laser Welle" bewegen ``laser_x`` (EFX auf den
      Laser-Achsen, nach dem Laden — LAS-23),
    * „Laser Lauf" schaltet nur zwischen 0 und 60 (Manual Control),
    * Grand Master 0 schaltet die Laser ohne Dimmer aus (LAS-24),
    * „Laser NOT-AUS" macht alle Laser-Kanäle dunkel.
    """
    laser = sorted(f.fid for f in ui.state.get_patched_fixtures()
                   if (f.label or "").startswith("Laser"))
    if len(laser) != 10:
        raise SzenenFehler(f"{len(laser)} Laser statt 10")
    for knopf in ("Laser langsam", "Laser Welle"):
        alles_aus(ui)
        for k in ("Laser an", "Laser grün", knopf):
            druecken(ui, k)
        verlauf = []
        for _ in range(16):
            ticks(ui, 22)
            verlauf.append(_laser_dmx(ui, laser, "laser_x"))
        erster = [v[0] for v in verlauf]
        print(f"BELEG {knopf}: Laser 1 X-Bewegung alle 0,5 s: {erster}", flush=True)
        for i in range(len(laser)):
            spur = {v[i] for v in verlauf}
            if max(spur) - min(spur) < 40:
                raise SzenenFehler(f"{knopf}: Laser {i + 1} bewegt sich nicht ({sorted(spur)})")
        if set(_laser_dmx(ui, laser, "shutter")) != {60}:
            raise SzenenFehler(f"{knopf}: Laser nicht an")
    alles_aus(ui)
    druecken(ui, "Laser an")
    druecken(ui, "Laser Lauf")
    werte = set()
    for _ in range(150):
        ticks(ui, 1)
        werte |= set(_laser_dmx(ui, laser, "shutter"))
    print(f"BELEG Laser Lauf: Shutter-Werte {sorted(werte)}", flush=True)
    if werte != {0, 60}:
        raise SzenenFehler(f"Laser Lauf: Shutter {sorted(werte)} statt 0/60")
    om = ui.state.output_manager
    stufen = []
    for gm in (0.5, 0.0):
        om.set_grand_master(gm)
        ticks(ui, 3)
        stufen.append((gm, sorted(set(_laser_dmx(ui, laser, "shutter")))))
    om.set_grand_master(1.0)
    print(f"BELEG Grand Master -> Laser-Shutter: {stufen}", flush=True)
    if stufen[-1][1] != [0]:
        raise SzenenFehler("Grand Master 0 schaltet die Laser nicht aus")
    druecken(ui, "Laser NOT-AUS")
    ticks(ui, 5)
    hoechst = max(max(_laser_dmx(ui, laser, a))
                  for a in ("shutter", "laser_x", "color_wheel", "laser_bank"))
    print(f"BELEG Laser NOT-AUS: höchster Laser-Wert {hoechst}", flush=True)
    if hoechst != 0:
        raise SzenenFehler("Laser NOT-AUS lässt Laser an")
    # Sperre wieder lösen wie in der Laser-Ansicht (Shutter im Programmer),
    # sonst bleiben die Laser in allen folgenden Bildern dunkel.
    ui.state.set_laser_estop(False)
    alles_aus(ui)
    druecken(ui, "Laser an")
    ticks(ui, 3)
    if set(_laser_dmx(ui, laser, "shutter")) != {60}:
        raise SzenenFehler("Laser nach Lösen des NOT-AUS nicht wieder an")
    alles_aus(ui)


# ── VC-Seite (offscreen) ────────────────────────────────────────────────────

def _vc_vorher(ui):
    show_laden(ui)
    ui.sektion("Virtual Console")
    alles_aus(ui)
    druecken(ui, "Drop")
    sekunden(ui, 1.0)
    ui.pump(0.3)


# ── Szenen ──────────────────────────────────────────────────────────────────

# GIF-Ausschnitt: oben ist in jeder Kamera nur dunkler Raum — weg damit.
_GIF_ZUSCHNITT = (230, 110, 1440, 767)


def _fahrt_gif(name, titel, knoepfe, kam_von, kam_bis, *, n=18, schritt_s=0.2,
               vorlauf_s=1.5, breite=640, weich=True):
    """GIF mit Kamerafahrt: je Frame laeuft die Show ``schritt_s`` weiter und
    die Kamera rueckt ein Stueck von ``kam_von`` nach ``kam_bis``."""
    uhr = Uhr()

    def frame_schritt(i):
        def schritt(ui):
            uhr.weiter(ui, schritt_s)
            kamera_sofort(ui, kamera_zwischen(kam_von, kam_bis, i / max(1, n - 1),
                                              weich=weich))
        return schritt
    return Szene(name, sektion="Bühne", vorher=_vorbereitung(knoepfe, kam_von, vorlauf_s),
                 nachher=_aufraeumen, braucht_gpu=True, groesse=_GROESSE,
                 gif_breite=breite, gif_zuschnitt=_GIF_ZUSCHNITT, warte_s=0.3,
                 frames=[Frame(dauer_s=schritt_s, schritt=frame_schritt(i),
                               dialog=flaeche, warte_s=0.12) for i in range(n)],
                 titel=titel)


# Kurze Wege je GIF: wenige Bilder ueber eine weite Fahrt springen sichtbar.
_ORBIT_A = dict(KAM_TOTALE, theta=-0.35, radius=27.0)
_ORBIT_B = dict(KAM_TOTALE, theta=0.35, radius=27.0)

SZENEN = [
    # Der Laser-Beleg laeuft NACH dem Bild: der NOT-AUS hinterlaesst eine
    # Meldung in der Statusleiste.
    Szene("01_vc_seite", sektion="Virtual Console", vorher=_vc_vorher,
          nachher=beleg_laser,
          titel="VC-Seite der Bühnen-Show: PAR-Dimmer/-Farbe, Moving Heads, "
                "Strobe + Laser, Show-Looks, Grand Master"),
    Szene("02_aufbau", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_vorbereitung(["PAR an", "Blau", "MH Licht an", "MH Weiß",
                                "Position Bühne", "Beam schmal", "Haze an"], KAM_SCHRAEG,
                               gm=0.55),
          dialog=flaeche, nachher=_aufraeumen,
          titel="Aufbau: 20-m-Bühne, drei Traversen-Ebenen, PAR-Türme, LED-Wand"),
    Szene("03_intro", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_vorbereitung(["Intro"], KAM_TOTALE, 3.0), dialog=flaeche,
          nachher=_aufraeumen,
          titel="Look Intro: blaue Dimmer-Welle, Tilt-Welle der Moving Heads, Laser"),
    Szene("04_drop", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_vorbereitung(["Drop"], KAM_PUBLIKUM, 2.3, gm=0.7), dialog=flaeche,
          nachher=_aufraeumen,
          titel="Look Drop: Lauflicht innen → außen, Schwenker A/B, Strobe-Lauf"),
    Szene("05_breakdown", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_vorbereitung(["Breakdown"], KAM_SCHRAEG, 2.0), dialog=flaeche,
          nachher=_aufraeumen, titel="Look Breakdown: Amber-Welle, blaue Moving Heads mit Gobo + Prisma, Acht"),
    Szene("06_finale", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_vorbereitung(["Finale"], KAM_TOTALE, 2.33, gm=0.5), dialog=flaeche,
          nachher=_aufraeumen, titel="Look Finale: Farbwechsel, Strobe, Kreis-Welle"),
    _fahrt_gif("07_wellen_orbit",
               "GIF: Dimmer-/Farbwelle über 40 PARs + Pan-Welle der Moving Heads, "
               "Kamera kreist langsam um die Bühne",
               ["Welle links → rechts", "Farbwelle", "MH Licht an", "Beam schmal",
                "Farbrad", "Pan-Welle", "Haze an"], _ORBIT_A, _ORBIT_B,
               n=16, schritt_s=0.2, breite=600),
    _fahrt_gif("08_schwenker_dolly",
               "GIF: Schwenker A/B im Wechsel, Kamera fährt von weit hinten "
               "im Publikum nach vorn",
               ["PAR an", "Blau", "MH Licht an", "MH Weiß", "Beam schmal",
                "Schwenker A/B"], KAM_WEIT, KAM_NAH, n=18, schritt_s=0.2),
    _fahrt_gif("09_lauflicht_strobe",
               "GIF: Lauflicht innen → außen, Strobes, Laser-Lauf — Schwenk",
               ["Lauflicht innen → außen", "Magenta", "Strobes Lauf", "Laser an",
                "Laser Lauf", "Laser Farbe", "MH Licht an", "Tilt-Welle", "Farbrad"],
               dict(KAM_PUBLIKUM, theta=-0.3), dict(KAM_PUBLIKUM, theta=0.1),
               n=14, schritt_s=0.12, breite=560),
]
