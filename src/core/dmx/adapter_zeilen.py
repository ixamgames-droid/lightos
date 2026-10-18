"""OUT-74 — ein Adapter, ein Universum: doppelte Adapter-Zeilen in ``universes.json``.

**Der Fehler.** „Verbinden" im Reiter „Enttec Pro USB" schrieb die Zeile des
gewaehlten Universums und liess jede andere Zeile stehen. Wer den Adapter von
Universum 2 auf Universum 1 umzog, hatte danach ZWEI Zeilen mit demselben
Anschluss. Im laufenden Programm stimmte es (``add_enttec`` schliesst den
Anschluss auf dem anderen Universum) — nach dem Neustart richtete
``apply_output_config`` beide Zeilen nacheinander ein, und der Adapter lag auf
dem Universum, das zufaellig weiter hinten in der Datei steht. Er sendete also
moeglicherweise das FALSCHE Universum, ohne jede Meldung.

**Die Regel.** Hinter den Ausgabetypen in :data:`ADAPTER_TYPEN` steht je Zeile
EIN Geraet am Rechner (anders als bei Art-Net/sACN, wo viele Universen an
dieselbe Adresse gehen duerfen). Zwei Zeilen mit demselben Adapter sind deshalb
nie Absicht:

* **Beim „Verbinden"** raeumt :func:`andere_abraeumen` die anderen Zeilen ab —
  der Bediener hat gerade gesagt, wohin der Adapter gehoert.
* **Beim Laden** (:func:`doppelte`) weiss das niemand. Welche der Zeilen gemeint
  war, steht nicht in der Datei, und die erste oder die letzte zu nehmen hiesse
  raten — im schlechtesten Fall bekommt ein Rig die Werte eines anderen
  Universums. Der Adapter wird dann fuer KEINE der Zeilen eingerichtet, und es
  wird gemeldet.

Das Modul kennt weder Qt noch den OutputManager; es rechnet auf den Zeilen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Ausgabetypen, bei denen ``patch`` EIN Geraet am Rechner benennt — genau die
#: Texte aus ``universes.json``. ``uDMX`` (OUT-68) steht schon hier, damit die
#: Regel greift, sobald es diese Zeilen gibt.
ADAPTER_TYPEN = ("Enttec", "uDMX")

_COM = re.compile(r"^com\d+$", re.IGNORECASE)


def _text(wert) -> str:
    """``patch``/``output`` als getrimmter Text — die Datei ist von Hand editierbar."""
    return "" if wert is None else str(wert).strip()


def schluessel(typ, patch) -> tuple[str, str] | None:
    """Woran man denselben Adapter erkennt — oder ``None``, wenn es keiner ist.

    Windows unterscheidet bei ``COM3``/``com3`` nicht; Geraetepfade unter Linux
    und macOS bleiben wie geschrieben. Ein Enttec ohne Anschluss wird nie
    eingerichtet und kollidiert deshalb mit nichts. Bei uDMX heisst ein leerer
    ``patch`` „der einzige Adapter" — zwei solche Zeilen meinen dasselbe Geraet.
    """
    typ = _text(typ)
    if typ not in ADAPTER_TYPEN:
        return None
    patch = _text(patch)
    if typ == "Enttec":
        if not patch:
            return None
        if _COM.match(patch):
            patch = patch.upper()
    return typ, patch


def _nummer(zeile) -> int | None:
    try:
        return int(zeile.get("num"))
    except (TypeError, ValueError, AttributeError):
        return None


@dataclass(frozen=True)
class Doppelt:
    """Ein Adapter, der in mehr als einer Zeile steht."""

    typ: str
    patch: str
    universen: tuple[int, ...]

    @property
    def name(self) -> str:
        return f"{self.typ} {self.patch}" if self.patch else self.typ

    @property
    def text(self) -> str:
        """Der Satz fuer Statusleiste, Dialog und Log."""
        liste = aufzaehlung(self.universen)
        return (f"{self.name} steht auf Universe {liste} — ein Adapter sendet "
                f"nur ein Universum. Er ist für keines davon eingerichtet. "
                f"Ausgabe → Konfigurieren…: beim Adapter das richtige Universe "
                f"wählen und „Verbinden“.")


def aufzaehlung(nummern) -> str:
    teile = [str(n) for n in nummern]
    if len(teile) <= 1:
        return "".join(teile)
    return ", ".join(teile[:-1]) + " und " + teile[-1]


def doppelte(rows) -> list[Doppelt]:
    """Adapter, die in mehr als einer Zeile stehen (nach Universum sortiert).

    Dieselbe Universumsnummer zweimal zaehlt nicht doppelt: dort gewinnt wie
    bisher die spaetere Zeile, und der Adapter liegt auf genau diesem Universum.
    """
    gesehen: dict[tuple[str, str], set[int]] = {}
    for zeile in rows or []:
        if not isinstance(zeile, dict):
            continue
        key = schluessel(zeile.get("output"), zeile.get("patch"))
        num = _nummer(zeile)
        if key is None or num is None:
            continue
        gesehen.setdefault(key, set()).add(num)
    return [Doppelt(typ, patch, tuple(sorted(nummern)))
            for (typ, patch), nummern in gesehen.items() if len(nummern) > 1]


def gesperrte_universen(rows) -> dict[int, Doppelt]:
    """Universum → der doppelte Adapter, der dort NICHT eingerichtet wird."""
    gesperrt: dict[int, Doppelt] = {}
    for d in doppelte(rows):
        for num in d.universen:
            gesperrt.setdefault(num, d)
    return gesperrt


def stoerungen(doppelt) -> list[dict]:
    """Doppelte Adapter als Eintraege fuer das Ausfall-Banner (OUT-67).

    Dieselbe Form wie ``OutputManager.ausgabe_status()``: ``verbunden is False``
    heisst dort „eingerichtet, sendet aber nicht" — genau das ist ein Adapter,
    der in der Datei steht und fuer keine seiner Zeilen eingerichtet wurde. Je
    Adapter EIN Eintrag (nicht je Universum), sonst zaehlte das Banner ihn
    doppelt.
    """
    return [{"universum": d.universen[0], "weg": d.typ, "ziel": d.patch,
             "verbunden": False,
             "problem": (f"steht auf Universe {aufzaehlung(d.universen)}, "
                         f"für keines eingerichtet")}
            for d in doppelt or [] if d.universen]


def andere_abraeumen(rows, typ, patch, bleibt: int) -> list[int]:
    """Nimmt denselben Adapter aus allen ANDEREN Zeilen (in ``rows`` selbst).

    Die Zeile bleibt stehen — Nummer und Name gehoeren dem Universum, nicht dem
    Adapter —, bekommt aber ``Disabled`` und einen leeren ``patch``. Zurueck
    kommen die Universumsnummern, die den Adapter eben verloren haben.
    """
    key = schluessel(typ, patch)
    if key is None:
        return []
    geraeumt: list[int] = []
    for zeile in rows or []:
        if not isinstance(zeile, dict):
            continue
        num = _nummer(zeile)
        if num is None or num == int(bleibt):
            continue
        if schluessel(zeile.get("output"), zeile.get("patch")) != key:
            continue
        zeile["output"] = "Disabled"
        zeile["patch"] = ""
        if num not in geraeumt:
            geraeumt.append(num)
    return sorted(geraeumt)


def umzug_text(geraeumt, jetzt: int) -> str:
    """„war Universe 2 — jetzt Universe 1" (leer, wenn nichts umgezogen ist)."""
    if not geraeumt:
        return ""
    return f"war Universe {aufzaehlung(geraeumt)} — jetzt Universe {int(jetzt)}"
