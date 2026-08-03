"""OUT-06: **die eine E1.31-Quelle dieses Prozesses** — CID, Sequenz, Besitz.

E1.31 kennt keine „Sender-Objekte". Es kennt **Quellen**, und eine Quelle ist ein
Tripel aus CID (wer), Universum (wohin) und einer fortlaufenden Sequenznummer
(in welcher Reihenfolge). Ein Empfaenger fuehrt seinen Zaehler je **(CID, Universum)**
— nicht je Socket, von dem er nichts weiss.

LightOS hatte diese drei Teile bisher **im Sender-Objekt** liegen, und weil
``OutputManager`` je Universum einen eigenen ``SACNSender`` haelt und ihn bei jedem
„Speichern"/„Uebernehmen" **ersetzt**, wanderte die Identitaet mit dem Objekt:

* **Pro Universum eine eigene Quelle.** Vier sACN-Universen erschienen dem
  Empfaenger als vier verschiedene Konsolen.
* **Bei jedem Neustart — und jedem Speichern — eine neue Quelle.** Wer Quellen
  ueber die CID verfolgt (Merge-Listen, Discovery-Anzeigen, Node-Konfigurationen),
  konnte „dieselbe Konsole wie eben" nie wiedererkennen.

Deshalb haelt dieses Modul die drei Teile zusammen. **Die CID allein hochzuziehen
waere schlimmer als der Ausgangszustand gewesen** — gemessen, nicht vermutet:

* **Sequenz.** Bliebe der Zaehler im Sender, faenge er beim Tausch wieder bei 0 an,
  waehrend CID und Universum gleich bleiben. Ein spec-konformer Empfaenger verwirft
  dann jedes Paket, dessen Abstand zum letzten in ``(-20, 0]`` liegt (§6.7.2) — im
  Versuch **15 von 45** Paketen, also bis zu 455 ms stehendes Licht, und das bei
  einem Klick auf „Speichern". Mit wechselnder CID gab es das nicht: der Empfaenger
  sah zwei verschiedene Quellen.
* **Besitz.** Der Alt-Sender terminiert beim ``close()`` seine Universen (§6.2.6).
  ``_swap_device`` traegt den neuen Sender aber **vor** dem ``close()`` des alten ein
  und gibt das Lock frei — der 44-Hz-Thread kann dazwischen bereits ueber den neuen
  Sender senden. Unter geteilter CID toetet die Termination des Alten dann den
  gerade etablierten Stream des Neuen. Deshalb terminiert nur, wer bei der Freigabe
  noch als Besitzer eingetragen ist.

Der Nachfolger erbt also den Zaehler des Vorgaengers, und der Tausch wird fuer den
Empfaenger unsichtbar — genau das, was E1.31 von „derselben Quelle" erwartet.

## Die CID auf der Platte

Abgelegt als UUID-Text in ``<app_data_dir>/sacn_cid`` (Pfad: ``paths.sacn_cid_path()``).

**Warum eine eigene Datei und nicht ``ui_prefs.json``?** Dort liegt mit
``remote.token`` (``src/web/remote_settings.py``) bereits eine maschinengebundene
Identitaet, die Praezedenz waere also da. Dagegen steht der Blast-Radius: auf
``ui_prefs.json`` schreiben sechs unabhaengige Stellen im Read-Modify-Write-Verfahren.
Ist die Datei kaputt, liefert deren Lade-Helfer ``{}`` und der naechste Speichervorgang
schreibt **nur den eigenen Key** zurueck — nachgemessen gehen dabei alle fremden Keys
verloren, einschliesslich des Web-Remote-Tokens. Eine Identitaet, die als Nebenwirkung
einer fremden Einstellung verschwindet, ist keine. Die Ein-Zeilen-Datei kann nur an
sich selbst scheitern, ist im Supportfall vorlesbar und braucht keinen JSON-Parser.

**Fehlerfaelle kosten nie den Ausgang.** Unlesbare, kaputte oder nicht schreibbare
Datei → frische Zufalls-CID im Speicher: sACN sendet weiter, nur die Wiedererkennung
ueber Neustarts fehlt. Wichtig ist, dass sie dann **fuer die ganze Sitzung** gilt —
wuerde bei jedem Zugriff neu gewuerfelt, haette jedes Universum wieder eine eigene
CID und die Aenderung waere unbemerkt wirkungslos.

**Test-Isolation:** ``LIGHTOS_SACN_CID`` biegt die Datei um; ``tests/conftest.py``
setzt das auf einen tmp-Pfad. Ohne das legte die Testsuite eine CID im echten
Datenordner des Nutzers an bzw. ueberschriebe seine — dieselbe Klasse wie
``LIGHTOS_CRASH_LOG``.
"""
from __future__ import annotations

