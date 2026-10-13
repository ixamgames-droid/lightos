"""ENG-39: gelbe Hinweiszeile „diese Taste und … steuern beide …“.

Reine Auskunft: die Zeile aendert nichts, blockiert nichts und oeffnet keinen
Dialog. Gerechnet wird nur beim Oeffnen der Eigenschaften und wenn sich die
Funktion der Taste, eine Stufe oder eine Funktion aendert — nie im Bild-Takt.
Die Rechnung selbst steht ohne Qt in ``src/core/engine/ueberschneidung.py``.

Betrachtet werden nur Funktionen, die der Bediener gleichzeitig starten kann:
solche, die auf einer anderen Taste („Funktion an/aus“, „Funktion (nur
gehalten)“) oder auf einem Effekt-Fader liegen, der seinen Effekt auch startet
und stoppt (Haken „bei 0 wirklich stoppen“). Tasten im selben Solo-Rahmen
zaehlen nicht — dort ist immer nur eine aktiv.
"""
from __future__ import annotations

import weakref

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QSizePolicy

from src.core.engine import ueberschneidung

HINWEIS_STIL = ("QLabel#vcUeberschneidungsHinweis { background:#3a3214; "
                "color:#f2d675; border:1px solid #8a7426; border-radius:4px; "
                "padding:6px; }")

HINWEIS_TOOLTIP = (
    "Nur ein Hinweis — er ändert und sperrt nichts.\n"
    "Er erscheint, wenn eine andere Taste oder ein Fader der Virtual Console "
    "an denselben Geräten denselben Baustein steuert (Dimmer, Farbe, Bewegung "
    "oder Gobo). Farbe und Dimmer sind getrennt und stören sich nicht.\n"
    "Die höhere Stufe gewinnt; bei gleicher Stufe gewinnt, wer zuletzt "
    "gestartet wurde. Die Stufe stellst du im Editor des Effekts oder im "
    "Reiter „Prioritäten“ ein.")


# ── Was liegt auf der Virtual Console? ───────────────────────────────────────

def wurzel_von(widget):
    """Die oberste Flaeche der Virtual Console ueber ``widget`` (oder None)."""
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    gefunden = None
    w = widget
    while w is not None:
        if isinstance(w, VCCanvas):
            gefunden = w
        try:
            w = w.parentWidget()
        except RuntimeError:
            break
    return gefunden


def _solo_rahmen(widget):
    """Der Solo-Rahmen, in dem ``widget`` DIREKT liegt (sonst None)."""
    try:
        eltern = widget.parentWidget()
    except RuntimeError:
        return None
    ist_solo = getattr(eltern, "is_solo", None)
    try:
        return eltern if callable(ist_solo) and ist_solo() else None
    except Exception:
        return None


def _start_ids(widget) -> list[int]:
    """Funktions-IDs, die ``widget`` STARTEN kann — leer fuer alles, was nur
    regelt (Tempo, Parameter) oder gar keine Funktion traegt."""
    from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
    from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
    try:
        if isinstance(widget, VCButton):
            if widget.action in (ButtonAction.FUNCTION_TOGGLE,
                                 ButtonAction.FUNCTION_FLASH):
                return list(widget._all_function_ids())
        elif isinstance(widget, VCSlider):
            if (widget.mode in (SliderMode.EFFECT_INTENSITY,
                                SliderMode.EFFECT_SPEED,
                                SliderMode.EFFECT_PARAM)
                    and getattr(widget, "effect_autostart", False)):
                return list(widget._all_target_fids())
    except Exception:
        return []
    return []


def konsolen_funktions_ids(wurzel, ausser=None) -> list[int]:
    """IDs aller Funktionen, die auf einer Taste oder einem Fader unter
    ``wurzel`` liegen — ohne ``ausser`` selbst und ohne dessen Geschwister im
    selben Solo-Rahmen. Reihenfolge stabil, ohne Doppelte."""
    if wurzel is None:
        return []
    from src.ui.virtualconsole.vc_widget import VCWidget
    solo = _solo_rahmen(ausser) if ausser is not None else None
    ids: list[int] = []
    gesehen: set[int] = set()
    try:
        alle = wurzel.findChildren(VCWidget)
    except RuntimeError:
        return []
    for w in alle:
        if w is ausser:
            continue
        if solo is not None and _solo_rahmen(w) is solo:
            continue
        for fid in _start_ids(w):
            if fid not in gesehen:
                gesehen.add(fid)
                ids.append(fid)
    return ids


# ── Auskuenfte aus der Show ──────────────────────────────────────────────────

def rechen_umgebung() -> dict:
    """Die Auskunfts-Funktionen fuer ``ueberschneidung.ueberschneidungen`` aus
    dem laufenden Zustand. Jede einzelne darf fehlen — dann meldet der Kern
    lieber nichts als etwas Falsches."""
    from src.core.app_state import get_state
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    state = get_state()

    geraete: dict[int, object] = {}
    try:
        for fx in state.get_patched_fixtures():
            geraete[int(fx.fid)] = fx
    except Exception as e:
        print(f"[ueberschneidung_hinweis] patch error: {e}")

    tabellen: dict[int, dict[int, str] | None] = {}

    def kanal_attribut(fid: int, kanal: int):
        if fid not in tabellen:
            fx = geraete.get(fid)
            tabelle = None
            if fx is not None:
                try:
                    from src.core.app_state import get_channels_for_patched
                    tabelle = {int(ch.channel_number): str(ch.attribute or "")
                               for ch in get_channels_for_patched(fx)}
                except Exception:
                    tabelle = None
            tabellen[fid] = tabelle
        tabelle = tabellen[fid]
        return tabelle.get(kanal) if tabelle else None

    def geraete_von(funktion):
        try:
            return fm.affected_fids(int(funktion.id))
        except Exception:
            return ()

    def geraete_name(fid: int):
        fx = geraete.get(int(fid))
        name = getattr(fx, "name", None) or getattr(fx, "label", None)
        return str(name) if name else None

    gruppen: list[tuple[str, list[int]]] = []
    try:
        for g in state.list_fixture_groups():
            gruppen.append((str(g.get("name") or ""), list(g.get("fids") or ())))
    except Exception as e:
        print(f"[ueberschneidung_hinweis] gruppen error: {e}")

    return {"aufloesen": fm.get, "geraete_von": geraete_von,
            "kanal_attribut": kanal_attribut, "gruppen": gruppen,
            "geraete_name": geraete_name, "cache": {}}


