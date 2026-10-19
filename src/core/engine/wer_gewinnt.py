"""ENG-35 Schritt 4: „Wer gewinnt?“ — live, je Geraet.

Der Engine-Merge laesst laufende Funktionen nacheinander in dieselben
Universen schreiben; wer zuletzt schreibt, gewinnt (``FunctionManager.tick``).
Dieses Modul haelt das optionale Protokoll dazu:

* :class:`SchreibProtokoll` — je Frame „Adresse -> letzter Schreiber (fid)“
  und je Funktion „welche Adressen hat sie geschrieben“. Der FunctionManager
  fuellt es NUR, solange eine Anzeige es angefordert hat
  (``wer_gewinnt_anfordern`` / ``wer_gewinnt_freigeben``); sonst kostet es im
  Takt nichts.
* die Schicht darueber („oben“): Adressen, die Cuelisten, Programmer oder
  Snap-Tasten nach den Funktionen ueberschrieben haben. Der Renderer
  (``AppState._render_frame``) meldet sie als ``{universum: {adresse: Name}}``.
* :func:`auswerten` — fuer jede Funktion, die im letzten Frame geschrieben hat:
  auf wie vielen Geraeten sie gewinnt und auf wie vielen sie von wem verdeckt
  ist.

Modify-Effekte (ENG-37) schreiben im Funktions-Durchlauf nichts — sie rechnen
spaeter auf das fertige Bild. Sie tauchen hier darum weder als Schreiber noch
als Verdecker auf. Mitglieder einer Sammlung/Show schreiben im Durchlauf ihres
Behaelters; das Protokoll fuehrt sie unter dessen fid.

Ohne Qt; der Kern rechnet, die Ansicht zeigt nur an.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PROGRAMMER = "Programmer"
SNAP = "Snap"
CUELISTE = "Cueliste"


class SchreibProtokoll:
    """Ein Frame: wer hat welche Adresse zuletzt geschrieben.

    Im Takt wird nur angehaengt (``eintragen`` = ein ``append``, die Menge
    wird uebernommen, nicht kopiert). Die Tabellen ``schreiber`` und
    ``geschrieben`` entstehen erst beim Lesen — also im Anzeige-Takt
    (2–4 Hz), nicht 44-mal je Sekunde."""

    __slots__ = ("_eintraege", "_schreiber", "_geschrieben")

    def __init__(self):
        self._eintraege: list[tuple[int, int, object]] = []
        self._schreiber: dict[int, dict[int, int]] | None = None
        self._geschrieben: dict[int, dict[int, set[int]]] | None = None

    def eintragen(self, fid: int, universum: int, adressen) -> None:
        """``adressen`` gehoert danach dem Protokoll (nicht mehr aendern)."""
        if adressen:
            self._eintraege.append((fid, universum, adressen))

    def _bauen(self) -> None:
        schreiber: dict[int, dict[int, int]] = {}
        geschrieben: dict[int, dict[int, set[int]]] = {}
        for fid, u, adressen in self._eintraege:       # Schreib-Reihenfolge
            ziel = schreiber.get(u)
            if ziel is None:
                ziel = schreiber[u] = {}
            ziel.update(dict.fromkeys(adressen, fid))
            je_u = geschrieben.setdefault(fid, {})
            vorhanden = je_u.get(u)
            if vorhanden is None:
                je_u[u] = set(adressen)
            else:
                vorhanden.update(adressen)
        self._schreiber, self._geschrieben = schreiber, geschrieben

    @property
    def schreiber(self) -> dict[int, dict[int, int]]:
        """universum -> {adresse: fid} (die zuletzt schreibende Funktion)."""
        if self._schreiber is None:
            self._bauen()
        return self._schreiber

    @property
    def geschrieben(self) -> dict[int, dict[int, set[int]]]:
        """fid -> {universum: Adressen}."""
        if self._geschrieben is None:
            self._bauen()
        return self._geschrieben


class Takt:
    """Gemeinsamer Stand aller Mitschnitte eines Takts: welche Funktion
    gerade schreibt. Je Funktion wird nur ``fid`` umgesetzt — unabhaengig
    davon, wie viele Universen es gibt."""

    __slots__ = ("fid",)

    def __init__(self):
        self.fid = None


class Mitschnitt:
    """Steht waehrend des Funktions-Durchlaufs an Stelle des Schreib-Protokolls
    eines Universums (``Universe.write_log_tauschen``) — einmal je Takt und
    Universum eingehaengt, nicht je Funktion. Jede geschriebene Adresse geht an
    das aeussere Protokoll (falls der Renderer eins fuehrt, unveraendert) und
    in die Menge der gerade schreibenden Funktion (``Takt.fid``)."""

    __slots__ = ("aussen", "takt", "je_fid", "_fid", "_menge")

    def __init__(self, aussen, takt: Takt):
        self.aussen = aussen
        self.takt = takt
        self.je_fid: dict[int, set[int]] = {}   # Einfuege-Reihenfolge = Takt
        self._fid = None
        self._menge: set[int] | None = None

    def _ziel(self) -> set[int]:
        fid = self.takt.fid
        if fid != self._fid or self._menge is None:
            m = self.je_fid.get(fid)
            if m is None:
                m = self.je_fid[fid] = set()
            self._fid, self._menge = fid, m
        return self._menge

    def add(self, adresse: int) -> None:
        # heisser Pfad (je geschriebenem Kanal): Ziel nur bei Wechsel suchen
        if self.aussen is not None:
            self.aussen.add(adresse)
        if self.takt.fid == self._fid and self._menge is not None:
            self._menge.add(adresse)
        else:
            self._ziel().add(adresse)

    def update(self, adressen) -> None:
        if self.aussen is not None:
            self.aussen.update(adressen)
        self._ziel().update(adressen)


@dataclass
class Ergebnis:
    """Was eine Funktion im letzten Frame erreicht hat."""
    gewinnt: int = 0                      # Geraete, auf denen alles von ihr ankommt
    verdeckt: int = 0                     # Geraete, auf denen jemand darueber liegt
    # Verdecker -> Anzahl Geraete (jedes verdeckte Geraet zaehlt beim Verdecker
    # mit den meisten Adressen dort), absteigend sortiert.
    von: list[tuple[str, int]] = field(default_factory=list)

    def text(self) -> str:
        """„verdeckt von X auf n Geräten“ — leer, wenn nichts verdeckt ist."""
        if not self.verdeckt or not self.von:
            return ""
        teile = [f"{name} auf {anzahl} {'Gerät' if anzahl == 1 else 'Geräten'}"
                 for name, anzahl in self.von[:2]]
        rest = len(self.von) - 2
        aus = "verdeckt von " + ", ".join(teile)
        if rest > 0:
            aus += f" (+{rest} weitere)"
        return aus

    def tooltip(self) -> str:
        zeilen = [f"gewinnt auf {self.gewinnt} "
                  f"{'Gerät' if self.gewinnt == 1 else 'Geräten'}"]
        if self.verdeckt:
            zeilen.append(f"verdeckt auf {self.verdeckt} "
                          f"{'Gerät' if self.verdeckt == 1 else 'Geräten'}:")
            for name, anzahl in self.von:
                zeilen.append(f"  · {name}: {anzahl}")
        return "\n".join(zeilen)


def geraete_index(patch) -> dict[int, dict[int, object]]:
    """``{universum: {adresse: geraete_schluessel}}`` aus der Patch-Liste
    (Adresse + Kanalzahl). Schluessel ist die fid des Geraets."""
    index: dict[int, dict[int, object]] = {}
    for fx in patch or ():
        try:
            u = int(getattr(fx, "universe", 1) or 1)
            start = int(getattr(fx, "address", 0) or 0)
            n = int(getattr(fx, "channel_count", 0) or 0)
        except (TypeError, ValueError):
            continue
        if start < 1 or n < 1:
            continue
        schl = getattr(fx, "fid", id(fx))
        ziel = index.setdefault(u, {})
        for a in range(start, min(start + n, 513)):
            ziel.setdefault(a, schl)              # Ueberlappung: das erste
    return index


def auswerten(protokoll: SchreibProtokoll | None, oben, patch,
              name_von) -> dict[int, Ergebnis]:
    """Je Funktion des Protokolls: gewinnt / verdeckt, je Geraet gezaehlt.

    ``oben``: ``{universum: {adresse: Name}}`` der Schicht ueber den
    Funktionen (Cuelisten, Programmer, Snap) oder ``None``.
    ``name_von(fid) -> str``: Anzeigename eines verdeckenden Effekts.

    Ein Geraet zaehlt als verdeckt, sobald auch nur eine Adresse, die die
    Funktion dort schreibt, am Ende von jemand anderem kommt. Adressen ohne
    gepatchtes Geraet zaehlen nicht."""
    if protokoll is None:
        return {}
    oben = oben or {}
    index = geraete_index(patch)
    aus: dict[int, Ergebnis] = {}
    for fid, je_u in protokoll.geschrieben.items():
        # geraet -> {verdecker: adressen}; geraet -> True wenn beruehrt
        beruehrt: set = set()
        verdeckt: dict[object, dict[str, int]] = {}
        for u, adressen in je_u.items():
            geraete = index.get(u)
            if not geraete:
                continue
            letzte = protokoll.schreiber.get(u, {})
            darueber = oben.get(u, {})
            for a in adressen:
                g = geraete.get(a)
                if g is None:
                    continue
                beruehrt.add(g)
                wer = darueber.get(a)
                if wer is None:
                    w = letzte.get(a, fid)
                    if w == fid:
                        continue
                    wer = _name(name_von, w)
                zaehler = verdeckt.setdefault(g, {})
                zaehler[wer] = zaehler.get(wer, 0) + 1
        if not beruehrt:
            continue
        je_verdecker: dict[str, int] = {}
        for zaehler in verdeckt.values():
            haupt = max(sorted(zaehler), key=lambda k: zaehler[k])
            je_verdecker[haupt] = je_verdecker.get(haupt, 0) + 1
        aus[fid] = Ergebnis(
            gewinnt=len(beruehrt) - len(verdeckt),
            verdeckt=len(verdeckt),
            von=sorted(je_verdecker.items(), key=lambda kv: (-kv[1], kv[0])))
    return aus


def _name(name_von, fid) -> str:
    try:
        n = name_von(fid)
    except Exception:
        n = None
    return str(n) if n else f"Effekt {fid}"
