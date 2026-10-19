"""OUT-80 — die Seriennummer eines Enttec dauerhaft in ``universes.json``.

**Der Befund.** Die USB-Seriennummer eines Enttec kannte die Ausgabe nur zur
Laufzeit (OUT-66). Nach einem Neustart war sie weg; vertauscht Linux beim
Booten ``ttyUSB0``/``ttyUSB1``, oeffnete jedes Universum den Dongle des anderen,
lernte ihn als eigenen und schrieb ab da dauerhaft dorthin. „Übernehmen“ im
Ausgabe-Dialog legte jede Ausgabe ebenfalls ohne Nummer neu an.

**Die Loesung.** Jede Enttec-Zeile traegt die gelernte Nummer im Feld
:data:`FELD`. Beim Anlegen (Start, „Übernehmen“, „Verbinden“) wird sie
mitgegeben; das erste Oeffnen sucht dann denselben Dongle wie der Reconnect.

Drei Zustaende des Feldes:

* fehlt — alte Zeile oder noch nie gelernt: Verhalten wie vor OUT-80;
* ``""`` — der Bediener hat „Dongle neu zuordnen“ gewaehlt: KEINE Nummer
  mitgeben, auch nicht die des laufenden Geraets; die naechste gelernte wird
  wieder eingetragen;
* Text — die Seriennummer.

Geschrieben wird nur bei Aenderung (nicht je Frame), im Hintergrund und
atomar (Hilfsdatei + ``os.replace``), damit ein Absturz mitten im Schreiben
die Konfiguration nie halb zuruecklaesst. Das Modul kennt kein Qt.
"""
from __future__ import annotations

import json
import os
import threading

#: Name des Feldes in einer ``universes.json``-Zeile.
FELD = "enttec_seriennr"

#: Serialisiert alle Schreiber von ``universes.json`` in diesem Prozess
#: (Dialog und Hintergrund-Speicher) — sonst koennte einer die Aenderung des
#: anderen mit einem alten Stand ueberschreiben.
DATEI_LOCK = threading.RLock()


def aus_zeile(zeile) -> str | None:
    """Die gespeicherte Nummer einer Zeile: ``None`` = Feld fehlt, ``""`` =
    bewusst vergessen, sonst die Nummer (getrimmt)."""
    if not isinstance(zeile, dict) or FELD not in zeile:
        return None
    wert = zeile.get(FELD)
    return "" if wert is None else str(wert).strip()


def _nummer(zeile) -> int | None:
    try:
        return int(zeile.get("num"))
    except (TypeError, ValueError, AttributeError):
        return None


def atomar_schreiben(pfad: str, rows) -> bool:
    """``rows`` als JSON nach ``pfad`` — erst in eine Hilfsdatei daneben, dann
    per ``os.replace`` an ihren Platz (auf Windows und POSIX atomar).
    ``True`` = geschrieben."""
    tmp = f"{pfad}.tmp{os.getpid()}"
    with DATEI_LOCK:
        try:
            ordner = os.path.dirname(pfad)
            if ordner:
                os.makedirs(ordner, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, pfad)
            return True
        except Exception as e:
            print(f"[enttec_konfig] ERROR: {pfad} nicht geschrieben: {e}")
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return False


def lies(pfad: str) -> list:
    """Alle Zeilen (leer bei fehlender/kaputter Datei)."""
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        return []
    return daten if isinstance(daten, list) else []


def seriennr_eintragen(pfad: str, universum: int, seriennr: str) -> bool:
    """Die gelernte Nummer in die Enttec-Zeile von ``universum`` schreiben.

    ``True`` nur, wenn die Datei geaendert wurde. Keine Enttec-Zeile fuer das
    Universum (geloescht, Typ gewechselt) oder schon dieselbe Nummer: nichts.

    Gegenpruefung: ein Dongle hat genau einen Ausgang — dieselbe Nummer
    verschwindet aus jeder ANDEREN Zeile (Feld entfernt). Sonst stand sie nach
    einem Verdraengen in zwei Zeilen, und nach dem Neustart sperrte sich eines
    der beiden Universen dauerhaft selbst.
    """
    sn = str(seriennr or "").strip()
    if not sn or not pfad:
        return False
    with DATEI_LOCK:
        if not os.path.exists(pfad):
            return False
        rows = lies(pfad)
        eigene = [z for z in rows if isinstance(z, dict)
                  and _nummer(z) == int(universum)
                  and str(z.get("output") or "").strip() == "Enttec"]
        if not eigene:
            return False
        geaendert = False
        for zeile in eigene:
            if aus_zeile(zeile) != sn:
                zeile[FELD] = sn
                geaendert = True
        for zeile in rows:
            if (isinstance(zeile, dict) and _nummer(zeile) != int(universum)
                    and aus_zeile(zeile) == sn):
                zeile.pop(FELD, None)
                geaendert = True
        if not geaendert:
            return False
        return atomar_schreiben(pfad, rows)


def doppelte(zuordnung) -> set:
    """Gegenpruefung: Nummern, die in ``{universum: nummer}`` mehr als einem
    Universum gehoeren. Sie sind mehrdeutig und werden keinem mitgegeben —
    jedes dieser Universen verhaelt sich wie eine alte Zeile ohne Nummer."""
    gesehen: dict[str, int] = {}
    for sn in dict(zuordnung or {}).values():
        sn = str(sn or "").strip()
        if sn:
            gesehen[sn] = gesehen.get(sn, 0) + 1
    return {sn for sn, n in gesehen.items() if n > 1}


class SeriennrSpeicher:
    """Schreibt gelernte Nummern im Hintergrund nach ``universes.json``.

    :meth:`vormerken` kommt aus dem Ausgabe-Thread und kehrt sofort zurueck;
    mehrere Meldungen kurz hintereinander werden zu einem Schreibvorgang
    zusammengefasst (je Universum gilt die letzte)."""

    def __init__(self, pfad_quelle):
        #: ``pfad_quelle()`` liefert den Pfad, den ``apply_output_config``
        #: zuletzt gelesen hat — Lese- und Schreibseite sehen dieselbe Datei.
        self._pfad_quelle = pfad_quelle
        self._lock = threading.Lock()
        self._offen: dict[int, str] = {}
        self._thread: threading.Thread | None = None

    def vormerken(self, universum: int, seriennr: str) -> None:
        with self._lock:
            self._offen[int(universum)] = str(seriennr)
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._lauf, name="EnttecSeriennrSpeicher", daemon=True)
            self._thread.start()

    def _lauf(self) -> None:
        while True:
            with self._lock:
                if not self._offen:
                    self._thread = None
                    return
                arbeit, self._offen = self._offen, {}
            try:
                pfad = self._pfad_quelle()
            except Exception:
                pfad = None
            for u, sn in sorted(arbeit.items()):
                try:
                    if seriennr_eintragen(pfad, u, sn):
                        print(f"[enttec_konfig] Universe {u}: Enttec-Seriennummer "
                              f"gespeichert (OUT-80).")
                except Exception as e:
                    print(f"[enttec_konfig] ERROR: Universe {u}: {e}")

    def warten(self, frist_s: float = 2.0) -> bool:
        """Tests/Beenden: bis alles geschrieben ist (``True``) oder die Frist um."""
        t = self._thread
        if t is not None:
            t.join(frist_s)
        with self._lock:
            return not self._offen and (self._thread is None
                                        or not self._thread.is_alive())