def treffer_fuer(eigene_ids, andere_ids, umgebung: dict | None = None) -> list:
    """Alle Ueberschneidungen der Funktionen ``eigene_ids`` (einer Taste) mit
    den Funktionen ``andere_ids``. Die eigenen Funktionen untereinander zaehlen
    nicht — die startet die Taste absichtlich gemeinsam."""
    umgebung = umgebung if umgebung is not None else rechen_umgebung()
    aufloesen = umgebung["aufloesen"]
    eigene_menge = set()
    for i in eigene_ids or ():
        try:
            eigene_menge.add(int(i))
        except (TypeError, ValueError):
            continue
    andere = [f for f in (aufloesen(i) for i in andere_ids or ()
                          if i not in eigene_menge) if f is not None]
    if not andere:
        return []
    treffer: list = []
    for fid in eigene_ids or ():
        try:
            f = aufloesen(int(fid))
        except (TypeError, ValueError):
            continue
        if f is not None:
            treffer.extend(ueberschneidung.ueberschneidungen(f, andere, **umgebung))
    treffer.sort(key=lambda t: ueberschneidung._RANG[t.verhaeltnis])
    return treffer


# ── Die Zeile ────────────────────────────────────────────────────────────────

class UeberschneidungsHinweis(QLabel):
    """Gelbe, mehrzeilige Hinweiszeile in den Eigenschaften einer Taste.

    ``quelle()`` liefert die Funktions-IDs, die die Taste gerade starten
    wuerde (aus den Feldern der Eigenschaften, nicht aus der Taste — im
    Dialog ist die Aenderung noch nicht uebernommen), oder eine leere Liste.
    ``sichtbar_setzen(bool)`` blendet die Zeile im umgebenden Formular ein/aus.
    """

    def __init__(self, taste, quelle, parent=None):
        super().__init__(parent)
        self._taste = taste
        self._quelle = quelle
        self.sichtbar_setzen = None
        self.treffer: list = []
        self.setObjectName("vcUeberschneidungsHinweis")
        self.setStyleSheet(HINWEIS_STIL)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setMinimumWidth(160)
        self.setToolTip(HINWEIS_TOOLTIP)
        # Kein Dauer-Zeitgeber: nur ein Sammler, der mehrere Meldungen im
        # selben Augenblick zu EINER Rechnung zusammenfasst.
        self._sammler = QTimer(self)
        self._sammler.setSingleShot(True)
        self._sammler.setInterval(0)
        self._sammler.timeout.connect(self.neu_berechnen)
        try:
            from src.ui.widgets.stufe_auswahl import stufen_melder
            stufen_melder().geaendert.connect(self.veraltet)
        except Exception as e:
            print(f"[ueberschneidung_hinweis] stufen_melder error: {e}")
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            ref = weakref.ref(self)

            def _veraltet(*_a, _ref=ref):
                w = _ref()
                if w is not None:
                    w.veraltet()

            for ev in (SyncEvent.FUNCTION_CHANGED, SyncEvent.SHOW_LOADED,
                       SyncEvent.PATCH_CHANGED):
                sync.subscribe_widget(ev, self, _veraltet)
        except Exception as e:
            print(f"[ueberschneidung_hinweis] sync subscribe error: {e}")
        self.neu_berechnen()

    def veraltet(self, *_a) -> None:
        """Etwas hat sich geaendert — beim naechsten Umlauf neu rechnen."""
        try:
            self._sammler.start()
        except RuntimeError:
            pass                        # Zeile schon abgebaut

    def neu_berechnen(self, *_a) -> None:
        try:
            eigene = list(self._quelle() or ())
        except Exception:
            eigene = []
        treffer: list = []
        if eigene:
            try:
                andere = konsolen_funktions_ids(wurzel_von(self._taste),
                                                ausser=self._taste)
                if andere:
                    treffer = treffer_fuer(eigene, andere)
            except Exception as e:
                print(f"[ueberschneidung_hinweis] Rechnung: {e}")
                treffer = []
        self.treffer = treffer
        zeilen = ueberschneidung.hinweis_zeilen(
            treffer, "Taste", nenne_eigene=len(set(eigene)) > 1)
        try:
            self.setText("\n".join(zeilen))
        except RuntimeError:
            return
        # Ein-/Ausblenden macht das umgebende Formular (ganze Zeile samt
        # Beschriftung). Ohne Formular bleibt die Zeile, wie sie ist — ein
        # elternloses Widget wuerde sonst als eigenes Fenster aufgehen.
        if callable(self.sichtbar_setzen):
            try:
                self.sichtbar_setzen(bool(zeilen))
            except Exception:
                pass

    def hat_hinweis(self) -> bool:
        return bool(self.text())
