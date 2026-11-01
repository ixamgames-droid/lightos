"""ENG-39: gelbe Hinweiszeile „diese Taste und … steuern beide …“.

Reihenfolge der Saetze: zuerst alle, gegen die diese Taste VERLIERT, dann
Gleichstand, dann die, gegen die sie gewinnt. Verlierer-Faelle verschwinden nie
hinter „… und n weitere“; der Tooltip traegt immer die vollstaendige Liste.

Reine Auskunft: die Zeile aendert nichts, blockiert nichts und oeffnet keinen
Dialog. Gerechnet wird nur beim Oeffnen der Eigenschaften und wenn sich die
Funktion der Taste, eine Stufe oder eine Funktion aendert — nie im Bild-Takt.
Die Rechnung selbst steht ohne Qt in ``src/core/engine/ueberschneidung.py``.

Betrachtet werden nur Funktionen, die auf einem anderen Bedienelement liegen:
auf einer Taste („Funktion an/aus“, „Funktion (nur gehalten)“) oder auf einem
Effekt-Fader. Ein Fader zaehlt IMMER mit — auch ohne den Haken „bei 0 wirklich
stoppen“: dann laeuft sein Effekt bei 0 unsichtbar weiter und belegt die
Geraete, und genau das sagt der Hinweis in einem eigenen Satz.

Exklusiv-Gruppe = Solo-Frame (``VCFrame.is_solo``, gespeichert als ``solo``):
Tasten, die DIREKT im selben Solo-Frame liegen, schalten sich gegenseitig aus
— zwischen ihnen gibt es keinen Hinweis, gegen alles ausserhalb weiterhin.
Das folgt genau dem, was ``VCFrame.on_child_activated`` tut: er schaltet nur
seine direkten Kinder aus und nur solche mit ``deactivate_for_solo`` (Tasten).
Ein Fader im Solo-Frame, eine Taste in einem Unter-Rahmen und Tasten zweier
verschiedener Solo-Frames gehoeren deshalb NICHT zur selben Gruppe.

ENG-41 — Tasten-Haken und Live-Edit-Slot: „Andere Funktionen stoppen (nur
diese aktiv)“, „Andere Effekte auf denselben Geräten stoppen“ und ein
gemeinsamer Live-Edit-Slot stoppen beim Start einer Taste andere Funktionen
(``VCButton._start_function_group``). Stoppen sich zwei Seiten GEGENSEITIG,
laufen sie nie zusammen — dann gibt es keinen Hinweis, wie in einer
Exklusiv-Gruppe. Stoppt nur eine Seite die andere, laufen beide, sobald die
andere danach startet: der Hinweis bleibt und benennt das Stoppen. Die
Zeile zieht nach, wenn ein ANDERES Bedienelement umbelegt wird
(:func:`belegung_geaendert`).
"""
from __future__ import annotations

import dataclasses
import weakref

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractScrollArea, QLabel, QSizePolicy

from src.core.engine import ueberschneidung

HINWEIS_STIL = ("QLabel#vcUeberschneidungsHinweis { background:#3a3214; "
                "color:#f2d675; border:1px solid #8a7426; border-radius:4px; "
                "padding:6px; }")

