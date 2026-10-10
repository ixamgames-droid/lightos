"""DEMO-07: Bilder fuer ``docs/showcase/`` — die Showcase-Shows „Club-Nacht" und
„Theater/Event" mit laufendem Playback.

Die Shows bauen ``tools/build_showcase_club.py`` und
``tools/build_showcase_theater.py`` — hier IN DER SANDBOX (Generator im
Unterprozess, Ziel und Buehne im Sandbox-Ordner), danach werden sie wie von
Hand geladen. Bedient wird ueber die echten Bedienelemente der Show:
``VCCueList._do_go`` (GO-Knopf der Cue-Liste) und ``VCButton._trigger``.

3D-Szenen brauchen WebGL und entstehen nur am echten Bildschirm::

    DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py showcase --bildschirm

VC- und Playback-Bilder entstehen offscreen::

    venv/bin/python tools/anleitungsbilder.py showcase

★ Zeit laeuft hier SIMULIERT (wie bei den Buehnen-Show-Bildern): Jeder
Schritt rechnet feste DMX-Frames mit dem echten ``OutputManager._send_all``.
Cue-Listen messen ihre Fades aber mit der Wanduhr (``time.monotonic``) und
stellen Follow-Cues mit ``threading.Timer`` — beides ersetzt :class:`SimUhr`
in ``cue_stack`` durch die simulierte Show-Zeit, und die Beats der globalen
BPM kommen ebenfalls aus ihr. Ein GIF-Frame mit 0,2 s zeigt so genau 0,2 s
Show, egal wie lange die Aufnahme dauert.

Darstellung wie in den Demo-Videos: Modus „Ansehen", Seitenleiste zu,
Namensschilder aus, Strahl-Deckkraft 20 %, Nebel an.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time as _time

from anleitungsbilder.runner import Frame, Szene, SzenenFehler

ZIEL = "docs/showcase/img"

_GROESSE = (1600, 900)      # Visualizer-Fenster
_HINWEIS_H = 40             # unten: Bedienhinweis der 3D-Ansicht, kommt nicht ins Bild
_TAKT = 1.0 / 44.0          # ein DMX-Frame
STRAHL_DECKKRAFT = 20
HELLIGKEIT = 10
SEED_BPM = 126.0

GENERATOR = {"club": "build_showcase_club.py", "theater": "build_showcase_theater.py"}


# ── simulierte Zeit fuer Cue-Listen und Beats ───────────────────────────────

class SimUhr:
    """Show-Zeit, die nur :func:`ticks` weiterschiebt."""

    def __init__(self):
        self.t = 1000.0
        self.timer: list = []
        self._beat_pos = None
        self.beat = None            # Original-``_emit_beat`` der BPM-Instanz

    def monotonic(self):
        return self.t

    def __getattr__(self, name):    # alles andere wie das echte ``time``
        return getattr(_time, name)

    def faellige(self):
        for eintrag in sorted([e for e in self.timer if e[0] <= self.t], key=lambda e: e[0]):
            if eintrag in self.timer:
                self.timer.remove(eintrag)
                if not eintrag[2].abgebrochen:
                    eintrag[1]()


_UHR = SimUhr()


class _SimTimer:
    """Ersatz fuer ``threading.Timer`` in ``cue_stack`` (Follow-Cues)."""

    def __init__(self, intervall, fn, *a, **kw):
        self.intervall, self.fn, self.abgebrochen, self.daemon = float(intervall), fn, False, True

    def start(self):
        _UHR.timer.append([_UHR.t + self.intervall, self.fn, self])

    def cancel(self):
        self.abgebrochen = True


class _SimThreading:
    Timer = _SimTimer

    def __getattr__(self, name):
        return getattr(threading, name)


def sim_einbauen():
    """Cue-Listen und Beats auf die simulierte Zeit umstellen (einmal je Prozess)."""
    from src.core.engine import cue_stack
    from src.core.engine.bpm_manager import get_bpm_manager
    if cue_stack.time is _UHR:
        return
    cue_stack.time = _UHR
    cue_stack.threading = _SimThreading()
    bm = get_bpm_manager()
    _UHR.beat = type(bm)._emit_beat.__get__(bm)
    bm._emit_beat = lambda: None        # der Wanduhr-Takt-Thread schweigt


def _beats_pruefen():
    """Je ganzem Beat des globalen Busses einen Beat ausloesen (beat_sync-Listen)."""
    from src.core.engine.tempo_bus import get_tempo_bus_manager
    bus = get_tempo_bus_manager().get("Global")
    if bus is None or _UHR.beat is None:
        return
    bpm, _bc, _bp, pos = bus.snapshot()
    if bpm <= 0:
        return
    ganz = int(math.floor(pos))
    if _UHR._beat_pos is None or ganz < _UHR._beat_pos:
        _UHR._beat_pos = ganz
    while _UHR._beat_pos < ganz:
        _UHR._beat_pos += 1
        _UHR.beat()


def ticks(ui, n: int):
    """``n`` DMX-Frames mit dem ECHTEN ``_send_all`` rechnen (ohne zu senden);
    die Show-Zeit laeuft je Frame 1/44 s weiter."""
    om = ui.state.output_manager
    tabellen = (om._enttec_outputs, om._artnet_outputs, om._sacn_outputs)
    gemerkt = [dict(t) for t in tabellen]
    try:
        for t in tabellen:
            t.clear()
        for _ in range(max(1, int(n))):
            _UHR.t += _TAKT
            _UHR.faellige()
            om._send_all()
            _beats_pruefen()
    finally:
        for t, alt in zip(tabellen, gemerkt):
            t.clear()
            t.update(alt)


def sekunden(ui, s: float):
    ticks(ui, round(s / _TAKT))


class Uhr:
    """Frames so rechnen, dass ihre Summe der Summe der Sekunden entspricht."""

    def __init__(self):
        self.zeit = 0.0
        self.frames = 0

    def weiter(self, ui, s: float):
        self.zeit += s
        soll = int(round(self.zeit / _TAKT))
        if soll > self.frames:
            ticks(ui, soll - self.frames)
            self.frames = soll


# ── Show laden und bedienen ─────────────────────────────────────────────────

def show_laden(ui, welche: str):
    """Showcase-Show in der Sandbox bauen (einmal je Prozess) und laden."""
    import subprocess
    import sys
    from src.core.paths import app_data_dir
    from src.core.show.show_file import load_show
    if ui.info.get("showcase") == welche:
        return
    if "lightos_doku_" not in os.path.realpath(app_data_dir()):
        raise SzenenFehler("Showcase-Shows nur in der Sandbox bauen")
    pfad = os.path.join(os.getcwd(), f"showcase_{welche}.lshow")
    if not os.path.exists(pfad):
        tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        lauf = subprocess.run([sys.executable, os.path.join(tools, GENERATOR[welche]),
                               "--out", pfad], env=env, cwd=os.getcwd(),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if lauf.returncode != 0 or not os.path.exists(pfad):
            raise SzenenFehler("Generator scheiterte: " + (lauf.stdout + lauf.stderr)[-600:])
    sim_einbauen()
    ok, meldung = load_show(pfad)
    if not ok:
        raise SzenenFehler(f"Showcase {welche} laedt nicht: {meldung}")
    ui.win._refresh_all_views()
    ui.state.show_fixture_labels = False
    ui.state.set_selected_fids([])
    ui.info["showcase"] = welche
    v = getattr(ui, "_doku_viz", None)
    if v is not None:
        ui.pump(1.5)                    # neue Buehne + Geraete im 3D
    ui.pump(0.5)


def _vc_canvas(ui):
    return ui.win._vc_view._canvas


def taste(ui, text):
    from src.ui.virtualconsole.vc_button import VCButton
    for w in _vc_canvas(ui).findChildren(VCButton):
        if (w.caption or "").replace("\n", " ") == text:
            return w
    raise SzenenFehler(f"VC-Knopf '{text}' fehlt")


def druecken(ui, text):
    """Kurzer Druck wie ein Klick/Pad."""
    w = taste(ui, text)
    w._pressed = True
    w._trigger(True)
    w._pressed = False
    w._trigger(False)
    w.update()


def halten(ui, text, an: bool):
    """Flash-Taste druecken (an) bzw. loslassen."""
    w = taste(ui, text)
    w._pressed = an
    w._trigger(an)
    w.update()


def cueliste(ui, titel):
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    for w in _vc_canvas(ui).findChildren(VCCueList):
        if w.caption == titel:
            return w
    raise SzenenFehler(f"Cue-Liste '{titel}' fehlt in der VC")


def go(ui, titel):
    """GO auf der Cue-Liste der VC (derselbe Weg wie der Knopf)."""
    w = cueliste(ui, titel)
    w._do_go()
    w._refresh()


def cue_springen(ui, titel, nummer):
    """Cue-Liste ohne Umweg auf Cue ``nummer`` stellen, Fade sofort fertig
    (Startzustand eines Bildes)."""
    w = cueliste(ui, titel)
    stack = w._executor().stack
    stack.go_to(float(nummer))
    if stack._fade is not None:
        stack._fade.start_time -= 1000.0
    stack._cancel_follow()
    w._refresh()


def alles_aus(ui):
    """Funktionen stoppen, Cue-Listen anhalten, Blackout loesen, GM voll."""
    from src.core.engine.function_manager import get_function_manager
    get_function_manager().stop_all()
    pe = ui.state.playback_engine
    for page in pe.pages:
        for ex in page:
            if ex.stack is not None:
                ex.stack.stop()
    om = ui.state.output_manager
    if getattr(om, "_blackout", False):
        taste(ui, "BLACKOUT")._trigger(False)
    om.set_grand_master(1.0)
    _UHR.timer.clear()
    ticks(ui, 3)


def tempo(ui, bpm=SEED_BPM):
    from src.core.engine.bpm_manager import get_bpm_manager
    get_bpm_manager().request_bpm(bpm, "doku")


# ── 3D ──────────────────────────────────────────────────────────────────────

def viz(ui):
    v = getattr(ui, "_doku_viz", None)
    if v is None:
        raise SzenenFehler("3D-Visualizer nicht offen")
    return v


def viz_auf(ui, welche, *, stufe="max", groesse=_GROESSE):
    """Show laden, Visualizer oeffnen (einmal), Modus Ansehen, Seitenleiste
    zu, Strahlen + Nebel."""
    from PySide6.QtCore import Qt
    from anleitungsbilder.szenen_vc_widgets import _viz_bereit
    from src.ui.views.programmer_view import _save_prefs
    from src.ui.visualizer.visualizer_window import VisualizerWindow
    show_laden(ui, welche)
    if getattr(ui, "_doku_viz", None) is not None:
        return
    _save_prefs({"viz_quality_tier": stufe})
    v = ui.win._visualizer_window
    if v is None:
        v = VisualizerWindow(ui.win)
        v.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        ui.win._visualizer_window = v
    v.resize(*groesse)
    v.show()
    ui._doku_viz = v
    _viz_bereit(ui, v)
    try:
        v._set_build_mode(False)        # Modus „Ansehen"
    except Exception:
        pass
    try:
        v.centralWidget().widget(1).hide()
    except Exception:
        pass
    ui.pump(1.0)
    einstellung(ui)


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
    viz(ui)._bridge.push_camera_preset("applycam:" + json.dumps(kam))
    ui.pump(1.0)


def kamera_sofort(ui, kam):
    js = ("(function(){var L=window.__lightos;if(!L)return -1;"
          "L.applyNamedCamera(%s);if(L.requestRender)L.requestRender();return 1;})()"
          % json.dumps(kam))
    viz(ui)._view.page().runJavaScript(js)


def _weich(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def kamera_zwischen(a: dict, b: dict, t: float, *, weich=True) -> dict:
    u = _weich(t) if weich else t
    aus = dict(a)
    for key in ("theta", "phi", "radius"):
        aus[key] = a[key] + (b[key] - a[key]) * u
    aus["target"] = [a["target"][i] + (b["target"][i] - a["target"][i]) * u for i in range(3)]
    return aus


def flaeche_pixmap(ui):
    v = viz(ui)
    pix = v._view.grab()
    if pix.isNull() or pix.width() < 200:
        raise SzenenFehler("3D-Ansicht liess sich nicht aufnehmen")
    return pix.copy(0, 0, pix.width(), pix.height() - _HINWEIS_H)


def flaeche(ui):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    pix = flaeche_pixmap(ui)
    lbl = QLabel()
    lbl.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    lbl.setFixedSize(pix.width(), pix.height())
    lbl.setPixmap(pix)
    return lbl


def _k(**kw):
    return dict({"name": "Doku", "mode": "3D"}, **kw)


# Kameras (theta 0 = aus dem Publikum, phi = Winkel von oben, radius in m).
CLUB_TOTALE = _k(theta=0.0, phi=1.36, radius=15.5, target=[0.0, 2.6, 0.5])
CLUB_SCHRAEG = _k(theta=0.55, phi=1.32, radius=14.5, target=[0.0, 2.6, 0.0])
CLUB_PUBLIKUM = _k(theta=-0.35, phi=1.45, radius=13.0, target=[0.0, 2.8, 0.0])
CLUB_HINTEN = _k(theta=0.15, phi=1.40, radius=24.0, target=[0.0, 2.6, 2.0])
THEATER_TOTALE = _k(theta=0.0, phi=1.40, radius=18.0, target=[0.0, 3.0, -2.5])
THEATER_SCHRAEG = _k(theta=-0.5, phi=1.34, radius=16.0, target=[-0.5, 2.8, -2.5])
THEATER_NAH = _k(theta=0.25, phi=1.42, radius=14.0, target=[-0.5, 2.6, -2.8])


# ── Club ────────────────────────────────────────────────────────────────────

CLUB_LISTE = "Club-Nacht (Ex 1)"
PULS_LISTE = "Drop-Puls (Ex 2)"


def _club_bewegung(ui):
    tempo(ui)
    for k in ("Kreis", "Spider an", "Schere", "Spider Farben"):
        druecken(ui, k)


def _club_vc_vorher(ui):
    show_laden(ui, "club")
    ui.sektion("Virtual Console")
    alles_aus(ui)
    _club_bewegung(ui)
    cue_springen(ui, CLUB_LISTE, 4)
    go(ui, PULS_LISTE)
    druecken(ui, "Laser an")
    druecken(ui, "Laser Farben")
    druecken(ui, "Laser Welle")
    sekunden(ui, 2.0)
    ui.pump(0.4)


def _club_playback_vorher(ui):
    _club_vc_vorher(ui)
    ui.sektion("Playback")
    ui.pump(0.5)


def _club_3d(cue, knoepfe, kam, gm=1.0, vorlauf=2.5, puls=False):
    def vorher(ui):
        viz_auf(ui, "club")
        alles_aus(ui)
        tempo(ui)
        for k in knoepfe:
            druecken(ui, k)
        cue_springen(ui, CLUB_LISTE, cue)
        if puls:
            go(ui, PULS_LISTE)
        ui.state.output_manager.set_grand_master(gm)
        sekunden(ui, vorlauf)
        kamera(ui, kam)
    return vorher


def _club_gif():
    """Cue-Liste laeuft durch (GO je Abschnitt), Kamera kreist langsam."""
    n, dt = 24, 0.4
    gos = {0: None, 5: "go", 11: "go", 17: "go"}       # Intro -> Groove -> Build-up -> Drop
    uhr = Uhr()
    a = dict(CLUB_TOTALE, theta=-0.4)
    b = dict(CLUB_TOTALE, theta=0.4, radius=17.0)

    def vorher(ui):
        _club_3d(1, ["Kreis", "Spider an", "Schere", "Spider Farben", "Laser an",
                     "Laser Farben", "Laser Welle"], a, gm=0.8, vorlauf=4.5)(ui)

    def frame_schritt(i):
        def schritt(ui):
            if gos.get(i) == "go":
                go(ui, CLUB_LISTE)
            if i == 17:
                go(ui, PULS_LISTE)
            uhr.weiter(ui, dt)
            kamera_sofort(ui, kamera_zwischen(a, b, i / (n - 1)))
        return schritt
    return Szene("club_05_playback", sektion="Bühne", vorher=vorher, nachher=alles_aus,
                 braucht_gpu=True, groesse=_GROESSE, gif_breite=560,
                 gif_zuschnitt=(130, 120, 1340, 700), warte_s=0.3,
                 frames=[Frame(dauer_s=dt, schritt=frame_schritt(i), dialog=flaeche,
                               warte_s=0.12) for i in range(n)],
                 titel="GIF: Cue-Liste Club-Nacht läuft — Intro, Groove, Build-up, Drop")


# ── Theater ─────────────────────────────────────────────────────────────────

ABEND_LISTE = "Abendablauf (Ex 1)"


def _theater_vc_vorher(ui):
    show_laden(ui, "theater")
    ui.sektion("Virtual Console")
    alles_aus(ui)
    cue_springen(ui, ABEND_LISTE, 4)
    sekunden(ui, 1.0)
    ui.pump(0.4)


def _theater_playback_vorher(ui):
    _theater_vc_vorher(ui)
    ui.sektion("Playback")
    ui.pump(0.5)


def _theater_3d(cue, kam, gm=1.0):
    def vorher(ui):
        viz_auf(ui, "theater")
        alles_aus(ui)
        cue_springen(ui, ABEND_LISTE, cue)
        ui.state.output_manager.set_grand_master(gm)
        sekunden(ui, 1.0)
        kamera(ui, kam)
    return vorher


def _theater_gif():
    """Begruessung -> Rede-Spot -> Szenenwechsel (folgt von selbst) -> Szene."""
    n, dt = 30, 0.5
    uhr = Uhr()
    a = dict(THEATER_TOTALE, theta=-0.25)
    b = dict(THEATER_TOTALE, theta=0.25, radius=19.0)

    def vorher(ui):
        _theater_3d(3, a)(ui)

    def frame_schritt(i):
        def schritt(ui):
            if i in (2, 8):                        # GO: Rede-Spot, dann Szenenwechsel
                go(ui, ABEND_LISTE)
            uhr.weiter(ui, dt)
            kamera_sofort(ui, kamera_zwischen(a, b, i / (n - 1)))
        return schritt
    return Szene("theater_05_ablauf", sektion="Bühne", vorher=vorher, nachher=alles_aus,
                 braucht_gpu=True, groesse=_GROESSE, gif_breite=560,
                 gif_zuschnitt=(150, 110, 1300, 700), warte_s=0.3,
                 frames=[Frame(dauer_s=dt, schritt=frame_schritt(i), dialog=flaeche,
                               warte_s=0.12) for i in range(n)],
                 titel="GIF: Rede-Spot, dann Szenenwechsel — die Spots fahren im Dunkeln "
                       "aufs Podest, die Szene folgt von selbst")


SZENEN = [
    Szene("club_01_vc", sektion="Virtual Console", vorher=_club_vc_vorher, nachher=alles_aus,
          titel="Club-Nacht: VC mit Cue-Listen (GO/BACK), Playback-Fadern, Tempo, "
                "Speed-Dials und Flash-Tasten"),
    Szene("club_02_playback", sektion="Playback", vorher=_club_playback_vorher,
          nachher=alles_aus, titel="Club-Nacht: Executor-Seite mit Ex 1 und Ex 2"),
    Szene("club_03_groove", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_club_3d(2, ["Acht", "Spider an", "Welle", "Spider Farben"], CLUB_SCHRAEG,
                          gm=0.85),
          dialog=flaeche, nachher=alles_aus,
          titel="Cue 2 Groove: Gobos drehen, Acht der Moving Heads, Spider-Farben je Takt"),
    Szene("club_04_drop", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_club_3d(4, ["Schwenk", "Spider an", "Schere", "Spider Farben", "Laser an",
                              "Laser Farben", "Laser Welle", "Strobe Lauf"],
                          CLUB_PUBLIKUM, gm=0.75, puls=True),
          dialog=flaeche, nachher=alles_aus,
          titel="Cue 4 Drop mit Drop-Puls auf Ex 2: rote Front im Takt, Laser, Strobe-Lauf"),
    _club_gif(),
    Szene("theater_01_vc", sektion="Virtual Console", vorher=_theater_vc_vorher,
          nachher=alles_aus,
          titel="Theater/Event: Cue-Liste Abendablauf mit GO/BACK, Playback-Fader, "
                "Grand Master"),
    Szene("theater_02_playback", sektion="Playback", vorher=_theater_playback_vorher,
          nachher=alles_aus,
          titel="Theater/Event: Cue-Liste mit Fade-, Delay- und Follow-Zeiten"),
    Szene("theater_03_rede", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_theater_3d(4, THEATER_SCHRAEG), dialog=flaeche, nachher=alles_aus,
          titel="Cue 4 Rede-Spot: beide Spots auf dem Rednerpult, Saal zurückgenommen"),
    Szene("theater_04_podest", sektion="Bühne", braucht_gpu=True, groesse=_GROESSE,
          vorher=_theater_3d(6, THEATER_NAH), dialog=flaeche, nachher=alles_aus,
          titel="Cue 6 Szene am Podest: Spots auf dem Podest, Horizont im Abendrot"),
    _theater_gif(),
]
