"""FM-52: Eigener Rueckgaengig-Verlauf des Programmers.

Der globale Undo-Stapel (``src/core/undo.py``) gehoert dem Patch und den
Geraeten — Strg+Z im Hauptfenster. Programmer-Werte landeten dort nie
(``set_programmer_value(undoable=False)`` ist Standard), deshalb nahm der
„Rückgängig"-Knopf im Programmer still die letzte PATCH-Aenderung zurueck.

Dieser Verlauf ist davon getrennt und kennt nur Programmer-Inhalt. Er wird an
genau den vier AppState-Methoden gefuettert, in denen JEDE Programmer-Aenderung
landet (``set_programmer_value``, ``_clear_programmer_attr``,
``clear_programmer``, ``_restore_shared_dimmer``) — egal ob Regler, Kachel,
Palette, Kommandozeile, VC, MIDI oder Web.

Ein Schritt ist ein Unterschied ``(fid, key) -> [alt, neu]`` (``None`` = nicht
gesetzt). Zurueckgenommen wird nur dieser Unterschied, NICHT ein ganzer
Schnappschuss: MIDI-/VC-/Web-Threads schreiben parallel, ein ganzer
Schnappschuss wuerde deren gleichzeitige Werte (z. B. einen gehaltenen
VC-Flash) mit ueberschreiben.

Gebuendelt wird zweifach:
* ausdruecklich ueber ``schritt(label)`` an den natuerlichen Grenzen
  (ein Knopfdruck, ein Regler-Zug, eine Kommandozeile …) — verschachtelbar,
  nur der aeusserste schliesst;
* als Sicherheitsnetz ueber ein Ruhe-Zeitfenster: ohne ausdruecklichen Schritt
  beendet ``RUHE_S`` Sekunden Ruhe den laufenden Schritt (MIDI-Fader,
  VC-Regler, Live-Werkzeuge, Mausrad am Regler).

Ohne Qt, thread-sicher (eigenes RLock).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager, nullcontext

STANDARD_LABEL = "Programmer-Änderung"


class _Schritt:
    __slots__ = ("label", "diff", "explizit")

    def __init__(self, label: str, explizit: bool):
        self.label = label or STANDARD_LABEL
        # (fid, key) -> [alt, neu]; Reihenfolge = erste Beruehrung
        self.diff: dict[tuple[int, str], list] = {}
        self.explizit = explizit

    def netto(self) -> dict[tuple[int, str], list]:
        """Nur die Schluessel, die sich ueber den ganzen Schritt geaendert haben."""
        return {k: v for k, v in self.diff.items() if v[0] != v[1]}


class ProgrammerVerlauf:
    MAX = 100
    RUHE_S = 0.4

    def __init__(self, on_change=None, max_tiefe: int | None = None):
        self._lock = threading.RLock()
        self._max = int(max_tiefe or self.MAX)
        self._undo: deque[_Schritt] = deque(maxlen=self._max)
        self._redo: list[_Schritt] = []
        self._offen: _Schritt | None = None
        self._tiefe = 0           # Verschachtelung ausdruecklicher Schritte
        self._letzte = 0.0        # time.monotonic() der letzten Aufnahme
        self._lokal = threading.local()   # Unterdruecken je Thread
        self._on_change = on_change
        self._status = self._status_jetzt()

    # ── Aufnahme ─────────────────────────────────────────────────────────────

    def unterdrueckt(self) -> bool:
        return getattr(self._lokal, "aus", 0) > 0

    @contextmanager
    def ohne_verlauf(self):
        """Aenderungen in diesem Block (nur in DIESEM Thread) nicht aufzeichnen:
        Seeding beim Reiter-Aufbau, Auto-Timer, Flash-Halten, das
        Wiederherstellen selbst."""
        self._lokal.aus = getattr(self._lokal, "aus", 0) + 1
        try:
            yield
        finally:
            self._lokal.aus -= 1

    def beginne(self, label: str = ""):
        """Oeffnet einen ausdruecklichen Schritt (Gegenstueck: ``beende``).
        Fuer Regler-Zuege, deren Anfang und Ende in zwei Ereignissen liegen
        (sliderPressed/sliderReleased)."""
        if self.unterdrueckt():
            return
        with self._lock:
            if self._tiefe == 0:
                self._abschliessen_locked()
                self._offen = _Schritt(label, explizit=True)
            self._tiefe += 1

    def beende(self):
        if self.unterdrueckt():
            return
        with self._lock:
            if self._tiefe <= 0:
                return
            self._tiefe -= 1
            if self._tiefe == 0:
                self._abschliessen_locked()
        self._melden()

    @contextmanager
    def schritt(self, label: str = ""):
        """Alles in diesem Block ist EIN Schritt (z. B. Hervorheben ueber
        zehn Geraete). Verschachtelbar — nur der aeusserste schliesst."""
        self.beginne(label)
        try:
            yield
        finally:
            self.beende()

    def notiere(self, aenderungen, label: str = ""):
        """Hook aus AppState: ``aenderungen`` = Iterable aus
        ``(fid, key, alt, neu)``. Je (fid, key) bleibt im Schritt der ERSTE
        Altwert, der Neuwert wird ueberschrieben."""
        if self.unterdrueckt():
            return
        aenderungen = [a for a in aenderungen if a[2] != a[3]]
        if not aenderungen:
            return
        with self._lock:
            jetzt = time.monotonic()
            if self._offen is not None and self._tiefe == 0 \
                    and jetzt - self._letzte > self.RUHE_S:
                self._abschliessen_locked()
            if self._offen is None:
                self._offen = _Schritt(label, explizit=False)
            diff = self._offen.diff
            for fid, key, alt, neu in aenderungen:
                eintrag = diff.get((fid, key))
                if eintrag is None:
                    diff[(fid, key)] = [alt, neu]
                else:
                    eintrag[1] = neu
            self._letzte = jetzt
            # Eine neue Aufnahme macht das Wiederholen gegenstandslos.
            self._redo.clear()
        self._melden()

    def _abschliessen_locked(self):
        s = self._offen
        self._offen = None
        if s is None:
            return
        netto = s.netto()
        if not netto:
            return      # z. B. Color-Picker-Leerlauf, zweimal Hervorheben
        s.diff = netto
        self._undo.append(s)

    def abschliessen(self):
        """Schliesst einen laufenden Schritt sofort (auch einen haengenden
        ausdruecklichen — falls ein sliderReleased nie kam)."""
        with self._lock:
            self._tiefe = 0
            self._abschliessen_locked()
        self._melden()

    # ── Zuruecknehmen ────────────────────────────────────────────────────────

    def rueckgaengig(self):
        """Nimmt den letzten Schritt vom Verlauf und liefert ``(label, werte)``
        mit ``werte = {(fid, key): altwert|None}`` — oder ``None``. Das
        Zurueckschreiben macht der Aufrufer (AppState) unter ``ohne_verlauf``."""
        with self._lock:
            self._tiefe = 0
            self._abschliessen_locked()
            if not self._undo:
                return None
            s = self._undo.pop()
            self._redo.append(s)
            werte = {k: v[0] for k, v in s.diff.items()}
            label = s.label
        self._melden()
        return label, werte

    def wiederholen(self):
        with self._lock:
            self._tiefe = 0
            self._abschliessen_locked()
            if not self._redo:
                return None
            s = self._redo.pop()
            self._undo.append(s)
            werte = {k: v[1] for k, v in s.diff.items()}
            label = s.label
        self._melden()
        return label, werte

    def leeren(self):
        with self._lock:
            self._undo.clear()
            self._redo.clear()
            self._offen = None
            self._tiefe = 0
            # Meldung ERZWINGEN: load_show leert unter ``_suppress_emits`` —
            # AppState._emit verwirft die Meldung dann, der Status-Cache stuende
            # aber schon auf „leer", und das zweite Leeren nach dem Laden
            # meldete nichts mehr („Rückgängig" bliebe mit altem Tooltip aktiv).
            self._status = None
        self._melden()

    # ── Abfrage ──────────────────────────────────────────────────────────────

    def kann_rueckgaengig(self) -> bool:
        with self._lock:
            return bool(self._undo) or bool(self._offen and self._offen.netto())

    def kann_wiederholen(self) -> bool:
        with self._lock:
            return bool(self._redo)

    def label_rueckgaengig(self) -> str | None:
        with self._lock:
            if self._offen is not None and self._offen.netto():
                return self._offen.label
            return self._undo[-1].label if self._undo else None

    def label_wiederholen(self) -> str | None:
        with self._lock:
            return self._redo[-1].label if self._redo else None

    def anzahl(self) -> int:
        """Anzahl abgeschlossener Schritte (ohne den laufenden)."""
        with self._lock:
            return len(self._undo)

    # ── Meldung an die Oberflaeche ───────────────────────────────────────────

    def _status_jetzt(self):
        return (self.kann_rueckgaengig(), self.kann_wiederholen(),
                self.label_rueckgaengig(), self.label_wiederholen())

    def _melden(self):
        """Ruft ``on_change`` nur, wenn sich fuer die Knoepfe etwas aendert
        (nicht bei jedem Tick eines Regler-Zugs). Ausserhalb des Locks."""
        neu = self._status_jetzt()
        with self._lock:
            if neu == self._status:
                return
            self._status = neu
        cb = self._on_change
        if cb is not None:
            try:
                cb()
            except Exception as e:
                print(f"[programmer_verlauf] on_change error: {e}")


# ── Defensive Zugriffe fuer Bedienflaechen ───────────────────────────────────
# Viele Tests reichen den Views/Werkzeugen einen gefaelschten State ohne
# Verlauf. Die Bedienflaechen sprechen ihn deshalb nur ueber diese Helfer an;
# fehlt er, wirkt der Block wie bisher (nullcontext).

def schritt(state, label: str = ""):
    """``with schritt(state, "Hervorheben"):`` — alles darin ist EIN Schritt."""
    fn = getattr(state, "programmer_schritt", None)
    if callable(fn):
        try:
            return fn(label)
        except Exception:
            pass
    return nullcontext()


def ohne_verlauf(state):
    """``with ohne_verlauf(state):`` — Aenderungen darin nicht aufzeichnen."""
    fn = getattr(state, "programmer_ohne_verlauf", None)
    if callable(fn):
        try:
            return fn()
        except Exception:
            pass
    return nullcontext()


def verlauf_von(state):
    """Der ProgrammerVerlauf des States — oder None (gefaelschter State)."""
    fn = getattr(state, "_get_programmer_verlauf", None)
    if callable(fn):
        try:
            v = fn()
        except Exception:
            return None
        return v if isinstance(v, ProgrammerVerlauf) else None
    return None
