"""VIZ-56: fremde Archive und XML-Dokumente sicher lesen.

Eine ``.mvr`` und jede eingebettete ``.gdtf`` sind ZIP-Archive aus fremder
Hand. Hier gilt:

* **Nichts wird entpackt.** Gelesen wird Eintrag fuer Eintrag in den Speicher,
  mit einer harten Grenze je Eintrag und fuer alles zusammen. Ein Archiv mit
  einem gefaehrlichen Namen (absoluter Pfad, ``..``, Laufwerksbuchstabe,
  Steuerzeichen) wird als Ganzes abgelehnt — es kommt nicht von einem
  ehrlichen Programm.
* **Zip-Bomben:** Eintragszahl, angegebene und WIRKLICH gelesene Groesse und
  das Kompressionsverhaeltnis sind begrenzt. Die Angabe im Verzeichnis kann
  luegen; :func:`lies_eintrag` liest deshalb nie mehr als die Grenze + 1 Byte.
* **XML ohne DTD:** ein Dokument mit ``<!DOCTYPE`` oder ``<!ENTITY`` wird
  abgelehnt, BEVOR es geparst wird (Entity-Expansion, externe Entities). Ein
  Dokument mit NUL-Bytes (UTF-16/32) ebenso — darin waere die Suche blind.

Jeder Fehler ist ein :class:`MvrFehler` mit einem deutschen Satz; nichts
anderes verlaesst dieses Modul.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

#: Hoechstens so viele Eintraege in einem Archiv.
EINTRAEGE_MAX = 5000
#: Hoechstens so gross darf EIN gelesener Eintrag entpackt sein.
EINTRAG_MAX = 64 * 1024 * 1024
#: Hoechstens so viel wird aus einem Archiv insgesamt gelesen.
GESAMT_MAX = 256 * 1024 * 1024
#: Entpackt / gepackt — darueber gilt ein Eintrag als Zip-Bombe. Echte XML
#: packt etwa 10–30 zu 1.
VERHAELTNIS_MAX = 200
#: Unter dieser entpackten Groesse zaehlt das Verhaeltnis nicht (winzige
#: Dateien aus lauter Leerzeichen sind keine Bombe).
VERHAELTNIS_AB = 1024 * 1024
#: Groesse der Datei selbst.
DATEI_MAX = 512 * 1024 * 1024


class MvrFehler(Exception):
    """Eine Datei laesst sich nicht lesen — ``str(e)`` ist ein deutscher Satz."""


_STEUERZEICHEN = re.compile(r"[\x00-\x1f]")


def name_ist_sicher(name: str) -> bool:
    """Darf ein Archiveintrag so heissen? Kein absoluter Pfad, kein ``..``,
    kein Laufwerk, kein Steuerzeichen."""
    if not name or _STEUERZEICHEN.search(name):
        return False
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return False
    return all(teil != ".." for teil in n.split("/"))


class Archiv:
    """Ein geoeffnetes ZIP — nur zum Lesen einzelner Eintraege in den Speicher.

    ``was`` nennt das Archiv in Meldungen („Die MVR-Datei“, „Die GDTF-Datei
    „x.gdtf““)."""

    def __init__(self, quelle, was: str, budget: list[int] | None = None):
        self.was = was
        #: Dativ fuer „… in der MVR-Datei“.
        self.wo = ("in der " + was[4:]) if was.startswith("Die ") else f"in {was}"
        #: Gemeinsames Restbudget (in Bytes) — eine MVR und alle ihre GDTF
        #: teilen sich :data:`GESAMT_MAX`.
        self._budget = budget if budget is not None else [GESAMT_MAX]
        try:
            self._zip = zipfile.ZipFile(quelle)
            infos = self._zip.infolist()
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError,
                EOFError, NotImplementedError) as e:
            raise MvrFehler(f"{was} ist kein gültiges ZIP-Archiv ({_kurz(e)}).") from None
        if len(infos) > EINTRAEGE_MAX:
            raise MvrFehler(f"{was} hat {len(infos)} Einträge — mehr als "
                            f"{EINTRAEGE_MAX} werden nicht gelesen.")
        for info in infos:
            if not name_ist_sicher(info.filename):
                raise MvrFehler(
                    f"{was} enthält einen unzulässigen Dateinamen "
                    f"(„{_sichtbar(info.filename)}“) — absolute Pfade und "
                    "„..“ sind nicht erlaubt. Die Datei wird nicht gelesen.")
        self._infos = {i.filename.replace("\\", "/"): i for i in infos
                       if not i.is_dir()}
        self._klein = {}
        for name in self._infos:
            self._klein.setdefault(name.casefold(), name)

    @property
    def namen(self) -> list[str]:
        return list(self._infos)

    def finde(self, name: str) -> str | None:
        """Eintragsname zu ``name`` — exakt, sonst ohne Gross/Klein."""
        n = (name or "").replace("\\", "/")
        if n in self._infos:
            return n
        return self._klein.get(n.casefold())

    def lies_eintrag(self, name: str) -> bytes:
        info = self._infos.get(name)
        if info is None:
            raise MvrFehler(f"{self.was} enthält „{_sichtbar(name)}“ nicht.")
        if info.file_size > EINTRAG_MAX:
            raise MvrFehler(
                f"Der Eintrag „{_sichtbar(name)}“ {self.wo} ist entpackt "
                f"{_mb(info.file_size)} groß — mehr als "
                f"{_mb(EINTRAG_MAX)} werden nicht gelesen.")
        grenze = min(EINTRAG_MAX, self._budget[0])
        try:
            with self._zip.open(info) as f:
                daten = f.read(grenze + 1)
        except (zipfile.BadZipFile, OSError, ValueError, EOFError,
                NotImplementedError, RuntimeError) as e:
            raise MvrFehler(f"Der Eintrag „{_sichtbar(name)}“ {self.wo} ist beschädigt "
                            f"({_kurz(e)}).") from None
        if len(daten) > grenze:
            if grenze < EINTRAG_MAX:
                raise MvrFehler(f"{self.was} ist entpackt zu groß — mehr als "
                                f"{_mb(GESAMT_MAX)} werden "
                                "insgesamt nicht gelesen.")
            raise MvrFehler(
                f"Der Eintrag „{_sichtbar(name)}“ {self.wo} ist entpackt größer als "
                f"{_mb(EINTRAG_MAX)} — wird nicht gelesen.")
        gepackt = max(1, int(info.compress_size or 0))
        if len(daten) >= VERHAELTNIS_AB and len(daten) / gepackt > VERHAELTNIS_MAX:
            raise MvrFehler(
                f"Der Eintrag „{_sichtbar(name)}“ {self.wo} ist ungewöhnlich stark "
                f"gepackt (mehr als {VERHAELTNIS_MAX}:1) — vermutlich eine "
                "Zip-Bombe. Die Datei wird nicht gelesen.")
        self._budget[0] -= len(daten)
        return daten

    def unterarchiv(self, name: str, was: str) -> "Archiv":
        """Ein eingebettetes ZIP (die ``.gdtf`` in der ``.mvr``) — aus dem
        Speicher, mit demselben Restbudget."""
        return Archiv(io.BytesIO(self.lies_eintrag(name)), was, self._budget)

    def schliessen(self) -> None:
        try:
            self._zip.close()
        except Exception:
            pass


_VERBOTEN = (b"<!doctype", b"<!entity")


def parse_xml(daten: bytes, was: str) -> ET.Element:
    """XML-Text -> Wurzelelement. Lehnt DTD/Entities VOR dem Parsen ab."""
    if b"\x00" in daten:
        raise MvrFehler(f"{was} ist kein UTF-8-Text (UTF-16/32 wird nicht "
                        "gelesen).")
    klein = daten.lower()
    for marke in _VERBOTEN:
        if marke in klein:
            raise MvrFehler(
                f"{was} enthält eine Dokumenttyp- oder Entity-Angabe "
                f"(„{marke.decode()[:9].upper()}…“). Solche Angaben braucht "
                "MVR nicht; aus Sicherheitsgründen wird die Datei nicht "
                "gelesen.")
    try:
        return ET.fromstring(daten)
    except ET.ParseError as e:
        raise MvrFehler(f"{was} ist kein gültiges XML ({_kurz(e)}).") from None
    except (ValueError, RecursionError) as e:
        raise MvrFehler(f"{was} ist kein gültiges XML ({_kurz(e)}).") from None


def _mb(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.0f} MB"
    return f"{max(1, round(n / 1024))} KB"


def _kurz(e: BaseException) -> str:
    text = str(e) or type(e).__name__
    return text if len(text) <= 120 else text[:117] + "…"


def _sichtbar(name: str) -> str:
    n = _STEUERZEICHEN.sub("?", name or "")
    return n if len(n) <= 80 else n[:77] + "…"
