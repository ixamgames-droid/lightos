"""NET-15: DMX-Fernsteuerung ueber den Art-Net-/sACN-Eingang.

Ein beliebiges Pult (oder ein anderes Programm), das Art-Net oder sACN sendet,
kann damit Executor-Fader, den Grand Master und die Tasten GO / Zurueck / Stop
eines Executors bedienen — der universelle Weg fuer jedes Pult, ganz ohne MIDI.

Zuordnung: ``(Quelle, eingehendes Universum, Kanal) -> Ziel``.

Verhalten (bewusst wie die MIDI-Zuordnung, ``midi_mapper``):

* **Fader-Ziele wirken nur bei Aenderung.** Ein DMX-Strom wiederholt jeden Wert
  ~44-mal pro Sekunde; MIDI sendet nur, wenn sich ein Regler bewegt. Wuerde
  jeder Wert angewandt, ueberschriebe ein ruhig stehendes Pult jede lokale
  Bedienung desselben Faders. Deshalb gilt: der erste Wert nach dem
  Einrichten (oder nach einer Empfangspause, ``PAUSE_S``) ist nur die
  **Ausgangslage**; angewandt wird erst, wenn sich der Kanal bewegt — dann
  springt der Fader auf den Pultwert (wie ein MIDI-Fader ohne Soft-Takeover,
  den es in LightOS auch fuer MIDI nicht gibt).
* **Tasten-Ziele (GO/Zurueck/Stop) loesen per Schwelle aus**: steigende Flanke
  ueber ``schwelle`` (Standard 50 %) loest **genau einmal** aus; erst wenn der
  Kanal unter ``schwelle - hysterese`` (Standard 10 %) faellt, ist die Taste
  wieder scharf. Steht der Kanal bei der Ausgangslage schon oben, loest das
  nichts aus.
* **Fernsteuer-Kanaele werden NICHT in die Ausgabe gemischt.** Laeuft auf
  demselben eingehenden Universum auch ein Input-Merge, nimmt der Merge diese
  Kanaele aus (:func:`reservierte_kanaele`).

Threads: :meth:`DmxFernsteuerung.empfange` laeuft im Empfangs-Thread
(``ArtNet-In``/``sACN-In``) und rechnet nur — es legt Aktionen in eine Queue.
Angewandt wird in :meth:`DmxFernsteuerung.abarbeiten`, im GUI-Thread: die
Qt-Bruecke (:func:`installiere_qt_wecker`) stoesst sie per Queued-Signal an.

Speicherort: eigene Datei ``dmx_fernsteuerung.json`` im App-Datenordner
(:func:`src.core.paths.dmx_fernsteuerung_path`, Override
``LIGHTOS_DMX_FERNSTEUERUNG``). ``universes.json`` bleibt unberuehrt — alte
Konfigurationen laden also unveraendert; fehlt die Datei, ist nichts
zugeordnet.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Callable

QUELLE_ARTNET = "artnet"
QUELLE_SACN = "sacn"
QUELLEN = (QUELLE_ARTNET, QUELLE_SACN)

ZIEL_FADER = "executor_fader"
ZIEL_GM = "grand_master"
ZIEL_GO = "executor_go"
ZIEL_BACK = "executor_back"
ZIEL_STOP = "executor_stop"
ZIELE = (ZIEL_FADER, ZIEL_GM, ZIEL_GO, ZIEL_BACK, ZIEL_STOP)
TASTEN_ZIELE = (ZIEL_GO, ZIEL_BACK, ZIEL_STOP)
#: Executor-Taste je Tasten-Ziel (``Executor.press_btn`` nimmt den Namen).
_TASTE = {ZIEL_GO: "go", ZIEL_BACK: "back", ZIEL_STOP: "stop"}

SCHWELLE_STANDARD = 50      # Prozent
HYSTERESE_STANDARD = 10     # Prozent
#: Nach so langer Empfangspause gilt der naechste Wert wieder nur als
#: Ausgangslage (wie der NET-05-Quellen-Timeout des Merges, ~2,5 s). Sonst
#: loeste ein Pult, das mit oben stehendem GO-Kanal zurueckkommt, sofort GO aus.
PAUSE_S = 2.5
FORMAT_VERSION = 1
EXECUTOR_MAX = 20           # PlaybackEngine.MAX_EXECUTORS


def _int(wert, vorgabe: int, lo: int, hi: int) -> int:
    try:
        n = int(wert)
    except (TypeError, ValueError):
        return vorgabe
    return max(lo, min(hi, n))


@dataclass
class Zuordnung:
    quelle: str = QUELLE_ARTNET
    universum: int = 1          # eingehendes Universum (Art-Net 1-basiert wie der Merge)
    kanal: int = 1              # 1..512
    ziel: str = ZIEL_FADER
    executor: int = 1           # 1..20, fuer Grand Master ohne Bedeutung
    schwelle: int = SCHWELLE_STANDARD    # % — nur Tasten-Ziele
    hysterese: int = HYSTERESE_STANDARD  # % — nur Tasten-Ziele

    @classmethod
    def aus_dict(cls, d) -> "Zuordnung | None":
        """Eine Zeile aus der Datei. Unbrauchbar (kein dict, unbekannte
        Quelle/Ziel) -> ``None``: eine kaputte Zeile kostet nur sich selbst."""
        if not isinstance(d, dict):
            return None
        quelle = str(d.get("quelle", "")).strip().lower()
        ziel = str(d.get("ziel", "")).strip()
        if quelle not in QUELLEN or ziel not in ZIELE:
            return None
        u_hi = 32768 if quelle == QUELLE_ARTNET else 63999
        return cls(
            quelle=quelle,
            universum=_int(d.get("universum"), 1, 1, u_hi),
            kanal=_int(d.get("kanal"), 1, 1, 512),
            ziel=ziel,
            executor=_int(d.get("executor"), 1, 1, EXECUTOR_MAX),
            schwelle=_int(d.get("schwelle"), SCHWELLE_STANDARD, 1, 100),
            hysterese=_int(d.get("hysterese"), HYSTERESE_STANDARD, 0, 99),
        )

    def als_dict(self) -> dict:
        return asdict(self)

    # Rohwert-Grenzen (0..255) fuer Tasten
    def ein_roh(self) -> int:
        """Ab diesem DMX-Wert gilt die Taste als gedrueckt (>=)."""
        return max(1, min(255, round(self.schwelle * 255 / 100)))

    def aus_roh(self) -> int:
        """Unter diesem DMX-Wert ist die Taste wieder scharf (<)."""
        return max(0, self.ein_roh() - round(self.hysterese * 255 / 100))


@dataclass
class Konfig:
    aktiv: bool = False
    zuordnungen: list[Zuordnung] = field(default_factory=list)

    @classmethod
    def aus_dict(cls, d) -> "Konfig":
        if not isinstance(d, dict):
            return cls()
        zs = []
        for z in d.get("zuordnungen") or []:
            zz = Zuordnung.aus_dict(z)
            if zz is not None:
                zs.append(zz)
        return cls(aktiv=bool(d.get("aktiv", False)), zuordnungen=zs)

    def als_dict(self) -> dict:
        return {"version": FORMAT_VERSION, "aktiv": bool(self.aktiv),
                "zuordnungen": [z.als_dict() for z in self.zuordnungen]}


def konfig_pfad() -> str:
    from src.core.paths import dmx_fernsteuerung_path
    return dmx_fernsteuerung_path()


def lade_konfig(pfad: str | None = None) -> Konfig:
    """Fehlende oder kaputte Datei -> leere, inaktive Konfiguration."""
    pfad = pfad or konfig_pfad()
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return Konfig.aus_dict(json.load(f))
    except (OSError, ValueError):
        return Konfig()


def speichere_konfig(konfig: Konfig, pfad: str | None = None) -> bool:
    """Atomar schreiben (Hilfsdatei + ``os.replace``). ``True`` = geschrieben."""
    pfad = pfad or konfig_pfad()
    try:
        ordner = os.path.dirname(pfad)
        if ordner:
            os.makedirs(ordner, exist_ok=True)
        tmp = pfad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(konfig.als_dict(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, pfad)
        return True
    except OSError as e:
        print(f"[fernsteuerung] speichern fehlgeschlagen: {e}")
        return False


@dataclass
class Aktion:
    """Eine im Empfangs-Thread erkannte, noch nicht angewandte Aktion."""
    ziel: str
    executor: int
    wert: float = 0.0       # Fader/GM: 0..1


class DmxFernsteuerung:
    def __init__(self, uhr: Callable[[], float] = time.monotonic):
        self._uhr = uhr
        self._lock = threading.Lock()
        self._konfig = Konfig()
        # {(quelle, universum): [(index, Zuordnung)]}
        self._index: dict[tuple[str, int], list[tuple[int, Zuordnung]]] = {}
        self._letzter: dict[int, int] = {}      # index -> letzter Rohwert
        self._oben: dict[int, bool] = {}        # index -> Taste steht oben
        self._zuletzt: dict[tuple[str, int], float] = {}
        self._queue: "queue.SimpleQueue[Aktion]" = queue.SimpleQueue()
        self._wecker: Callable[[], None] | None = None
        self._verbunden: dict[str, object] = {}
        self.angewandt = 0      # Zaehler (Status/Tests)

    # ── Konfiguration ─────────────────────────────────────────────────────

    @property
    def konfig(self) -> Konfig:
        return self._konfig

    def konfigurieren(self, konfig: Konfig) -> None:
        """Neue Zuordnung setzen. Alle Ausgangslagen verfallen: der naechste
        Wert je Kanal ist wieder nur Ausgangslage (kein Sprung, kein GO)."""
        idx: dict[tuple[str, int], list[tuple[int, Zuordnung]]] = {}
        if konfig.aktiv:
            for i, z in enumerate(konfig.zuordnungen):
                idx.setdefault((z.quelle, int(z.universum)), []).append((i, z))
        with self._lock:
            self._konfig = konfig
            self._index = idx
            self._letzter.clear()
            self._oben.clear()
            self._zuletzt.clear()
        # Liegengebliebene Aktionen der alten Zuordnung verwerfen.
        self._leeren()

    def reservierte_kanaele(self, quelle: str, universum: int) -> frozenset[int]:
        """Kanaele (1..512) eines eingehenden Universums, die der Fernsteuerung
        gehoeren und deshalb NICHT in die Ausgabe gemischt werden."""
        with self._lock:
            eintraege = self._index.get((quelle, int(universum)))
            if not eintraege:
                return frozenset()
            return frozenset(z.kanal for _i, z in eintraege)

    def universen(self, quelle: str) -> list[int]:
        with self._lock:
            return sorted({u for (q, u) in self._index if q == quelle})

    # ── Empfangs-Thread ───────────────────────────────────────────────────

    def empfange(self, quelle: str, universum: int, data) -> int:
        """Im Empfangs-Thread: Werte pruefen, Aktionen einreihen. Liefert die
        Zahl neu eingereihter Aktionen. Wendet NICHTS selbst an."""
        neu = 0
        jetzt = self._uhr()
        schluessel = (quelle, int(universum))
        with self._lock:
            eintraege = self._index.get(schluessel)
            if not eintraege:
                return 0
            vorher = self._zuletzt.get(schluessel)
            self._zuletzt[schluessel] = jetzt
            if vorher is not None and jetzt - vorher > PAUSE_S:
                # Pult war weg -> Ausgangslage neu aufnehmen.
                for i, _z in eintraege:
                    self._letzter.pop(i, None)
                    self._oben.pop(i, None)
            for i, z in eintraege:
                if z.kanal > len(data):
                    continue
                wert = int(data[z.kanal - 1]) & 0xFF
                alt = self._letzter.get(i)
                self._letzter[i] = wert
                if z.ziel in TASTEN_ZIELE:
                    oben = self._oben.get(i)
                    if oben is None:
                        # Ausgangslage: steht schon oben -> kein Ausloesen.
                        self._oben[i] = wert >= z.ein_roh()
                        continue
                    if not oben and wert >= z.ein_roh():
                        self._oben[i] = True
                        self._queue.put(Aktion(z.ziel, z.executor))
                        neu += 1
                    elif oben and wert < z.aus_roh():
                        self._oben[i] = False
                    continue
                # Fader / Grand Master: nur bei Aenderung.
                if alt is None or alt == wert:
                    continue
                self._queue.put(Aktion(z.ziel, z.executor, wert / 255.0))
                neu += 1
        if neu:
            w = self._wecker
            if w is not None:
                try:
                    w()
                except Exception as e:
                    print(f"[fernsteuerung] wecker: {e}")
        return neu

    # ── GUI-/Engine-Thread ────────────────────────────────────────────────

    def set_wecker(self, wecker: Callable[[], None] | None) -> None:
        """``wecker`` wird aus dem Empfangs-Thread gerufen, sobald Aktionen
        warten — er muss :meth:`abarbeiten` in den GUI-Thread uebergeben."""
        self._wecker = wecker

    def _leeren(self) -> list[Aktion]:
        aus = []
        while True:
            try:
                aus.append(self._queue.get_nowait())
            except queue.Empty:
                return aus

    def abarbeiten(self, state=None) -> int:
        """Wartende Aktionen anwenden (GUI-Thread). Mehrere Fader-Werte fuer
        dasselbe Ziel fallen auf den letzten zusammen; Tasten zaehlen einzeln.
        Liefert die Zahl angewandter Aktionen."""
        aktionen = self._leeren()
        if not aktionen:
            return 0
        if state is None:
            from src.core.app_state import get_state
            state = get_state()
        letzte_fader: dict[tuple[str, int], Aktion] = {}
        reihe: list = []
        for a in aktionen:
            if a.ziel in TASTEN_ZIELE:
                reihe.append(a)
            else:
                k = (a.ziel, a.executor if a.ziel == ZIEL_FADER else 0)
                if k not in letzte_fader:
                    reihe.append(k)
                letzte_fader[k] = a
        n = 0
        for eintrag in reihe:
            a = letzte_fader[eintrag] if isinstance(eintrag, tuple) else eintrag
            try:
                if self._anwenden(state, a):
                    n += 1
            except Exception as e:
                print(f"[fernsteuerung] {a.ziel}: {e}")
        self.angewandt += n
        return n

    @staticmethod
    def _anwenden(state, a: Aktion) -> bool:
        pe = getattr(state, "playback_engine", None)
        if a.ziel == ZIEL_GM:
            val = max(0.0, min(1.0, a.wert))
            state.output_manager.set_grand_master(val)
            # wie midi_mapper: Executoren mit Fader-Funktion "master" folgen
            if pe is not None:
                for ex in pe.executors:
                    if ex.fader_function == "master":
                        ex.fader_value = val
            return True
        if pe is None:
            return False
        ex = pe.get_executor(int(a.executor))
        if a.ziel == ZIEL_FADER:
            ex.fader_value = max(0.0, min(1.0, a.wert))
            return True
        taste = _TASTE.get(a.ziel)
        if taste:
            ex.press_btn(taste)
            return True
        return False

    # ── Empfaenger anbinden ───────────────────────────────────────────────

    def _cb_artnet(self, universum: int, data) -> None:
        self.empfange(QUELLE_ARTNET, universum, data)

    def _cb_sacn(self, universum: int, data) -> None:
        self.empfange(QUELLE_SACN, universum, data)

    def verbinden(self, artnet_rx=None, sacn_rx=None) -> None:
        """Als Empfangs-Callback anmelden (idempotent). Ohne Argument die
        App-Empfaenger (Singletons)."""
        if artnet_rx is None:
            from src.core.dmx.artnet_input import get_artnet_receiver
            artnet_rx = get_artnet_receiver()
        if sacn_rx is None:
            from src.core.dmx.sacn_input import get_sacn_receiver
            sacn_rx = get_sacn_receiver()
        artnet_rx.subscribe(self._cb_artnet)
        sacn_rx.subscribe(self._cb_sacn)
        self._verbunden = {QUELLE_ARTNET: artnet_rx, QUELLE_SACN: sacn_rx}

    def empfaenger_starten(self) -> list[str]:
        """Die fuer die aktive Zuordnung noetigen App-Empfaenger starten bzw.
        bei sACN die Multicast-Gruppen beitreten. Liefert die gestarteten
        Quellen (fuer die Statuszeile)."""
        self.verbinden()
        gestartet = []
        art = self.universen(QUELLE_ARTNET)
        if art:
            rx = self._verbunden[QUELLE_ARTNET]
            if not rx.is_running():
                rx.start()
            gestartet.append(QUELLE_ARTNET)
        sac = self.universen(QUELLE_SACN)
        if sac:
            rx = self._verbunden[QUELLE_SACN]
            if not rx.is_running():
                rx.start(universes=sac)
            else:
                for u in sac:
                    rx.join_universe(u)
            gestartet.append(QUELLE_SACN)
        return gestartet


_instanz: DmxFernsteuerung | None = None
_instanz_lock = threading.Lock()


def get_fernsteuerung() -> DmxFernsteuerung:
    global _instanz
    with _instanz_lock:
        if _instanz is None:
            _instanz = DmxFernsteuerung()
        return _instanz


def reservierte_kanaele(quelle: str, universum: int) -> frozenset[int]:
    """Fuer die Merge-Callbacks der Empfaenger. Ohne Instanz: nichts reserviert
    (kein Anlegen aus dem Empfangs-Thread heraus)."""
    inst = _instanz
    if inst is None:
        return frozenset()
    return inst.reservierte_kanaele(quelle, universum)


# ── Qt-Bruecke (GUI-Thread) ───────────────────────────────────────────────

_qt_wecker = None


def installiere_qt_wecker():
    """Im GUI-Thread aufrufen: legt (einmal je Prozess) ein elternloses QObject
    an, dessen Signal aus dem Empfangs-Thread gefeuert und per
    Queued-Connection im GUI-Thread ausgeliefert wird — dort laeuft dann
    :meth:`abarbeiten`. Mehrfaches Anstossen, solange schon eines unterwegs
    ist, wird zusammengefasst. Elternlos, damit es kein geschlossenes Fenster
    mit in den Tod reisst (Tests bauen viele Hauptfenster)."""
    global _qt_wecker
    fs = get_fernsteuerung()
    if _qt_wecker is not None:
        fs.set_wecker(_qt_wecker.wecken)
        return _qt_wecker
    from PySide6.QtCore import QObject, Qt, Signal

    class _Wecker(QObject):
        anstossen = Signal()

        def __init__(self, fs: DmxFernsteuerung):
            super().__init__(None)
            self._fs = fs
            self._unterwegs = threading.Event()
            self.anstossen.connect(self._los, Qt.ConnectionType.QueuedConnection)

        def wecken(self):
            if not self._unterwegs.is_set():
                self._unterwegs.set()
                self.anstossen.emit()

        def _los(self):
            self._unterwegs.clear()
            self._fs.abarbeiten()

    _qt_wecker = _Wecker(fs)
    fs.set_wecker(_qt_wecker.wecken)
    return _qt_wecker


def beim_start() -> list[str]:
    """App-Start (GUI-Thread): gespeicherte Zuordnung laden, Qt-Bruecke
    einrichten und — nur wenn die Fernsteuerung aktiv gespeichert ist — die
    noetigen Empfaenger starten. Ohne Datei passiert nichts (kein Port)."""
    konfig = lade_konfig()
    fs = get_fernsteuerung()
    fs.konfigurieren(konfig)
    installiere_qt_wecker()
    if konfig.aktiv and konfig.zuordnungen:
        return fs.empfaenger_starten()
    return []