import os
import threading
import uuid

from src.core.paths import sacn_cid_path


# ── CID-Datei ────────────────────────────────────────────────────────────────

def cid_file_path() -> str:
    """Ablageort der CID-Datei — aufgeloest in ``src/core/paths.py``.

    Die Aufloesung liegt dort und nicht hier, weil jede Datei im App-Datenordner
    mit Test-Override an EINER Stelle stehen soll (neben ``crash_log_path()``);
    genau dort greift auch der Waechter-Test.
    """
    return sacn_cid_path()


def _read_cid(path: str) -> bytes | None:
    """Liest die CID; ``None`` bei fehlender, unlesbarer oder kaputter Datei."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return uuid.UUID(text).bytes
    except (ValueError, AttributeError, TypeError):
        # Kaputter Inhalt (haendisch editiert, halb geschriebene Datei): behandeln
        # wie "keine CID" -> es wird eine neue erzeugt und die Datei ueberschrieben.
        return None


def _write_cid(path: str, cid: bytes) -> bool:
    """Schreibt die CID atomar (tmp + ``os.replace``). ``False`` = nicht gespeichert.

    Atomar, damit ein Absturz oder ein zweiter Prozess mitten im Schreiben keine
    halbe Datei hinterlaesst — die waere beim naechsten Start unlesbar, und die
    Installation bekaeme still wieder wechselnde CIDs.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(str(uuid.UUID(bytes=cid)))
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def _load_or_create_cid() -> bytes:
    path = cid_file_path()
    cid = _read_cid(path)
    if cid is None:
        cid = uuid.uuid4().bytes
        _write_cid(path, cid)   # scheitert leise -> nur diese Sitzung stabil
    return cid


# ── Die Quelle ───────────────────────────────────────────────────────────────

