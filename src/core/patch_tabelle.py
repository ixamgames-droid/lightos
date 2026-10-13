"""IMP-1: Patch aus einer Tabelle (CSV) — lesen, zuordnen, pruefen, anwenden.

Wer von einem anderen Lichtprogramm umsteigt, tippt oder exportiert seine
Geraeteliste als Tabelle ``Name; Profil; Universum; Adresse`` und LightOS legt
die Geraete an. Dieses Modul ist der Kern OHNE Qt:

* :func:`lies_tabelle` / :func:`lies_datei` — Text bzw. Datei -> :class:`Tabelle`
  (Trennzeichen und Kodierung erkennen, Kopfzeile grosszuegig deuten).
* :class:`Bibliothek` — Profil + Modus zu dem finden, was in der Tabelle steht.
* :func:`baue_plan` — je Tabellenzeile ein :class:`PlanZeile` mit Profil, Modus,
  Kanalzahl, Adressen und dem Ergebnis aller Pruefungen.
* :func:`wende_an` — legt die anlegbaren Zeilen ueber ``AppState.add_fixture``
  an (derselbe Weg wie das Patchen von Hand), als EIN Rueckgaengig-Schritt.

★ Zwei Regeln, die nicht aufgeweicht werden duerfen:

1. **Nie still ein falsches Profil.** Zugeordnet wird nur ein exakter Treffer
   oder ein EINDEUTIGER Treffer ohne Gross/Klein und Leerzeichen. Alles andere
   (mehrere Treffer, nur aehnlich, mehrere Modi ohne Angabe) bleibt „offen“ und
   wird nicht angelegt, bis jemand ein Profil waehlt. Ein falsches Profil
   faellt erst auf der Buehne auf — als Geraet, das auf dem falschen Kanal
   blitzt.
2. **Vorhandenes wird nie veraendert.** Der Import legt nur an. Eine Zeile,
   die sich mit einem vorhandenen Geraet ueberschneidet, wird ausgelassen.
"""
from __future__ import annotations

import csv
import difflib
import io
import re
from contextlib import nullcontext
from dataclasses import dataclass, field, replace

from .patch_ueberlappung import ueberlappende_paare

UNIVERSUM_MIN = 1
#: Wie der Dialog „Geraet hinzufuegen“ (``fixture_browser._UNIVERSE_MAX``) —
#: per Test aneinander gebunden.
UNIVERSUM_MAX = 32
UNIVERSUM_GROESSE = 512
ANZAHL_MAX = 512

# ── Spalten ──────────────────────────────────────────────────────────────────

NAME, HERSTELLER, PROFIL, MODUS = "name", "hersteller", "profil", "modus"
UNIVERSUM, ADRESSE, ANZAHL, KANAELE = "universum", "adresse", "anzahl", "kanaele"

#: Ueberschriften in der Vorlage und in Meldungen.
SPALTEN_TEXT = {
    NAME: "Name", HERSTELLER: "Hersteller", PROFIL: "Profil", MODUS: "Modus",
    UNIVERSUM: "Universum", ADRESSE: "Adresse", ANZAHL: "Anzahl",
    KANAELE: "Kanäle",
}

#: Was als Spaltenname gilt — in der Vergleichsform von :func:`_schluessel`
#: (klein, Umlaute ausgeschrieben, nur Buchstaben/Ziffern). „Geraet“ und „Typ“
#: meinen das Profil: so heissen die Spalten in der Patch-Tabelle von LightOS
#: („Label“, „Gerät“) und in den Listen der meisten Lichtprogramme.
_SPALTEN_NAMEN = {
    NAME: ("name", "label", "bezeichnung", "geraetename", "anzeigename",
           "beschriftung", "fixturelabel"),
    HERSTELLER: ("hersteller", "manufacturer", "marke", "brand", "fabrikat",
                 "make"),
    PROFIL: ("profil", "profile", "modell", "model", "fixture", "geraet",
             "geraetetyp", "typ", "type", "fixturetype", "device", "lampe",
             "produkt", "product"),
    MODUS: ("modus", "mode", "betriebsart", "kanalmodus", "dmxmodus",
            "dmxmode"),
    UNIVERSUM: ("universum", "universe", "univ", "uni", "dmxuniversum",
                "dmxuniverse", "linie", "line"),
    ADRESSE: ("adresse", "address", "dmx", "dmxadresse", "dmxaddress",
              "startadresse", "startaddress", "start", "addr", "adr", "patch"),
    ANZAHL: ("anzahl", "count", "menge", "stueck", "stk", "qty", "quantity"),
    KANAELE: ("kanaele", "kanalzahl", "channels", "channelcount", "footprint",
              "ch"),
}
_SPALTE_ZU = {wort: spalte for spalte, woerter in _SPALTEN_NAMEN.items()
              for wort in woerter}

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _schluessel(text: str) -> str:
    """Vergleichsform eines Spaltennamens: ``"DMX-Adresse"`` -> ``dmxadresse``."""
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold().translate(_UMLAUTE))


def _ohne_leer(text: str) -> str:
    """Vergleichsform fuer Profil/Hersteller/Modus: Gross/Klein und
    Leerzeichen zaehlen nicht — sonst nichts (Regel 1 im Modulkopf)."""
    return "".join((text or "").split()).casefold()


# ── Tabelle lesen ────────────────────────────────────────────────────────────

TRENNZEICHEN_TEXT = {";": "Semikolon", ",": "Komma", "\t": "Tabulator"}