HINWEIS_TOOLTIP = (
    "Nur ein Hinweis — er ändert und sperrt nichts.\n"
    "Er erscheint, wenn eine andere Taste oder ein Fader der Virtual Console "
    "an denselben Geräten denselben Baustein steuert (Dimmer, Farbe, Bewegung "
    "oder Gobo). Farbe und Dimmer sind getrennt und stören sich nicht.\n"
    "Ein Fader zählt immer mit. Stoppt er seinen Effekt bei 0 nicht wirklich, "
    "läuft der Effekt dort weiter und belegt die Geräte — der Hinweis sagt "
    "das dazu.\n"
    "Tasten im selben Solo-Frame schalten sich gegenseitig aus; zwischen "
    "ihnen gibt es keinen Hinweis. Ebenso nicht, wenn sich zwei Tasten beim "
    "Start gegenseitig stoppen („Andere Funktionen stoppen“, „Andere Effekte "
    "auf denselben Geräten stoppen“ oder derselbe Live-Edit-Slot); stoppt nur "
    "eine die andere, sagt der Hinweis das dazu.\n"
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


def exklusiv_gruppe(widget):
    """Der Solo-Frame, dessen Exklusiv-Gruppe ``widget`` angehoert — sonst
    None. Dazu gehoert nur, was DIREKT im Solo-Frame liegt und sich von ihm
    ausschalten laesst (``deactivate_for_solo``, also Tasten): genau diese
    Elemente schaltet ``VCFrame.on_child_activated`` gegenseitig aus."""
    if not callable(getattr(widget, "deactivate_for_solo", None)):
        return None
    try:
        eltern = widget.parentWidget()
    except RuntimeError:
        return None
    ist_solo = getattr(eltern, "is_solo", None)
    try:
        return eltern if callable(ist_solo) and ist_solo() else None
    except Exception:
        return None


def _effekt_fader(widget) -> bool:
    from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
    return (isinstance(widget, VCSlider)
            and widget.mode in (SliderMode.EFFECT_INTENSITY,
                                SliderMode.EFFECT_SPEED,
                                SliderMode.EFFECT_PARAM))


def _start_ids(widget) -> list[int]:
    """Funktions-IDs, die ``widget`` fest steuert — leer fuer alles, was nur
    Tempo, Programmer oder Pegel regelt oder gar keine Funktion traegt. Ein
    Effekt-Fader zaehlt immer, mit und ohne „bei 0 wirklich stoppen“."""
    from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
    try:
        if isinstance(widget, VCButton):
            if widget.action in (ButtonAction.FUNCTION_TOGGLE,
                                 ButtonAction.FUNCTION_FLASH):
                return list(widget._all_function_ids())
        elif _effekt_fader(widget):
            return list(widget._all_target_fids())
    except Exception:
        return []
    return []


def haelt_bei_null(widget) -> bool:
    """Effekt-Fader OHNE „bei 0 wirklich stoppen“: sein Effekt laeuft bei 0
    weiter."""
    try:
        return (_effekt_fader(widget)
                and not getattr(widget, "effect_autostart", False))
    except Exception:
        return False


def _bedienelemente(wurzel) -> list[tuple]:
    """``(Element, Funktions-IDs, Exklusiv-Gruppe, haelt bei 0)`` fuer jedes
    Bedienelement unter ``wurzel``, das eine Funktion fest steuert."""
    if wurzel is None:
        return []
    from src.ui.virtualconsole.vc_widget import VCWidget
    try:
        alle = wurzel.findChildren(VCWidget)
    except RuntimeError:
        return []
    aus = []
    for w in alle:
        ids = _start_ids(w)
        if ids:
            aus.append((w, ids, exklusiv_gruppe(w), haelt_bei_null(w)))
    return aus


def konsolen_funktions_ids(wurzel, ausser=None) -> list[int]:
    """IDs aller Funktionen, die auf einer Taste oder einem Fader unter
    ``wurzel`` liegen — ohne ``ausser`` selbst und ohne die Tasten seiner
    Exklusiv-Gruppe (selber Solo-Frame). Reihenfolge stabil, ohne Doppelte."""
    gruppe = exklusiv_gruppe(ausser) if ausser is not None else None
    ids: list[int] = []
    gesehen: set[int] = set()
    for w, eigene, ihre_gruppe, _haelt in _bedienelemente(wurzel):
        if w is ausser:
            continue
        if gruppe is not None and ihre_gruppe is gruppe:
            continue
        for fid in eigene:
            if fid not in gesehen:
                gesehen.add(fid)
                ids.append(fid)
    return ids


def haltende_ids(wurzel, ausser=None) -> set[int]:
    """IDs der Funktionen, die auf einem Fader ohne „bei 0 wirklich stoppen“
    liegen (ohne ``ausser`` selbst)."""
    return {int(fid) for w, ids, _g, haelt in _bedienelemente(wurzel)
            if haelt and w is not ausser for fid in ids}


# ── ENG-41: Tasten, die beim Start andere stoppen ───────────────────────────

class _BelegungsMelder(QObject):
    """Sagt offenen Hinweiszeilen Bescheid, wenn ein Bedienelement der
    Virtual Console umbelegt, angelegt oder entfernt wurde. Dafuer gibt es
    kein Sync-Ereignis; ohne das bliebe die Zeile stehen, bis der Dialog neu
    geoeffnet wird."""
    geaendert = Signal()


_belegung: _BelegungsMelder | None = None


def belegung_melder() -> _BelegungsMelder:
    global _belegung
    if _belegung is None:
        _belegung = _BelegungsMelder()
    return _belegung


def belegung_geaendert() -> None:
    """Ein Bedienelement wurde umbelegt — offene Hinweiszeilen rechnen beim
    naechsten Umlauf neu (mehrere Meldungen ergeben EINE Rechnung)."""
    try:
        belegung_melder().geaendert.emit()
    except Exception as e:
        print(f"[ueberschneidung_hinweis] belegung_geaendert: {e}")


@dataclasses.dataclass(frozen=True)
class StartRegeln:
    """Was eine Taste beim Start stoppt (``VCButton._start_function_group``).

    ``alles``: „Andere Funktionen stoppen (nur diese aktiv)“ — greift nur OHNE
    Live-Edit-Slot (sonst gilt der Slot). ``gleiche_geraete``: „Andere Effekte
    auf denselben Geräten stoppen“. ``edit_slot``: stoppt das Bearbeitungsziel
    desselben Slots, also die erste Funktion einer anderen Taste mit diesem
    Slot."""
    alles: bool = False
    gleiche_geraete: bool = False
    edit_slot: str = ""

    @classmethod
    def aus(cls, exklusiv, gleiche_geraete, edit_slot) -> "StartRegeln":
        slot = str(edit_slot or "").strip()
        return cls(alles=bool(exklusiv) and not slot,
                   gleiche_geraete=bool(gleiche_geraete), edit_slot=slot)


def start_regeln(widget) -> StartRegeln | None:
    """Die Start-Regeln einer Funktions-Taste — None fuer alles andere (ein
    Fader stoppt beim Start nichts)."""
    from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
    try:
        if (isinstance(widget, VCButton)
                and widget.action in (ButtonAction.FUNCTION_TOGGLE,
                                      ButtonAction.FUNCTION_FLASH)):
            return StartRegeln.aus(widget.exclusive, widget.solo_fixtures,
                                   widget.edit_slot)
    except Exception:
        return None
    return None


def stoppt_beim_start(regeln, eigene_ids, ihre_regeln, ihre_ids, fid) -> bool:
    """Stoppt ein Element mit ``regeln`` (startet ``eigene_ids``) beim Start
    sicher die Funktion ``fid`` eines Elements mit ``ihre_regeln`` /
    ``ihre_ids``? Gefragt wird nur fuer Funktionen, die mit den eigenen
    Geraete teilen (sonst gaebe es keine Ueberschneidung) — darum genuegt
    „Andere Effekte auf denselben Geräten stoppen“."""
    if regeln is None:
        return False
    try:
        fid = int(fid)
        eigene = {int(i) for i in eigene_ids or ()}
    except (TypeError, ValueError):
        return False
    # Startet das Element ``fid`` selbst mit, stoppt es sie nicht: ``stop_all``
    # laeuft VOR dem Start, ``stop_others_sharing_fixture_group`` schuetzt die
    # eigenen Ziele, und der Slot stoppt nur ein Ziel ausserhalb der Gruppe.
    if fid in eigene:
        return False
    if regeln.alles or regeln.gleiche_geraete:
        return True
    if (regeln.edit_slot and ihre_regeln is not None
            and ihre_regeln.edit_slot == regeln.edit_slot and ihre_ids):
        try:
            return int(ihre_ids[0]) == fid
        except (TypeError, ValueError):
            return False
    return False


def gegenueber_elemente(wurzel, ausser=None) -> list[tuple]:
    """``(Funktions-IDs, Start-Regeln)`` jedes Bedienelements, gegen das der
    Hinweis an ``ausser`` rechnet — ohne ``ausser`` selbst und ohne seine
    Exklusiv-Gruppe (wie :func:`konsolen_funktions_ids`)."""
    gruppe = exklusiv_gruppe(ausser) if ausser is not None else None
    aus = []
    for w, ids, ihre_gruppe, _haelt in _bedienelemente(wurzel):
        if w is ausser or (gruppe is not None and ihre_gruppe is gruppe):
            continue
        aus.append((tuple(int(i) for i in ids), start_regeln(w)))
    return aus


def stopp_regeln_anwenden(treffer, eigene_ids, eigene_regeln, elemente) -> list:
    """ENG-41: Treffer gegen Tasten, die sich beim Start GEGENSEITIG stoppen,
    fallen weg (die beiden laufen nie zusammen). Stoppt nur eine Seite die
    andere, bleibt der Treffer und traegt ``stoppt``. Liegt die andere
    Funktion auf mehreren Bedienelementen, muss es fuer JEDES gelten."""
    eigene = [int(i) for i in eigene_ids or ()]
    aus = []
    for t in treffer:
        try:
            aid = int(getattr(t.andere, "id"))
            eid = int(getattr(t.eigene, "id"))
        except (TypeError, ValueError, AttributeError):
            aus.append(t)
            continue
        traeger = [(ids, r) for ids, r in elemente if aid in ids]
        if not traeger:
            aus.append(t)
            continue
        diese = all(stoppt_beim_start(eigene_regeln, eigene, r, ids, aid)
                    for ids, r in traeger)
        andere = all(stoppt_beim_start(r, ids, eigene_regeln, eigene, eid)
                     for ids, r in traeger)
        if diese and andere:
            continue
        if diese:
            t = dataclasses.replace(t, stoppt=ueberschneidung.DIESE_STOPPT)
        elif andere:
            t = dataclasses.replace(t, stoppt=ueberschneidung.ANDERE_STOPPT)
        aus.append(t)
    return aus


def konsolen_beziehungen(flaechen) -> tuple[list[int], dict[int, set[int]], set[int]]:
    """Fuer eine Sicht ueber ALLE Bedienelemente (Reiter „Prioritäten“):
    ``(IDs, Gegenueber, haltend)``. ``Gegenueber[f]`` sind die Funktionen, die
    auf einem ANDEREN Bedienelement liegen, das nicht zur selben
    Exklusiv-Gruppe gehoert — nur gegen sie gibt es einen Hinweis. Dieselbe
    Regel wie an der Taste: zwei Funktionen derselben Taste und zwei Tasten
    desselben Solo-Frames melden sich nicht."""
    elemente = []
    for flaeche in flaechen or ():
        elemente.extend(_bedienelemente(flaeche))
    ids: list[int] = []
    haltend: set[int] = set()
    gegenueber: dict[int, set[int]] = {}
    mengen = [frozenset(int(i) for i in eigene) for _w, eigene, _g, _h in elemente]
    for (w, eigene, gruppe, haelt), menge in zip(elemente, mengen):
        for fid in eigene:
            if fid not in gegenueber:
                gegenueber[int(fid)] = set()
                ids.append(int(fid))
        if haelt:
            haltend |= menge
    # Zaehlen statt jedes Element mit jedem zu vergleichen: wie viele Elemente
    # tragen eine Funktion insgesamt, wie viele davon je Exklusiv-Gruppe?
    gesamt: dict[int, int] = {}
    je_gruppe: dict[int, dict[int, int]] = {}
    for (_w, _eigene, gruppe, _haelt), menge in zip(elemente, mengen):
        in_gruppe = (je_gruppe.setdefault(id(gruppe), {})
                     if gruppe is not None else None)
        for fid in menge:
            gesamt[fid] = gesamt.get(fid, 0) + 1
            if in_gruppe is not None:
                in_gruppe[fid] = in_gruppe.get(fid, 0) + 1
    alle = frozenset(gesamt)
    ausserhalb: dict[int, frozenset] = {}       # je Gruppe: was draussen liegt
    for (_w, _eigene, gruppe, _haelt), menge in zip(elemente, mengen):
        if gruppe is None:
            # alles, was (auch) auf einem ANDEREN Element liegt
            andere = alle - {fid for fid in menge if gesamt[fid] == 1}
        else:
            schluessel = id(gruppe)
            if schluessel not in ausserhalb:
                drin = je_gruppe[schluessel]
                ausserhalb[schluessel] = frozenset(
                    fid for fid in alle if gesamt[fid] > drin.get(fid, 0))
            andere = ausserhalb[schluessel]
        for fid in menge:
            gegenueber[fid] |= andere
    for fid, menge in gegenueber.items():
        menge.discard(fid)
    return ids, gegenueber, haltend


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


def treffer_fuer(eigene_ids, andere_ids, umgebung: dict | None = None,
                 haltend=None) -> list:
    """Alle Ueberschneidungen der Funktionen ``eigene_ids`` (einer Taste) mit
    den Funktionen ``andere_ids``. Die eigenen Funktionen untereinander zaehlen
    nicht — die startet die Taste absichtlich gemeinsam. ``haltend``: IDs der
    Funktionen auf einem Fader ohne „bei 0 wirklich stoppen“."""
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
            treffer.extend(ueberschneidung.ueberschneidungen(
                f, andere, haltend=haltend, **umgebung))
    # Ueber alle eigenen Funktionen hinweg: Verlierer-Faelle zuerst.
    treffer.sort(key=ueberschneidung.sortier_schluessel)
    return treffer


# ── Die Zeile ────────────────────────────────────────────────────────────────

class UeberschneidungsHinweis(QLabel):
    """Gelbe, mehrzeilige Hinweiszeile in den Eigenschaften einer Taste oder
    eines Effekt-Faders.

    ``subjekt``: „Taste“ oder „Fader“ — so beginnt der Satz. ``haelt_selbst()``
    (nur Fader) sagt aus den FELDERN des Dialogs, ob der Haken „bei 0 wirklich
    stoppen“ fehlt.

    ``quelle()`` liefert die Funktions-IDs, die die Taste gerade starten
    wuerde (aus den Feldern der Eigenschaften, nicht aus der Taste — im
    Dialog ist die Aenderung noch nicht uebernommen), oder eine leere Liste.
    ``sichtbar_setzen(bool)`` blendet die Zeile im umgebenden Formular ein/aus.

    Breite: die Zeile bricht um und verlangt selbst keine Breite — sie macht
    weder Dialog noch Inspector breiter. Steckt sie in einem Rollbereich, der
    schmaler ist als sein Inhalt (Inspector bei 260 px), haelt sie sich an die
    SICHTBARE Breite: der gelbe Text steht dann ganz im Bild, nicht halb
    dahinter.
    """

    #: Unter dieser Breite wird die Zeile auch im schmalsten Rollbereich nicht
    #: zusammengedrueckt.
    KLEINSTE_BREITE = 120

    def __init__(self, taste, quelle, parent=None, subjekt: str = "Taste",
                 haelt_selbst=None, regeln_selbst=None):
        super().__init__(parent)
        self._taste = taste
        self._quelle = quelle
        self._subjekt = subjekt
        self._haelt_selbst = haelt_selbst
        # ENG-41: die eigenen Start-Regeln aus den FELDERN des Dialogs
        # (``StartRegeln`` oder None) — im Dialog ist noch nichts uebernommen.
        self._regeln_selbst = regeln_selbst
        self.sichtbar_setzen = None
        self._stillgelegt = False
        self.treffer: list = []
        self.setObjectName("vcUeberschneidungsHinweis")
        self.setStyleSheet(HINWEIS_STIL)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        # Breite „Ignored“: der Wunsch der Zeile zaehlt nicht, sie nimmt, was
        # das Formular hat. Hoehe folgt dem umbrochenen Text.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setToolTip(HINWEIS_TOOLTIP)
        self._rollflaeche = None        # beobachtete Sichtflaeche (oder None)
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
        # ENG-41: ein ANDERES Bedienelement wurde umbelegt.
        belegung_melder().geaendert.connect(self.veraltet)
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

    # ── Breite ──────────────────────────────────────────────────────────────

    def minimumSizeHint(self) -> QSize:
        """Nie breiter als ``KLEINSTE_BREITE`` — auch nicht mit einem langen
        Effektnamen ohne Leerzeichen."""
        s = super().minimumSizeHint()
        return QSize(min(s.width(), self.KLEINSTE_BREITE), s.height())

    def heightForWidth(self, breite: int) -> int:
        """Hoehe fuer die Breite, die die Zeile wirklich bekommt: das Formular
        fragt mit SEINER Breite, im schmalen Rollbereich ist die Zeile aber
        auf die sichtbare Breite begrenzt und braucht mehr Zeilen."""
        return super().heightForWidth(min(int(breite), self.maximumWidth()))

    def _rollbereich(self):
        try:
            w = self.parentWidget()
            while w is not None:
                if isinstance(w, QAbstractScrollArea):
                    return w
                w = w.parentWidget()
        except RuntimeError:
            pass
        return None

    def showEvent(self, event):
        super().showEvent(event)
        self._an_sichtbare_breite_halten()

    def _an_sichtbare_breite_halten(self) -> None:
        """Im Rollbereich nie breiter als das, was zu sehen ist."""
        try:
            bereich = self._rollbereich()
            if bereich is None:
                return
            flaeche = bereich.viewport()
            if self._rollflaeche is not flaeche:
                flaeche.installEventFilter(self)
                self._rollflaeche = flaeche
            inhalt = getattr(bereich, "widget", lambda: None)()
            links = (self.mapTo(inhalt, QPoint(0, 0)).x()
                     if inhalt is not None and inhalt.isAncestorOf(self) else 0)
            breite = max(self.KLEINSTE_BREITE, flaeche.width() - max(0, links))
            if self.maximumWidth() != breite:
                self.setMaximumWidth(breite)
                self.updateGeometry()
        except RuntimeError:
            pass                        # Zeile oder Rollbereich schon abgebaut

    def eventFilter(self, obj, event):
        if obj is self._rollflaeche and event.type() == QEvent.Type.Resize:
            self._an_sichtbare_breite_halten()
        return False

    def stilllegen(self) -> None:
        """Ab jetzt nicht mehr nachrechnen. Der Eigenschaften-Dialog ruft das
        nach dem Schliessen: er bleibt als Kind der Taste bestehen, und ohne
        das rechnete jede je geoeffnete Zeile bei jeder Aenderung weiter."""
        self._stillgelegt = True
        try:
            self._sammler.stop()
        except RuntimeError:
            pass

    def veraltet(self, *_a) -> None:
        """Etwas hat sich geaendert — beim naechsten Umlauf neu rechnen."""
        if self._stillgelegt:
            return
        try:
            self._sammler.start()
        except RuntimeError:
            pass                        # Zeile schon abgebaut

    def _eigene_regeln(self):
        if callable(self._regeln_selbst):
            try:
                return self._regeln_selbst()
            except Exception:
                return None
        return start_regeln(self._taste)

    def neu_berechnen(self, *_a) -> None:
        try:
            eigene = list(self._quelle() or ())
        except Exception:
            eigene = []
        treffer: list = []
        # Nur der Fader weiss, ob ER den Effekt bei 0 weiterlaufen laesst —
        # sonst haelt ihn (wenn ueberhaupt) ein anderer Fader.
        selbst_haelt = None
        if eigene:
            try:
                wurzel = wurzel_von(self._taste)
                andere = konsolen_funktions_ids(wurzel, ausser=self._taste)
                if andere:
                    haltend = haltende_ids(wurzel, ausser=self._taste)
                    if callable(self._haelt_selbst):
                        selbst_haelt = bool(self._haelt_selbst())
                        if selbst_haelt:
                            haltend |= {int(i) for i in eigene}
                    treffer = treffer_fuer(eigene, andere, haltend=haltend)
                    if treffer:
                        treffer = stopp_regeln_anwenden(
                            treffer, eigene, self._eigene_regeln(),
                            gegenueber_elemente(wurzel, ausser=self._taste))
            except Exception as e:
                print(f"[ueberschneidung_hinweis] Rechnung: {e}")
                treffer = []
        self.treffer = treffer
        mehrere = len(set(eigene)) > 1
        zeilen = ueberschneidung.hinweis_zeilen(treffer, self._subjekt,
                                                nenne_eigene=mehrere,
                                                selbst_haelt=selbst_haelt)
        # Der Tooltip traegt IMMER die vollstaendige Liste — auch das, was die
        # Zeile in „… und n weitere“ zusammenfasst.
        alle = ueberschneidung.hinweis_zeilen(treffer, self._subjekt,
                                              nenne_eigene=mehrere,
                                              hoechstens=None,
                                              selbst_haelt=selbst_haelt)
        try:
            self.setText("\n".join(zeilen))
            self.setToolTip("\n".join(alle) + "\n\n" + HINWEIS_TOOLTIP
                            if alle else HINWEIS_TOOLTIP)
            self.updateGeometry()
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