class SacnSource:
    """CID + Sequenzzaehler je Universum + Besitz je Universum.

    Alle drei sind bewusst hier und nicht im ``SACNSender``: sie beschreiben, was
    der Empfaenger sieht, und der sieht keine Sender-Objekte.
    """

    def __init__(self, cid: bytes):
        self._cid = cid
        self._lock = threading.Lock()
        self._seq: dict[int, int] = {}        # Universum -> naechste Sequenznummer
        self._owner: dict[int, int] = {}      # Universum -> Token des Senders
        self._next_token = 0

    @property
    def cid(self) -> bytes:
        return self._cid

    def new_token(self) -> int:
        """Ausweis fuer einen Sender. Bewusst ein eigener Zaehler statt ``id()``:
        Objekt-Adressen werden nach der Freigabe wiederverwendet, und dann haette
        ein neuer Sender denselben Ausweis wie ein alter."""
        with self._lock:
            self._next_token += 1
            return self._next_token

    def _erster_seq(self) -> int:
        """Startwert eines noch unbenutzten Universums — **zufaellig, nicht 0.**

        Der Grund ist der Neustart nach einem Absturz (Codex-Befund zu PR #563):
        stirbt LightOS ohne ``close()``, bleibt die persistente CID, aber der
        Zaehler faengt wieder an. Ein Empfaenger, der die Quelle noch kennt —
        er vergisst sie erst nach 2,5 s (E1.31 §6.7.1) — verwirft dann jeden
        Frame, dessen Abstand zum letzten in ``(-20, 0]`` liegt.

        **Das Fenster ist erreichbar:** gemessen geht der erste sACN-Frame
        bereits **1,38 s** nach dem Prozessstart raus (``apply_output_config``
        laeuft im AppState-Aufbau, lange vor dem fertigen Fenster).

        Mit festem Start 0 trifft es **immer**, wenn die vorige Sitzung im
        Bereich 1..19 stand — also gerade beim Absturz kurz nach dem Start, dem
        haeufigsten Fall. Ein zufaelliger Startwert macht daraus die
        Grundwahrscheinlichkeit **20/256 ≈ 7,8 %**, kostet nichts und braucht
        weder Persistenz noch I/O im 44-Hz-Sendepfad.

        **Der Rest bleibt bewusst stehen.** Ihn zu beseitigen hiesse, den
        Sequenzstand laufend auf die Platte zu schreiben — Datei-I/O in genau
        dem Pfad, der 44-mal je Sekunde laeuft, gegen einen Fall, der einen
        Absturz UND einen Neustart binnen 2,5 s UND einen Treffer in einem
        20-von-256-Fenster verlangt. Wer das anders bewertet, findet die
        Rechnung dafuer in `tests/test_sacn_source.py`.
        """
        return uuid.uuid4().bytes[0]              # 0..255, gleichverteilt

    def next_seq(self, universe: int, token: int) -> int:
        """Naechste Sequenznummer fuer dieses Universum — und der Sender uebernimmt
        damit den Besitz. Beides zusammen, weil beides genau beim Senden gilt."""
        with self._lock:
            self._owner[universe] = token
            if universe not in self._seq:
                self._seq[universe] = self._erster_seq()
            seq = self._seq.get(universe, 0)
            self._seq[universe] = (seq + 1) & 0xFF
            return seq

    def release(self, universe: int, token: int) -> int | None:
        """Gibt das Universum frei. Rueckgabe = Sequenznummer fuer die
        Stream-Termination, oder ``None``, wenn inzwischen ein anderer Sender
        dieses Universum bedient — dann darf **nicht** terminiert werden, sonst
        reisst der Abschied des Alten den Stream des Neuen mit.

        Die Termination **verbraucht** ihre Sequenznummer, und der Zaehler laeuft
        danach weiter. Beides zusammen ist noetig: kommt spaeter wieder ein Sender
        fuer dieses Universum (Adapter aus und wieder an), setzt er die Reihe fort
        statt bei 0 anzufangen — und er beginnt nicht auf der Nummer, mit der eben
        terminiert wurde, die ein Empfaenger sonst als Rueckwaerts-Sprung verwirft.
        Genau diesen Fehler hatte der erste Entwurf; gefunden hat ihn der Test, nicht
        das Auge.
        """
        with self._lock:
            if self._owner.get(universe) != token:
                return None
            del self._owner[universe]
            seq = self._seq.get(universe, 0)
            self._seq[universe] = (seq + 1) & 0xFF
            return seq


_lock = threading.Lock()
_source: SacnSource | None = None


def sacn_source() -> SacnSource:
    """Die Quelle dieses Prozesses. Erster Aufruf liest bzw. legt die CID an."""
    global _source
    with _lock:
        if _source is None:
            _source = SacnSource(_load_or_create_cid())
        return _source


def sacn_cid() -> bytes:
    """Kurzform fuer ``sacn_source().cid`` — 16 Byte."""
    return sacn_source().cid


def reset_for_tests() -> None:
    """Verwirft die Prozess-Quelle — simuliert einen Neustart der Anwendung.

    Nur fuer Tests. Ohne das koennte kein Test pruefen, ob die CID wirklich aus der
    DATEI kommt: der zwischengespeicherte Wert wuerde jede zweite Messung
    beantworten, und ein Modul, das gar nichts speichert, saehe genauso aus.
    """
    global _source
    with _lock:
        _source = None