@dataclass
class Zeile:
    """Eine Datenzeile der Tabelle, so wie sie dort steht."""
    nr: int                     # Zeilennummer in der Datei (1 = erste Zeile)
    name: str = ""
    hersteller: str = ""
    profil: str = ""
    modus: str = ""
    universum: int | None = None
    adresse: int | None = None
    anzahl: int = 1
    kanaele: int | None = None
    fehler: list[str] = field(default_factory=list)

    @property
    def profil_text(self) -> str:
        """Was die Tabelle als Geraet nennt — fuer die Vorschau."""
        text = " ".join(t for t in (self.hersteller, self.profil) if t)
        if self.modus:
            text += f" · {self.modus}"
        elif self.kanaele:
            text += f" · {self.kanaele} Kanäle"
        return text


@dataclass
class Tabelle:
    zeilen: list[Zeile] = field(default_factory=list)
    trennzeichen: str = ";"
    kodierung: str = "UTF-8"
    kopfzeile: bool = True
    spalten: dict[str, int] = field(default_factory=dict)
    hinweise: list[str] = field(default_factory=list)
    #: Nicht leer = die Tabelle ist als Ganzes nicht lesbar (keine Zeilen).
    fehler: str = ""


def dekodiere(daten: bytes) -> tuple[str, str]:
    """Bytes -> ``(Text, Name der Kodierung)``. UTF-8 mit oder ohne BOM,
    UTF-16 mit BOM („Unicode-Text“ aus Tabellenprogrammen), sonst cp1252 —
    das schreibt ein deutsches Windows-Tabellenprogramm bei „CSV“."""
    if daten.startswith(b"\xef\xbb\xbf"):
        return daten[3:].decode("utf-8", errors="replace"), "UTF-8 (mit BOM)"
    if daten[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return daten.decode("utf-16"), "UTF-16"
        except UnicodeDecodeError:
            pass
    try:
        return daten.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        return daten.decode("cp1252", errors="replace"), "Windows-1252"


def erkenne_trennzeichen(text: str) -> str:
    """``;``, Tabulator oder ``,`` — das Zeichen, das die meisten der ersten
    Zeilen in GLEICH viele Spalten (mehr als eine) teilt. Bei Gleichstand in
    dieser Reihenfolge; ein Komma im Geraetenamen kippt damit keine
    Semikolon-Tabelle."""
    proben = [z for z in text.splitlines() if z.strip()][:20]
    bestes, beste_wertung = ";", (0, 0)
    for zeichen in (";", "\t", ","):
        try:
            breiten = [len(next(csv.reader([z], delimiter=zeichen), []))
                       for z in proben]
        except csv.Error:
            # z. B. ein Feld ueber der Groessengrenze — den Satz dazu liefert
            # ``lies_tabelle`` beim eigentlichen Lesen.
            continue
        mehr = [b for b in breiten if b > 1]
        if not mehr:
            continue
        haeufigste = max(set(mehr), key=mehr.count)
        wertung = (mehr.count(haeufigste), haeufigste)
        if wertung > beste_wertung:
            bestes, beste_wertung = zeichen, wertung
    return bestes


_ADRESSE = re.compile(r"^(?:(\d+)\s*[./:]\s*)?(\d+)$")
#: „2“, „U2“, „Univ. 2“, „Universum 2“ — ein Wort davor ist erlaubt, ein
#: Vorzeichen oder Rechenzeichen nicht: „-1“ darf nicht still Universum 1 werden.
_UNIVERSUM = re.compile(r"^(?:[^\W\d_]+[\s.:#]*)?(\d+)$")


def _zahl(text: str) -> int | None:
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def _ist_zahl_artig(text: str) -> bool:
    return bool(_ADRESSE.match((text or "").strip()))


def _kopf_deuten(zellen: list[str]) -> dict[str, int]:
    """Spalte -> Index fuer die Zellen, die wie eine Ueberschrift heissen.
    Steht eine Spalte doppelt da, zaehlt die erste."""
    spalten: dict[str, int] = {}
    for i, zelle in enumerate(zellen):
        spalte = _SPALTE_ZU.get(_schluessel(zelle))
        if spalte is not None:
            spalten.setdefault(spalte, i)
    return spalten


#: Ohne Kopfzeile: die Reihenfolge der Vorlage in ihrer kurzen Form.
_OHNE_KOPF = {
    3: (NAME, PROFIL, ADRESSE),
    4: (NAME, PROFIL, UNIVERSUM, ADRESSE),
}


def lies_tabelle(text: str, kodierung: str = "UTF-8") -> Tabelle:
    """Tabellentext -> :class:`Tabelle`. Wirft nicht: was nicht lesbar ist,
    steht in ``Tabelle.fehler`` (ganze Tabelle) bzw. ``Zeile.fehler``."""
    tab = Tabelle(kodierung=kodierung)
    text = text.replace("\x00", "")
    # Tabellenprogramme schreiben manchmal „sep=;“ als erste Zeile.
    vorgabe = re.match(r"^\s*sep=(.)\s*\r?\n", text, flags=re.IGNORECASE)
    if vorgabe:
        tab.trennzeichen = vorgabe.group(1)
        text = text[vorgabe.end():]
        versatz = 1
    else:
        tab.trennzeichen = erkenne_trennzeichen(text)
        versatz = 0

    leser = csv.reader(io.StringIO(text, newline=""),
                       delimiter=tab.trennzeichen)
    roh: list[tuple[int, list[str]]] = []
    try:
        for zellen in leser:
            zellen = [z.strip() for z in zellen]
            if not any(zellen) or zellen[0].startswith("#"):
                continue                      # Leer- und Kommentarzeilen
            roh.append((leser.line_num + versatz, zellen))
    except csv.Error as e:
        tab.fehler = f"Die Tabelle lässt sich nicht lesen ({e})."
        return tab
    if not roh:
        tab.fehler = "Die Tabelle ist leer."
        return tab

    erste = roh[0][1]
    spalten = _kopf_deuten(erste)
    tab.kopfzeile = len(spalten) >= 2 or (
        len(spalten) == 1 and not any(_ist_zahl_artig(z) for z in erste))
    if tab.kopfzeile:
        daten = roh[1:]
        unbekannt = [z for i, z in enumerate(erste)
                     if z and i not in spalten.values()]
        if unbekannt:
            tab.hinweise.append(
                "Nicht verwendete Spalten: " + ", ".join(unbekannt) + ".")
    else:
        daten = roh
        folge = _OHNE_KOPF.get(len(erste))
        if folge is None:
            tab.fehler = (
                "In der ersten Zeile steht keine Kopfzeile mit Spaltennamen "
                "(zum Beispiel „Name; Profil; Universum; Adresse“). Ohne "
                "Kopfzeile versteht LightOS nur Tabellen mit genau drei "
                "(Name; Profil; Adresse) oder vier Spalten "
                "(Name; Profil; Universum; Adresse).")
            return tab
        spalten = {spalte: i for i, spalte in enumerate(folge)}
        tab.hinweise.append(
            "Keine Kopfzeile gefunden — die Spalten werden gelesen als: "
            + "; ".join(SPALTEN_TEXT[s] for s in folge) + ".")
    tab.spalten = spalten

    fehlend = [SPALTEN_TEXT[s] for s in (PROFIL, ADRESSE) if s not in spalten]
    if fehlend:
        tab.fehler = ("In der Kopfzeile fehlt die Spalte "
                      + " und die Spalte ".join(f"„{f}“" for f in fehlend)
                      + ". Gebraucht werden mindestens Profil und Adresse.")
        return tab
    if not daten:
        tab.fehler = "Die Tabelle hat eine Kopfzeile, aber keine Geräte."
        return tab

    for nr, zellen in daten:
        tab.zeilen.append(_zeile_deuten(nr, zellen, spalten))
    return tab


def _zeile_deuten(nr: int, zellen: list[str], spalten: dict[str, int]) -> Zeile:
    def zelle(spalte: str) -> str:
        i = spalten.get(spalte)
        return zellen[i] if i is not None and i < len(zellen) else ""

    z = Zeile(nr=nr, name=zelle(NAME), hersteller=zelle(HERSTELLER),
              profil=zelle(PROFIL), modus=zelle(MODUS))

    universum_aus_adresse = None
    roh = zelle(ADRESSE)
    treffer = _ADRESSE.match(roh)
    if not roh:
        z.fehler.append("Die Adresse fehlt.")
    elif not treffer:
        z.fehler.append(
            f"Die Adresse „{roh}“ ist keine Zahl (erlaubt: 101, oder mit "
            "Universum davor: 2.101 oder 2/101).")
    else:
        z.adresse = int(treffer.group(2))
        if treffer.group(1) is not None:
            universum_aus_adresse = int(treffer.group(1))

    roh = zelle(UNIVERSUM)
    if roh:
        treffer = _UNIVERSUM.match(roh)
        if not treffer:
            z.fehler.append(f"Das Universum „{roh}“ ist keine Zahl.")
        else:
            z.universum = int(treffer.group(1))
    if universum_aus_adresse is not None:
        if z.universum is not None and z.universum != universum_aus_adresse:
            z.fehler.append(
                f"Das Universum steht zweimal da und widerspricht sich: "
                f"Spalte Universum sagt {z.universum}, die Adresse sagt "
                f"{universum_aus_adresse}.")
        else:
            z.universum = universum_aus_adresse

    roh = zelle(ANZAHL)
    if roh:
        anzahl = _zahl(roh)
        if anzahl is None or not 1 <= anzahl <= ANZAHL_MAX:
            z.fehler.append(
                f"Die Anzahl „{roh}“ muss eine Zahl von 1 bis {ANZAHL_MAX} sein.")
        else:
            z.anzahl = anzahl

    roh = zelle(KANAELE)
    if roh:
        # „8“, „8ch“, „8 Kanäle“ — nur ein Hinweis fuer die Modus-Wahl.
        treffer = re.match(r"^(\d+)", roh)
        z.kanaele = int(treffer.group(1)) if treffer else None
    return z


def lies_datei(pfad: str) -> Tabelle:
    """Datei -> :class:`Tabelle`. Eine nicht lesbare Datei wird zu
    ``Tabelle.fehler`` — der Aufrufer zeigt den Satz, statt abzustuerzen."""
    try:
        with open(pfad, "rb") as f:
            daten = f.read()
    except OSError as e:
        return Tabelle(fehler=f"Die Datei lässt sich nicht öffnen ({e.strerror or e}).")
    if daten.startswith(b"PK\x03\x04"):
        return Tabelle(fehler=(
            "Das ist eine Excel-Arbeitsmappe (.xlsx), keine CSV-Tabelle. Im "
            "Tabellenprogramm „Speichern unter…“ wählen und als Dateityp "
            "„CSV (Trennzeichen-getrennt)“ nehmen."))
    text, kodierung = dekodiere(daten)
    return lies_tabelle(text, kodierung)


# ── Vorlage ──────────────────────────────────────────────────────────────────

#: Kopfzeile + zwei Beispiele. Beide Profile liefert LightOS mit, die Vorlage
#: laesst sich also unveraendert einlesen (per Test belegt).
VORLAGE_ZEILEN = (
    ("Name", "Hersteller", "Profil", "Modus", "Universum", "Adresse", "Anzahl"),
    ("PAR vorne", "Generic", "Stage Light ZQ01424", "8-Kanal RGBW", "1", "1", "4"),
    ("Moving Head links", "U King", "ZQ02001 Mini Moving Head", "11-Kanal",
     "1", "101", "1"),
)


def vorlage_text() -> str:
    puffer = io.StringIO(newline="")
    csv.writer(puffer, delimiter=";", lineterminator="\r\n").writerows(VORLAGE_ZEILEN)
    return puffer.getvalue()


def schreibe_vorlage(pfad: str) -> None:
    """Beispiel-Tabelle schreiben: Semikolon, UTF-8 MIT BOM und CRLF — so
    oeffnet sie ein deutsches Tabellenprogramm per Doppelklick richtig
    (Spalten getrennt, Umlaute heil)."""
    with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
        f.write(vorlage_text())


# ── Bibliothek: Profil und Modus finden ──────────────────────────────────────

@dataclass(frozen=True)
class Modus:
    name: str
    kanaele: int


@dataclass(frozen=True)
class Profil:
    id: int
    hersteller: str
    name: str
    typ: str = "other"
    modi: tuple[Modus, ...] = ()

    @property
    def anzeige(self) -> str:
        return f"{self.hersteller} {self.name}".strip()

    def modus(self, name: str) -> Modus | None:
        return next((m for m in self.modi if m.name == name), None)


EXAKT, UNSCHARF, GEWAEHLT, OFFEN = "exakt", "unscharf", "gewaehlt", "offen"

#: So viele aehnliche Profile bietet eine offene Zeile hoechstens an.
VORSCHLAEGE_MAX = 6
_AEHNLICH_AB = 0.6


@dataclass(frozen=True)
class Fund:
    profil: Profil | None
    art: str
    grund: str = ""
    vorschlaege: tuple[Profil, ...] = ()


def _nur_zeichen(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold().translate(_UMLAUTE))


class Bibliothek:
    """Die Profile, aus denen der Import waehlen darf."""

    def __init__(self, profile):
        self.profile: list[Profil] = list(profile)
        self._nach_id = {p.id: p for p in self.profile}
        self._funde: dict[tuple[str, str], Fund] = {}
        self._aehnlich_form = [(_nur_zeichen(p.name), _nur_zeichen(p.anzeige))
                               for p in self.profile]

    def profil(self, profil_id) -> Profil | None:
        return self._nach_id.get(profil_id)

    def finde(self, hersteller: str, text: str) -> Fund:
        """Profil zu ``hersteller`` (darf leer sein) + ``text`` aus der Tabelle."""
        h, t = (hersteller or "").strip(), (text or "").strip()
        fund = self._funde.get((h, t))
        if fund is None:
            fund = self._funde[(h, t)] = self._finde(h, t)
        return fund

    def _finde(self, h: str, t: str) -> Fund:
        if not t:
            return Fund(None, OFFEN, "In der Tabelle steht kein Profil.")
        # Stufe 1: buchstabengenau. Ohne Hersteller-Spalte darf der Hersteller
        # auch vorn im Profilnamen stehen („Eurolite LED PAR-56“).
        exakt = [p for p in self.profile
                 if (p.name == t and (not h or p.hersteller == h))
                 or (not h and p.anzeige == t)]
        if len(exakt) == 1:
            return Fund(exakt[0], EXAKT)
        if len(exakt) > 1:
            return Fund(None, OFFEN, self._mehrere(exakt, h), tuple(exakt))
        # Stufe 2: ohne Gross/Klein und Leerzeichen — nur wenn EINDEUTIG.
        nt, nh = _ohne_leer(t), _ohne_leer(h)
        lose = [p for p in self.profile
                if (_ohne_leer(p.name) == nt
                    and (not nh or _ohne_leer(p.hersteller) == nh))
                or (not nh and _ohne_leer(p.anzeige) == nt)]
        if len(lose) == 1:
            return Fund(lose[0], UNSCHARF)
        if len(lose) > 1:
            return Fund(None, OFFEN, self._mehrere(lose, h), tuple(lose))
        # Stufe 3: nur Vorschlaege — nie eine Zuordnung.
        aehnliche = self.aehnliche(h, t)
        gesucht = f"{h} {t}".strip()
        if aehnliche:
            grund = (f"„{gesucht}“ steht so nicht in der Geräte-Bibliothek — "
                     "bitte eines der ähnlichen Profile wählen.")
        else:
            grund = (f"„{gesucht}“ steht nicht in der Geräte-Bibliothek, und "
                     "es gibt kein ähnliches Profil.")
        return Fund(None, OFFEN, grund, tuple(aehnliche))

    @staticmethod
    def _mehrere(treffer, h: str) -> str:
        if h:
            return (f"Die Bibliothek hat {len(treffer)} Profile mit diesem "
                    "Hersteller und Namen — bitte eines wählen.")
        return (f"{len(treffer)} Profile heißen so (verschiedene Hersteller) — "
                "bitte eines wählen.")

    def aehnliche(self, h: str, t: str) -> list[Profil]:
        """Die aehnlichsten Profile, beste zuerst (hoechstens
        :data:`VORSCHLAEGE_MAX`)."""
        name, voll = _nur_zeichen(t), _nur_zeichen(f"{h} {t}")
        if not name:
            return []
        proben = {name, voll}
        vergleicher = {probe: difflib.SequenceMatcher(None, "", probe, autojunk=False)
                       for probe in proben}
        gewertet: list[tuple[float, int]] = []
        for i, formen in enumerate(self._aehnlich_form):
            beste = 0.0
            for form in set(formen):
                if not form:
                    continue
                for probe, sm in vergleicher.items():
                    if len(probe) >= 3 and (probe in form or form in probe):
                        beste = max(beste, 0.8 + 0.2 * min(len(probe), len(form))
                                    / max(len(probe), len(form)))
                        continue
                    sm.set_seq1(form)
                    if sm.real_quick_ratio() < _AEHNLICH_AB \
                            or sm.quick_ratio() < _AEHNLICH_AB:
                        continue
                    beste = max(beste, sm.ratio())
            if beste >= _AEHNLICH_AB:
                gewertet.append((beste, i))
        gewertet.sort(key=lambda w: (-w[0], self.profile[w[1]].anzeige.casefold()))
        return [self.profile[i] for _, i in gewertet[:VORSCHLAEGE_MAX]]


_KANAL_ANGABE = re.compile(
    r"^(\d+)\s*-?\s*(ch|chan|channel|channels|kanal|kanaele|kanäle|k)\.?$",
    re.IGNORECASE)


def finde_modus(profil: Profil, text: str = "",
                kanaele: int | None = None) -> tuple[Modus | None, str]:
    """Modus von ``profil`` zu dem, was die Tabelle sagt -> ``(Modus, Grund)``.

    Ohne Angabe gilt nur ein Profil mit EINEM Modus als eindeutig — nie
    „der erste“: 8 und 14 Kanaele desselben Geraets verschieben jede Adresse
    dahinter."""
    modi = profil.modi
    if not modi:
        return None, "Dieses Profil hat keinen Modus."
    text = (text or "").strip()
    if text:
        for m in modi:
            if m.name == text:
                return m, ""
        lose = [m for m in modi if _ohne_leer(m.name) == _ohne_leer(text)]
        if len(lose) == 1:
            return lose[0], ""
        # „8ch“ / „8 Kanal“: die Kanalzahl statt des Modusnamens.
        angabe = _KANAL_ANGABE.match(text)
        if angabe:
            passend = [m for m in modi if m.kanaele == int(angabe.group(1))]
            if len(passend) == 1:
                return passend[0], ""
        return None, (f"Den Modus „{text}“ gibt es bei diesem Profil nicht — "
                      "bitte einen wählen.")
    if len(modi) == 1:
        return modi[0], ""
    if kanaele:
        passend = [m for m in modi if m.kanaele == kanaele]
        if len(passend) == 1:
            return passend[0], ""
    return None, (f"Das Profil hat {len(modi)} Modi und die Tabelle nennt "
                  "keinen — bitte einen wählen.")


def bibliothek_aus_db() -> Bibliothek:
    """Die Geraete-Bibliothek, wie die Suche sie anbietet: ohne die QLC+-Importe,
    die ein LightOS-Profil abloest (FM-63)."""
    from .database import fixture_db as fdb
    weg = fdb.abgeloeste_profil_ids()
    profile = []
    for hersteller in fdb.get_all_manufacturers():
        for p in hersteller.fixtures:
            if p.id in weg:
                continue
            profile.append(Profil(
                id=p.id, hersteller=hersteller.name or "", name=p.name or "",
                typ=p.fixture_type or "other",
                modi=tuple(Modus(m.name, int(m.channel_count or 0))
                           for m in p.modes)))
    return Bibliothek(profile)


# ── Plan ─────────────────────────────────────────────────────────────────────

ANLEGBAR, UEBERSCHNEIDUNG, FEHLER = "anlegbar", "ueberschneidung", "fehler"
# OFFEN (oben) ist zugleich der vierte Status.

STATUS_TEXT = {
    ANLEGBAR: "wird angelegt",
    OFFEN: "offen",
    UEBERSCHNEIDUNG: "wird nicht angelegt — Überschneidung",
    FEHLER: "wird nicht angelegt",
}


@dataclass(frozen=True)
class Belegung:
    """Ein vorhandenes Geraet, soweit der Import es kennen muss."""
    name: str
    universum: int
    adresse: int
    kanaele: int
    belegt_dmx: bool = True


@dataclass(frozen=True)
class Geraet:
    """Ein Geraet, das der Import anlegen wuerde."""
    name: str
    universum: int
    adresse: int
    kanaele: int

    @property
    def ende(self) -> int:
        return self.adresse + self.kanaele - 1


@dataclass
class PlanZeile:
    index: int                              # Position in ``Tabelle.zeilen``
    zeile: Zeile
    profil: Profil | None = None
    modus: Modus | None = None
    art: str = OFFEN
    vorschlaege: tuple[Profil, ...] = ()
    geraete: list[Geraet] = field(default_factory=list)
    status: str = OFFEN
    gruende: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    #: IMP-3: ``(Name aus der Tabelle, neuer Name)`` je Geraet, das beim
    #: Import eine Nummer bekommt, weil es den Namen schon gab.
    umbenannt: list[tuple[str, str]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return (self.zeile.name or (self.profil.name if self.profil else "")
                or self.zeile.profil)

    @property
    def anzeige_name(self) -> str:
        """IMP-3: der Name, unter dem die Zeile WIRKLICH angelegt wird — fuer
        die Spalte „Name“ der Vorschau. Bei mehreren Geraeten erster und
        letzter Name, sobald einer davon umbenannt wurde."""
        if self.status != ANLEGBAR or not self.geraete:
            return self.name
        if len(self.geraete) == 1:
            return self.geraete[0].name
        if self.umbenannt:
            return f"{self.geraete[0].name} … {self.geraete[-1].name}"
        return self.name

    def _umbenannt_text(self) -> str:
        neu = [f"„{n}“" for _alt, n in self.umbenannt]
        if len(neu) == 1:
            if len(self.geraete) == 1:
                return f"Name gab es schon, heißt jetzt {neu[0]}."
            return f"1 Name gab es schon, das Gerät heißt jetzt {neu[0]}."
        if len(neu) > 4:
            liste = ", ".join(neu[:3]) + f" … {neu[-1]}"
        else:
            liste = ", ".join(neu[:-1]) + " und " + neu[-1]
        return f"{len(neu)} Namen gab es schon, die Geräte heißen jetzt {liste}."

    @property
    def universum(self) -> int:
        return self.zeile.universum if self.zeile.universum is not None else 1

    @property
    def kanaele(self) -> int | None:
        return self.modus.kanaele if self.modus else None

    @property
    def status_text(self) -> str:
        """Ein Satz fuer die Status-Spalte: was passiert und warum."""
        if self.status == ANLEGBAR:
            n = len(self.geraete)
            text = STATUS_TEXT[ANLEGBAR] + (f" ({n} Geräte)" if n > 1 else "")
            if self.umbenannt:
                # IMP-3: vorn im Satz, nicht hinten bei den Hinweisen — der
                # Name im Patch ist ein anderer als der in der Tabelle.
                text += " — " + self._umbenannt_text()
        elif self.status == OFFEN:
            text = "offen — " + " ".join(self.gruende)
        else:
            text = "wird nicht angelegt — " + " ".join(self.gruende)
        if self.hinweise:
            text += "  Hinweis: " + " ".join(self.hinweise)
        return text


@dataclass
class Plan:
    tabelle: Tabelle
    zeilen: list[PlanZeile]
    wahl: dict[int, tuple[int, str]]

    def anlegbare(self) -> list[PlanZeile]:
        return [z for z in self.zeilen if z.status == ANLEGBAR]

    def zaehler(self) -> dict[str, int]:
        """``{"geraete": …, OFFEN: …, UEBERSCHNEIDUNG: …, FEHLER: …}`` —
        Geraete, die angelegt werden, und ZEILEN je anderem Status."""
        z = {"geraete": sum(len(p.geraete) for p in self.anlegbare()),
             "umbenannt": sum(len(p.umbenannt) for p in self.anlegbare())}
        for status in (OFFEN, UEBERSCHNEIDUNG, FEHLER):
            z[status] = sum(1 for p in self.zeilen if p.status == status)
        return z

    def zaehlerzeile(self) -> str:
        z = self.zaehler()
        n = z["geraete"]
        teile = ["Kein Gerät wird angelegt" if n == 0
                 else "1 Gerät wird angelegt" if n == 1
                 else f"{n} Geräte werden angelegt"]
        if z["umbenannt"]:
            teile[0] += f" ({z['umbenannt']} umbenannt, weil es den Namen schon gab)"
        if z[OFFEN]:
            teile.append(f"{z[OFFEN]} offen")
        if z[UEBERSCHNEIDUNG]:
            n = z[UEBERSCHNEIDUNG]
            teile.append(f"{n} Überschneidung" + ("en" if n > 1 else ""))
        if z[FEHLER]:
            teile.append(f"{z[FEHLER]} mit Fehler")
        return ", ".join(teile)


def belegung_aus_state(state) -> list[Belegung]:
    """Der vorhandene Patch als :class:`Belegung`. Netzwerk-Geraete (Laser
    ueber IP) belegen keine DMX-Kanaele, ihr Name zaehlt aber."""
    from .app_state import fixture_uses_dmx
    return [Belegung(name=f.label or "", universum=int(f.universe),
                     adresse=int(f.address), kanaele=int(f.channel_count),
                     belegt_dmx=bool(fixture_uses_dmx(f)))
            for f in state.get_patched_fixtures()]


def baue_plan(tabelle: Tabelle, bibliothek: Bibliothek, vorhandene=(),
              wahl: dict[int, tuple[int, str]] | None = None) -> Plan:
    """Aus Tabelle + Bibliothek + vorhandenem Patch den Plan rechnen.

    ``wahl``: was der Nutzer fuer eine Zeile ausgesucht hat —
    ``{Zeilenindex: (Profil-ID, Modusname)}``. Eine Wahl, die es in der
    Bibliothek nicht (mehr) gibt, zaehlt nicht."""
    wahl = dict(wahl or {})
    vorhandene = list(vorhandene)
    zeilen = [_plan_zeile(i, z, bibliothek, wahl.get(i))
              for i, z in enumerate(tabelle.zeilen)]
    _pruefe_ueberschneidungen(zeilen, vorhandene)
    _vergib_namen(zeilen, vorhandene)
    return Plan(tabelle=tabelle, zeilen=zeilen, wahl=wahl)


def _plan_zeile(index: int, z: Zeile, bibliothek: Bibliothek, gewaehlt) -> PlanZeile:
    pz = PlanZeile(index=index, zeile=z)
    fund = bibliothek.finde(z.hersteller, z.profil)
    pz.vorschlaege = fund.vorschlaege
    offen_grund = ""

    profil = modus = None
    if gewaehlt is not None:
        profil = bibliothek.profil(gewaehlt[0])
        modus = profil.modus(gewaehlt[1]) if profil else None
    if profil is not None and modus is not None:
        pz.profil, pz.modus, pz.art = profil, modus, GEWAEHLT
    elif fund.profil is not None:
        pz.profil, pz.art = fund.profil, fund.art
        pz.modus, offen_grund = finde_modus(fund.profil, z.modus, z.kanaele)
        if fund.art == UNSCHARF:
            pz.hinweise.append(
                f"Profil ohne Rücksicht auf Groß-/Kleinschreibung und "
                f"Leerzeichen erkannt („{fund.profil.anzeige}“).")
    else:
        offen_grund = fund.grund

    # Fehler aus der Tabelle selbst und Bereichspruefungen — eine Profilwahl
    # heilt sie nicht, darum gehen sie „offen“ vor.
    pz.gruende.extend(z.fehler)
    if z.universum is not None and not UNIVERSUM_MIN <= z.universum <= UNIVERSUM_MAX:
        pz.gruende.append(
            f"Universum {z.universum} gibt es nicht (erlaubt: "
            f"{UNIVERSUM_MIN} bis {UNIVERSUM_MAX}).")
    if z.adresse is not None and not 1 <= z.adresse <= UNIVERSUM_GROESSE:
        pz.gruende.append(
            f"Adresse {z.adresse} liegt nicht im Bereich 1 bis "
            f"{UNIVERSUM_GROESSE}.")
    if pz.gruende:
        pz.status = FEHLER
        return pz
    if pz.profil is None or pz.modus is None:
        pz.status = OFFEN
        pz.gruende.append(offen_grund)
        return pz

    kanaele = pz.modus.kanaele
    if kanaele < 1:
        pz.status = FEHLER
        pz.gruende.append(f"Der Modus „{pz.modus.name}“ hat keine Kanäle.")
        return pz
    if z.kanaele and z.kanaele != kanaele and pz.art != GEWAEHLT:
        pz.hinweise.append(
            f"Die Tabelle nennt {z.kanaele} Kanäle, der Modus "
            f"„{pz.modus.name}“ hat {kanaele}.")
    for k in range(z.anzahl):
        adresse = z.adresse + k * kanaele
        if adresse + kanaele - 1 > UNIVERSUM_GROESSE:
            pz.status = FEHLER
            wer = "Das Gerät" if z.anzahl == 1 else f"Gerät {k + 1} von {z.anzahl}"
            pz.gruende.append(
                f"{wer} passt nicht mehr ins Universum: {kanaele} Kanäle ab "
                f"Adresse {adresse} reichen über Kanal {UNIVERSUM_GROESSE} hinaus.")
            pz.geraete = []
            return pz
        name = pz.name if z.anzahl == 1 else f"{pz.name} {k + 1}"
        pz.geraete.append(Geraet(name, pz.universum, adresse, kanaele))
    pz.status = ANLEGBAR
    return pz


def _pruefe_ueberschneidungen(zeilen: list[PlanZeile], vorhandene) -> None:
    """Anlegbare Zeilen gegen den vorhandenen Patch und gegeneinander pruefen.

    Ueberschneiden sich zwei Zeilen der Tabelle, werden BEIDE nicht angelegt:
    welche von beiden stimmt, weiss nur, wer die Tabelle geschrieben hat."""
    eintraege: dict[int, list] = {}
    for b in vorhandene:
        if b.belegt_dmx and b.kanaele > 0:
            eintraege.setdefault(b.universum, []).append(
                (b.adresse, b.adresse + b.kanaele - 1, (None, b)))
    for pz in zeilen:
        if pz.status != ANLEGBAR:
            continue
        for g in pz.geraete:
            eintraege.setdefault(g.universum, []).append(
                (g.adresse, g.ende, (pz, g)))
    gruende: dict[int, list[str]] = {}

    def melde(pz: PlanZeile, text: str) -> None:
        liste = gruende.setdefault(pz.index, [])
        if text not in liste:
            liste.append(text)

    for universum in eintraege:
        for a, b in ueberlappende_paare(eintraege[universum]):
            (pa, ga), (pb, gb) = a[2], b[2]
            if pa is None and pb is None:
                continue                        # zwei vorhandene: nicht unser Thema
            if pa is pb:
                continue
            for hier, dort, dort_g in ((pa, pb, gb), (pb, pa, ga)):
                if hier is None:
                    continue
                if dort is None:
                    melde(hier, f"Überschneidet sich mit dem vorhandenen Gerät "
                                f"„{dort_g.name}“ (Universum {universum}, Kanal "
                                f"{dort_g.adresse} bis "
                                f"{dort_g.adresse + dort_g.kanaele - 1}).")
                else:
                    melde(hier, f"Überschneidet sich mit Zeile {dort.zeile.nr} "
                                f"der Tabelle („{dort.name}“).")
    for pz in zeilen:
        if pz.index in gruende:
            pz.status = UEBERSCHNEIDUNG
            pz.gruende.extend(gruende[pz.index])
            pz.geraete = []


_NAME_MIT_NUMMER = re.compile(r"^(.*\S)\s+(\d+)$")


def naechster_freier_name(name: str, belegt) -> str:
    """IMP-3: ``name`` mit der naechsten freien Nummer — „PAR links“ ->
    „PAR links 2“, „PAR links 3“ … ``belegt``: vergebene Namen, klein
    geschrieben (``casefold``); Gross/Klein unterscheidet zwei Namen nicht.

    Endet der Name schon auf eine ABGESETZTE Zahl („PAR 3“), ist das ein
    Zaehler: es wird weitergezaehlt („PAR 4“), nicht „PAR 3 2“ angehaengt —
    das laese sich wie eine Unternummer und sortiert falsch. Klebt die Zahl
    am Wort („ZQ01424“, „PAR64“, „LED-PAR-56“), gehoert sie zur
    Typbezeichnung und bleibt stehen: „PAR64“ -> „PAR64 2“. Fuehrende Nullen
    bleiben erhalten („Spot 01“ -> „Spot 02“)."""
    treffer = _NAME_MIT_NUMMER.match(name)
    if treffer:
        stamm, ziffern = treffer.group(1), treffer.group(2)
        nummer, stellen = int(ziffern) + 1, len(ziffern)
    else:
        stamm, nummer, stellen = name, 2, 1
    while True:
        kandidat = f"{stamm} {nummer:0{stellen}d}" if stamm else str(nummer)
        if kandidat.casefold() not in belegt:
            return kandidat
        nummer += 1


def _vergib_namen(zeilen: list[PlanZeile], vorhandene) -> None:
    """IMP-3 (Entscheidung der Leitung): jedes Geraet bekommt beim Import
    einen EIGENEN Namen. Steht ein Name mehrfach in der Tabelle oder gibt es
    ihn im Patch schon, wird er nummeriert (:func:`naechster_freier_name`).
    Vorher war das nur ein Hinweis und beide Geraete hiessen gleich — in
    Auswahllisten, Gruppen und der Befehlszeile nicht zu unterscheiden.

    Zwei Durchgaenge: zuerst behaelt jeder Name, der noch frei ist, seinen
    Platz (auch ein ausdruecklich so genanntes „PAR 2“ weiter unten in der
    Tabelle), erst danach bekommen die Doppelten ihre Nummer. So benennt der
    Import nie ein Geraet um, dessen Name in der Tabelle eindeutig war."""
    belegt = {b.name.casefold() for b in vorhandene if b.name}
    doppelt: list[tuple[PlanZeile, int]] = []
    for pz in zeilen:
        pz.umbenannt = []
        if pz.status != ANLEGBAR:
            continue
        for k, g in enumerate(pz.geraete):
            schluessel = g.name.casefold()
            if schluessel in belegt:
                doppelt.append((pz, k))
            else:
                belegt.add(schluessel)
    for pz, k in doppelt:
        alt = pz.geraete[k]
        neu = naechster_freier_name(alt.name, belegt)
        belegt.add(neu.casefold())
        pz.geraete[k] = replace(alt, name=neu)
        pz.umbenannt.append((alt.name, neu))


# ── Anwenden ─────────────────────────────────────────────────────────────────

@dataclass
class Ergebnis:
    fids: list[int] = field(default_factory=list)
    zeilen: int = 0
    #: Zeilen, die NICHT angelegt wurden (offen, Ueberschneidung, Fehler).
    ausgelassen: int = 0
    fehler: list[str] = field(default_factory=list)
    #: IMP-3: Geraete, die eine Nummer bekamen, weil es den Namen schon gab.
    umbenannt: int = 0

    @property
    def geraete(self) -> int:
        return len(self.fids)


def _auto_dual_tilt(profil_id: int, modus_name: str) -> bool:
    """Wie „Geraet hinzufuegen“: ein importierter Spider mit zwei Motoren
    wird beim Patchen als Doppel-Tilt markiert."""
    try:
        from .database import fixture_db as fdb
        prof = fdb.get_fixture(profil_id)
        if prof is None:
            return False
        modus = next((m for m in prof.modes if m.name == modus_name), None)
        if modus is None:
            return False
        return bool(fdb.should_auto_mark_dual_tilt(prof, fdb.get_channels(modus.id)))
    except Exception:
        return False


def wende_an(state, plan: Plan, bibliothek: Bibliothek) -> Ergebnis:
    """Die anlegbaren Zeilen anlegen — ueber ``state.add_fixture`` wie beim
    Patchen von Hand (Render-Plan, Kopf-Gruppen, Hinweise), als EIN
    Rueckgaengig-Schritt. Doppelte Namen sind dabei schon nummeriert
    (``_vergib_namen``, gegen den JETZIGEN Patch).

    Der Plan wird vorher gegen den JETZIGEN Patch neu gerechnet: lag zwischen
    Vorschau und Anwenden eine Aenderung, wird nichts ueberschrieben.
    Vorhandene Geraete werden nie angefasst."""
    from .database.models import PatchedFixture
    from .undo import get_undo_stack

    frisch = baue_plan(plan.tabelle, bibliothek, belegung_aus_state(state),
                       plan.wahl)
    anlegbar = frisch.anlegbare()
    ergebnis = Ergebnis(ausgelassen=len(frisch.zeilen) - len(anlegbar))
    anzahl = sum(len(pz.geraete) for pz in anlegbar)
    if not anzahl:
        return ergebnis
    etikett = ("Patch-Import: 1 Gerät" if anzahl == 1
               else f"Patch-Import: {anzahl} Geräte")
    # IMP-3: EIN Neuaufbau (Render-Plan) und EIN patch_changed fuer den ganzen
    # Import statt einem je Geraet — auch beim Rueckgaengig/Wiederholen des
    # Schritts (``rahmen``). Kopf-Gruppen, Laser-Hinweis und die Einzelschritte
    # laufen unveraendert ueber add_fixture.
    sammeln = getattr(state, "patch_sammeln", None) or nullcontext
    with sammeln(), get_undo_stack().gruppe(etikett, rahmen=sammeln):
        for pz in anlegbar:
            dual = _auto_dual_tilt(pz.profil.id, pz.modus.name)
            try:
                for g in pz.geraete:
                    ergebnis.fids.append(state.add_fixture(PatchedFixture(
                        fid=state.next_fid(),
                        label=g.name,
                        fixture_profile_id=pz.profil.id,
                        mode_name=pz.modus.name,
                        universe=g.universum,
                        address=g.adresse,
                        channel_count=g.kanaele,
                        manufacturer_name=pz.profil.hersteller,
                        fixture_name=pz.profil.name,
                        fixture_type=pz.profil.typ,
                        spider_dual_tilt=dual,
                    )))
                ergebnis.zeilen += 1
                ergebnis.umbenannt += len(pz.umbenannt)
            except Exception as e:
                ergebnis.fehler.append(
                    f"Zeile {pz.zeile.nr} („{pz.name}“) ließ sich nicht "
                    f"anlegen: {e}")
    return ergebnis
