"""STAB-31 (2): JS-Konsole des Visualizers ins Diagnose-Log.

Ohne Weiterleitung reicht Qts Standard-``javaScriptConsoleMessage`` nur
Warnungen/Fehler als nackte Qt-Meldung weiter (Kategorie ``js``) — ohne Stufe,
Zeile und Quelle und ungedrosselt; ``console.log`` kommt gar nicht an. Diese
Seite schreibt stattdessen eine Zeile

    [viz-js:<herkunft>] FEHLER stage_scene.html:42 — <Meldung>

ueber ``print`` (also durch den Tee ins Sitzungs-Log, STAB-30).

* Warnungen und Fehler immer, Info (``console.log``) nur mit ``LIGHTOS_DEBUG``.
* Gedrosselt: dieselbe Meldung (Herkunft, Stufe, Quelle, Zeile, Text) hoechstens
  ``MAX_GLEICH`` Mal je ``FENSTER_S`` Sekunden, alle zusammen hoechstens
  ``MAX_GESAMT`` je Fenster; was wegfaellt, wird beim naechsten Durchlassen als
  Zaehler nachgetragen — auch ein Fehler im Render-Takt flutet das Log nicht.
* Die GPU-Tier-Zeile (``console.warn``) geht wie bisher an
  ``diagnose_log.merke_viz_gpu`` (STAB-33), auch wenn sie gedrosselt wird.
* Wirft nie — ein Fehler hier darf die Seite nicht stoeren.
"""
from __future__ import annotations

import threading
import time

from PySide6.QtWebEngineCore import QWebEnginePage

MAX_GLEICH = 5
MAX_GESAMT = 60
FENSTER_S = 60.0
_MAX_TEXT = 500
_MAX_SCHLUESSEL = 500

_L = QWebEnginePage.JavaScriptConsoleMessageLevel
_STUFEN = {
    _L.InfoMessageLevel: "INFO",
    _L.WarningMessageLevel: "WARNUNG",
    _L.ErrorMessageLevel: "FEHLER",
}


def _quelle_kurz(source) -> str:
    """Nur der Dateiname der Quelle (keine lokalen Pfade ins Log)."""
    try:
        s = str(source or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
        return s.rsplit("/", 1)[-1] or "?"
    except Exception:
        return "?"


def _debug_an() -> bool:
    try:
        from src.core import debug_log
        return debug_log.is_enabled()
    except Exception:
        return False


class JsKonsolenWeiterleitung:
    """Drosselt und formatiert JS-Konsolen-Meldungen; ``melde`` gibt die
    tatsaechlich geschriebenen Zeilen zurueck (fuer Tests)."""

    def __init__(self, *, max_gleich: int = MAX_GLEICH, max_gesamt: int = MAX_GESAMT,
                 fenster_s: float = FENSTER_S, uhr=time.monotonic, ausgabe=print):
        self._max_gleich = max_gleich
        self._max_gesamt = max_gesamt
        self._fenster_s = fenster_s
        self._uhr = uhr
        self._ausgabe = ausgabe
        self._lock = threading.Lock()
        self._fenster_start = None
        self._gesamt = 0
        self._gesamt_weg = 0
        # schluessel -> [anzahl im Fenster, unterdrueckt seit letzter Zeile]
        self._je_meldung: dict[tuple, list[int]] = {}

    def _fenster_pruefen(self, jetzt: float) -> list[str]:
        if self._fenster_start is not None and jetzt - self._fenster_start < self._fenster_s:
            return []
        nachtrag = []
        if self._gesamt_weg:
            nachtrag.append(f"[viz-js] {self._gesamt_weg} weitere JS-Meldungen "
                            "im letzten Fenster unterdrueckt")
        self._fenster_start = jetzt
        self._gesamt = 0
        self._gesamt_weg = 0
        # Zaehler zuruecksetzen, Unterdrueckt-Zaehler behalten (Nachtrag beim
        # naechsten Auftreten); ganz ruhige Eintraege verwerfen.
        self._je_meldung = {k: [0, v[1]] for k, v in self._je_meldung.items() if v[1]}
        if len(self._je_meldung) > _MAX_SCHLUESSEL:
            self._je_meldung.clear()
        return nachtrag

    def melde(self, stufe: str, meldung, zeile=0, quelle="", herkunft: str = "viz") -> list[str]:
        try:
            text = str(meldung if meldung is not None else "")
            if stufe == "WARNUNG":
                try:
                    from src.core import diagnose_log
                    diagnose_log.merke_viz_gpu(text)
                except Exception:
                    pass
            if stufe == "INFO" and not _debug_an():
                return []
            text = text[:_MAX_TEXT]
            ort = f"{_quelle_kurz(quelle)}:{int(zeile or 0)}"
            schluessel = (herkunft, stufe, ort, text)
            with self._lock:
                aus = self._fenster_pruefen(self._uhr())
                eintrag = self._je_meldung.setdefault(schluessel, [0, 0])
                if eintrag[0] >= self._max_gleich or self._gesamt >= self._max_gesamt:
                    eintrag[1] += 1
                    if self._gesamt >= self._max_gesamt:
                        self._gesamt_weg += 1
                        if self._gesamt_weg == 1:
                            aus.append("[viz-js] zu viele JS-Meldungen — weitere in "
                                       "diesem Fenster werden unterdrueckt")
                    zeilen = aus
                else:
                    eintrag[0] += 1
                    self._gesamt += 1
                    zusatz = f" (+{eintrag[1]} gleiche unterdrueckt)" if eintrag[1] else ""
                    eintrag[1] = 0
                    zeilen = aus + [f"[viz-js:{herkunft}] {stufe} {ort} — {text}{zusatz}"]
            if not zeilen:
                return []
            try:
                from src.core.diagnose_log import anonymisiere
                zeilen = [anonymisiere(z) for z in zeilen]
            except Exception:
                pass
            for z in zeilen:
                self._ausgabe(z)
            return zeilen
        except Exception:
            return []


#: eine gemeinsame Drossel fuer alle Visualizer-Seiten (Fenster + eingebettet)
WEITERLEITUNG = JsKonsolenWeiterleitung()


class KonsolenPage(QWebEnginePage):
    """``QWebEnginePage`` mit JS-Konsolen-Weiterleitung ins Diagnose-Log."""

    def __init__(self, parent=None, *, herkunft: str = "viz", weiterleitung=None):
        super().__init__(parent)
        self._herkunft = herkunft
        self._weiterleitung = weiterleitung

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        try:
            (self._weiterleitung or WEITERLEITUNG).melde(
                _STUFEN.get(level, "INFO"), message, lineNumber, sourceID,
                herkunft=self._herkunft)
        except Exception:
            pass


def installiere_js_konsole(view, herkunft: str = "viz"):
    """Ersetzt die Standard-Seite einer frischen ``QWebEngineView`` durch eine
    ``KonsolenPage``. Direkt nach dem Erzeugen aufrufen — vor Profil-/Settings-
    Zugriffen und Signal-Verbindungen, die sonst an der alten Seite haengen.
    Scheitert es, bleibt die Standard-Seite (gemeldet, nie geworfen)."""
    try:
        page = KonsolenPage(view, herkunft=herkunft)
        view.setPage(page)
        return page
    except Exception as e:
        try:
            from src.core.diagnose_log import melde_still
            melde_still("viz.js_konsole", e)
        except Exception:
            pass
        return None
