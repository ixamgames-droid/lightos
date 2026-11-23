"""VIZ-115: 3D-Ansicht nur oeffnen, wenn ein Kindprozess vorher WebGL bekommen hat.

**Der Fund (Live-Klicktest 23.11.2026).** In einem Fenster-Server ohne GPU
(Xephyr, Mesa llvmpipe) stuerzte die ganze App beim Oeffnen der 3D-Ansicht ab:
``Fatal Python error: Segmentation fault`` im Hauptthread (``app.exec``), fuenf
Mal nachgestellt, auch mit ``--disable-gpu``. Nachgemessen mit einem kleinen
Kindprozess auf demselben Server: Chromium sperrt dort WebGL komplett
(``WebGL1 blocklisted`` / ``WebGL2 blocklisted``), die Szene bekommt keinen
Kontext. Mit Software-Rendering (``--use-gl=angle --use-angle=swiftshader
--enable-unsafe-swiftshader --ignore-gpu-blocklist``) meldet derselbe Server
WebGL **ok**.

Ein Absturz im nativen Code laesst sich in Python nicht abfangen. Darum prueft
ein **Kindprozess** vorab (beim App-Start im Hintergrund, < 1 s):

1. mit den Flags der App — WebGL da?  -> 3D normal laden,
2. sonst mit Software-Rendering — WebGL da? -> 3D mit diesen Flags laden,
3. sonst (kein WebGL, Kindprozess abgestuerzt, haengt) -> 3D **nicht** laden,
   verstaendliche Meldung, die 2D-Ansicht bleibt.

Stuerzt der Kindprozess ab, stirbt nur er. Die Entscheidungslogik
(:func:`bewerte`, :func:`entscheide`) ist rein und offscreen testbar.

Schalter (Umgebung):
  * ``LIGHTOS_3D_PROBE=0`` — keine Probe, 3D wie frueher laden.
  * ``LIGHTOS_3D_PROBE=1`` — Probe auch ausserhalb von Linux/xcb.
  * ``LIGHTOS_3D_ERZWINGEN=1`` — 3D trotz negativer Probe laden (auf eigene Gefahr).

Grenze: Die Software-Flags wirken nur, solange QtWebEngine im Prozess noch
nicht gestartet ist (die 3D-Ansicht ist der erste WebEngine-Nutzer; hat vorher
schon die Geraete-Vorschau WebEngine gestartet, bleibt es bei der Meldung).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass

#: Chromium-Flags fuer reines Software-WebGL (SwiftShader ueber ANGLE).
SOFTWARE_FLAGS = ("--use-gl=angle --use-angle=swiftshader "
                  "--enable-unsafe-swiftshader --ignore-gpu-blocklist")

#: Zeile, die der Kindprozess ausgibt (``ok`` oder ``nogl``).
MARKE = "LIGHTOS_WEBGL="

#: Hoechstdauer je Kindprozess (Sekunden). Gemessen: ~0,6 s.
ZEIT_S = 20.0

_ENV_PROBE = "LIGHTOS_3D_PROBE"
_ENV_ERZWINGEN = "LIGHTOS_3D_ERZWINGEN"
_AUS = {"0", "false", "no", "off", "nein", "aus"}
_AN = {"1", "true", "yes", "on", "ja", "an"}

MELDUNG_AUS = (
    "Die 3D-Ansicht kann auf diesem Rechner nicht geöffnet werden: "
    "die Grafik stellt kein WebGL bereit ({grund}). Damit LightOS nicht "
    "abstürzt, bleibt die 2D-Bühne aktiv. Abhilfe: Grafiktreiber "
    "installieren oder an einem Bildschirm mit Grafikbeschleunigung "
    "starten. Erzwingen (auf eigene Gefahr): LIGHTOS_3D_ERZWINGEN=1.")
MELDUNG_SOFTWARE = ("3D läuft ohne Grafikbeschleunigung (Software-Grafik) — "
                    "langsamer, aber stabil.")

_GRUENDE = {
    "nogl": "WebGL gesperrt oder nicht vorhanden",
    "absturz": "Testprozess abgestürzt",
    "zeit": "Testprozess antwortet nicht",
    "fehler": "Testprozess konnte nicht starten",
}


@dataclass(frozen=True)
class Entscheidung:
    modus: str            # "normal" | "software" | "aus"
    grund: str = ""
    meldung: str = ""

    @property
    def erlaubt(self) -> bool:
        return self.modus != "aus"


def bewerte(rueckgabe, ausgabe: str, zeit_ueberschritten: bool = False) -> str:
    """Ein Kindprozess-Lauf -> ``ok`` | ``nogl`` | ``absturz`` | ``zeit`` | ``fehler``."""
    if zeit_ueberschritten:
        return "zeit"
    if rueckgabe is None:
        return "fehler"
    wert = ""
    for zeile in (ausgabe or "").splitlines():
        zeile = zeile.strip()
        if zeile.startswith(MARKE):
            wert = zeile[len(MARKE):].strip()
    if rueckgabe < 0:                     # durch Signal beendet (SIGSEGV ...)
        return "absturz"
    if wert == "ok" and rueckgabe == 0:
        return "ok"
    if wert == "nogl":
        return "nogl"
    return "absturz" if rueckgabe != 0 else "fehler"


def entscheide(basis: str, software: str | None, env=None) -> Entscheidung:
    """Aus den Probe-Ergebnissen den Startweg der 3D-Ansicht waehlen."""
    env = os.environ if env is None else env
    if basis == "ok":
        return Entscheidung("normal")
    if software == "ok":
        return Entscheidung("software", basis, MELDUNG_SOFTWARE)
    grund = basis
    if str(env.get(_ENV_ERZWINGEN, "")).strip().lower() in _AN:
        return Entscheidung("normal", grund)
    text = MELDUNG_AUS.format(grund=_GRUENDE.get(grund, grund))
    return Entscheidung("aus", grund, text)


def probe_noetig(env=None, plattform: str | None = None) -> bool:
    """Nur unter Linux mit echtem Fenster-Server proben (Abwahl/Erzwingen per Env)."""
    env = os.environ if env is None else env
    plattform = sys.platform if plattform is None else plattform
    wahl = str(env.get(_ENV_PROBE, "")).strip().lower()
    if wahl in _AUS:
        return False
    if wahl in _AN:
        return True
    qpa = str(env.get("QT_QPA_PLATFORM", "")).strip().lower()
    if qpa.startswith(("offscreen", "minimal")):
        return False                      # Tests/CI: Szene laeuft dort (SwiftShader)
    return plattform.startswith("linux")


def _kind_lauf(flags: str, ausfuehren=subprocess.run, zeit_s: float = ZEIT_S) -> str:
    env = dict(os.environ)
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    try:
        r = ausfuehren([sys.executable, "-I", os.path.abspath(__file__), "--kind"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=zeit_s, env=env)
    except subprocess.TimeoutExpired:
        return bewerte(None, "", True)
    except Exception:
        return "fehler"
    return bewerte(r.returncode, r.stdout or "")


def pruefen(ausfuehren=subprocess.run, env=None) -> Entscheidung:
    """Beide Stufen der Probe laufen lassen und entscheiden (blockiert < ~2 s)."""
    env = os.environ if env is None else env
    basis_flags = str(env.get("QTWEBENGINE_CHROMIUM_FLAGS", "")).strip()
    basis = _kind_lauf(basis_flags, ausfuehren)
    software = None
    if basis != "ok":
        software = _kind_lauf(f"{basis_flags} {SOFTWARE_FLAGS}".strip(), ausfuehren)
    return entscheide(basis, software, env)


# ── Hintergrund-Probe + einmalige Anwendung ────────────────────────────────
_lock = threading.Lock()
_thread: threading.Thread | None = None
_ergebnis: Entscheidung | None = None
_angewandt = False


def starte_hintergrund() -> None:
    """Beim App-Start: Probe im Hintergrund, damit der 3D-Knopf nicht wartet."""
    global _thread
    if not probe_noetig():
        return
    with _lock:
        if _thread is not None or _ergebnis is not None:
            return

        def _lauf():
            global _ergebnis
            try:
                e = pruefen()
            except Exception as ex:          # nie die App gefaehrden
                e = entscheide("fehler", "fehler", {})
                print(f"[webgl_probe] Probe fehlgeschlagen: {ex}")
            _ergebnis = e

        _thread = threading.Thread(target=_lauf, name="webgl-probe", daemon=True)
        _thread.start()


def vor_3d_start(warte_s: float = 2 * ZEIT_S + 5) -> Entscheidung:
    """Vor dem ERSTEN Bau einer 3D-Ansicht aufrufen. Ergebnis wird gemerkt.

    ``software`` setzt die Software-Flags in ``QTWEBENGINE_CHROMIUM_FLAGS``
    (nur einmal). ``aus`` heisst: 3D NICHT bauen, ``meldung`` zeigen.
    """
    global _ergebnis, _angewandt
    if not probe_noetig():
        return Entscheidung("normal")
    t = _thread
    if t is not None:
        t.join(warte_s)
    if _ergebnis is None:
        _ergebnis = pruefen()
    e = _ergebnis
    if e.modus == "software" and not _angewandt:
        alt = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        if SOFTWARE_FLAGS not in alt:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{alt} {SOFTWARE_FLAGS}".strip()
        _angewandt = True
        print(f"[webgl_probe] {MELDUNG_SOFTWARE}")
    elif e.modus == "aus":
        print(f"[webgl_probe] 3D gesperrt: {e.grund}")
    return e


def _zuruecksetzen_fuer_test() -> None:
    global _thread, _ergebnis, _angewandt
    _thread = None
    _ergebnis = None
    _angewandt = False


# ── Kindprozess ────────────────────────────────────────────────────────────
_KIND_JS = ("(function(){try{var c=document.createElement('canvas');"
            "var g=c.getContext('webgl2')||c.getContext('webgl');"
            "return g?'ok':'nogl';}catch(e){return 'nogl';}})()")


def _kind_main() -> int:                  # pragma: no cover - laeuft im Kindprozess
    from PySide6.QtCore import QCoreApplication, Qt, QTimer
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    app = QApplication([sys.argv[0]])
    view = QWebEngineView()
    view.resize(160, 120)
    # Pruef-Fund: nie ein sichtbares Fenster (Kiosk/Fokus) — die WebGL-
    # Probe liefert verdeckt dasselbe Ergebnis (in Xephyr nachgemessen).
    view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    def _fertig(wert):
        print(f"{MARKE}{wert if wert == 'ok' else 'nogl'}", flush=True)
        app.exit(0)

    view.loadFinished.connect(
        lambda _ok: view.page().runJavaScript(_KIND_JS, 0, _fertig))
    view.setHtml("<html><body></body></html>")
    view.show()
    QTimer.singleShot(int(ZEIT_S * 1000) - 2000, lambda: app.exit(3))
    return app.exec()


if __name__ == "__main__" and "--kind" in sys.argv:   # pragma: no cover
    sys.exit(_kind_main())
