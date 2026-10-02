"""Zuordnung Dimmer -> Weiss-Segment (FM-46).

Ein Geraet mit EIGENER Weiss-Achse (mehr oder weniger ``color_w`` als
Farbkoepfe, ``weiss_ist_eigene_achse_for_channels``) und MEHREREN Dimmern
sagt in seiner Kanalliste nicht, welcher Dimmer welches Weiss-Segment dimmt.
Gemessen ueber importierte Profile: bei 26 von 71 Modi mit eigener Achse kommt
``intensity`` 2- bis 5-mal vor. Die Matrix konnte dort den Dimmer eines
Weiss-Segments nicht treiben und schrieb bewusst nichts (FM-46, Befund C).

★ **Entscheidung des Projektinhabers (02.10.):** die Zuordnung setzt ein
  MENSCH im Fixture-Editor bzw. -Generator (``FixtureChannel.segment``).
  Zur Laufzeit wird NIE geraten — ``channels_for_axis`` liest nur, was
  gespeichert ist. Ohne Eintrag oeffnen die Matrix-Pfade bei
  ``drive_intensity`` alle freien Dimmer gemeinsam (Etappe 2,
  ``app_state.weiss_rueckfall_dimmer``) — auch das waehlt nichts aus.
  Dieses Modul liefert die beiden Hilfen fuer die Eingabe:

* :func:`vorschlag_dimmer_segmente` — ein Vorschlag aus der
  Kanalreihenfolge, aber nur, wenn er EINDEUTIG ist; sonst ``{}``.
* :func:`zuordnung_fehlt` — soll der Editor den Hinweis zeigen?

Ausnahme mit Quelle statt Mensch (Etappe 3): beim QLC+-Import liefert
:func:`segmente_aus_heads` die Zuordnung aus den ``<Head>``-Gruppen der
Datei — nur wenn sie eindeutig ist, und gespeichert wie eine Handeingabe.

Reine Funktionen ohne Qt und ohne DB: Kanaele duerfen ORM-Objekte,
beliebige Objekte mit ``attribute`` oder die Kanal-Dicts der Editoren sein.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.core.attr_groups import ATTR_GROUPS

# Dieselbe Definition wie ``app_state._DIM_INTENSITY_ATTRS`` — hier aus
# derselben Quelle gebildet statt importiert, damit dieses Modul ohne den
# schweren AppState importierbar bleibt (die Editoren laden es beim Bauen).
# Ein Test haelt beide gleich (tests/test_fm46_dimmer_segment.py).
DIMMER_ATTRS = frozenset(ATTR_GROUPS["Intensity"]) - frozenset({"shutter", "strobe"})

#: Hinweistext fuer beide Editoren — EIN Wortlaut, nicht zwei.
HINWEIS_TEXT = (
    "Dieses Gerät hat eine eigene Weiß-Leiste und mehrere Dimmer. Welcher "
    "Dimmer welches Weiß-Segment dimmt, steht nicht in der Kanalliste — trage "
    "es in der Spalte „Weiß-Segment“ ein (oder „Vorschlag aus Reihenfolge“). "
    "Im Handbuch steht es meist in der DMX-Tabelle: ein Dimmer, der direkt vor "
    "oder nach einem Weiß-Kanal liegt oder im selben Abschnitt („Zone 2“, "
    "„Segment 2“) steht, gehört zu diesem Weiß. Ohne Eintrag fährt die Matrix "
    "(wenn sie die Dimmer fährt) alle freien Dimmer gemeinsam — außer denen "
    "neben einem reinen Farbteil."
)


def _attr(ch) -> str:
    if isinstance(ch, dict):
        a = ch.get("attribute")
    else:
        a = getattr(ch, "attribute", "")
    return (a or "").lower()


def segment_von(ch) -> int | None:
    """Die GESPEICHERTE Zuordnung eines Kanals — ``None`` = keine.

    Tolerant gegen jede Kanalart: ORM-Objekt (Spalte ``segment``),
    ``_AttrOverrideChannel`` (delegiert), Kanal-Dict der Editoren, Builtin-
    oder Test-Objekte ohne das Feld. Nur eine echte ganze Zahl >= 0 zaehlt:
    ``bool`` nicht (``True`` waere sonst Segment 1) und auch kein Mock-Objekt,
    dessen ``__int__`` zufaellig eine Zahl liefert — eine Zuordnung, die nie
    jemand gesetzt hat, darf nicht wirken."""
    if isinstance(ch, dict):
        v = ch.get("segment")
    else:
        try:
            v = getattr(ch, "segment", None)
        except Exception:
            return None
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if v >= 0 else None


def _mehrfache_dimmer(attrs: list[str]) -> dict[str, list[int]]:
    """``{dimmer_attr: [positionen]}`` fuer jedes MEHRFACH vorkommende
    Dimmer-Attribut. Ein einmaliger Dimmer ist geteilt und faehrt ohnehin mit
    (``channels_for_axis``) — er braucht keine Zuordnung."""
    pos: dict[str, list[int]] = {}
    for i, a in enumerate(attrs):
        if a in DIMMER_ATTRS:
            pos.setdefault(a, []).append(i)
    return {a: p for a, p in pos.items() if len(p) > 1}


def vorschlag_dimmer_segmente(channels) -> dict[int, int]:
    """Vorschlag ``{kanal_index: segment}`` (beide 0-basiert) aus der
    Kanalreihenfolge — oder ``{}``, wenn er nicht EINDEUTIG ist.

    Ein Vorschlag kommt nur zustande, wenn
    1. genau EIN Dimmer-Attribut mehrfach vorkommt,
    2. seine Zahl gleich der Zahl der ``color_w``-Kanaele ist (>= 2), und
    3. genau EINE der drei Lesarten der Reihenfolge eine vollstaendige
       Zuordnung ergibt:

       * jeder Dimmer steht **direkt vor** seinem Weiss (``[I,W,I,W]``),
       * jeder Dimmer steht **direkt nach** seinem Weiss (``[W,I,W,I]``),
       * **Bloecke gleicher Groesse**: der k-te Dimmer und das k-te Weiss
         bilden Block k, alle Bloecke haben denselben Abstand und
         ueberlappen nicht (``[I,R,G,B,W, I,R,G,B,W]``).

       Ergeben mehrere Lesarten verschiedene Zuordnungen, ist das Muster
       mehrdeutig -> ``{}``.

    ⚠️ Das ist ein VORSCHLAG fuer den Menschen im Editor, keine Laufzeitregel.
    Ob der Dimmer physisch dieses Segment dimmt, weiss nur das Handbuch bzw.
    der Test am Geraet — darum wird der Vorschlag erst wirksam, wenn er
    gespeichert ist.
    """
    attrs = [_attr(c) for c in (channels or ())]
    mehrfach = _mehrfache_dimmer(attrs)
    if len(mehrfach) != 1:
        return {}
    dimmer = next(iter(mehrfach.values()))
    weiss = [i for i, a in enumerate(attrs) if a == "color_w"]
    n = len(dimmer)
    if n < 2 or len(weiss) != n:
        return {}
    w_index = {p: k for k, p in enumerate(weiss)}

    def _nachbar(versatz: int) -> dict[int, int] | None:
        out: dict[int, int] = {}
        for d in dimmer:
            k = w_index.get(d + versatz)
            if k is None:
                return None
            out[d] = k
        return out if len(set(out.values())) == n else None

    def _bloecke() -> dict[int, int] | None:
        paare = list(zip(dimmer, weiss))
        schritt_d = {b[0] - a[0] for a, b in zip(paare, paare[1:])}
        schritt_w = {b[1] - a[1] for a, b in zip(paare, paare[1:])}
        if len(schritt_d) != 1 or schritt_d != schritt_w:
            return None
        for (d0, w0), (d1, w1) in zip(paare, paare[1:]):
            if max(d0, w0) >= min(d1, w1):
                return None
        return {d: k for k, (d, _w) in enumerate(paare)}

    lesarten = [m for m in (_nachbar(+1), _nachbar(-1), _bloecke()) if m]
    verschieden = {tuple(sorted(m.items())) for m in lesarten}
    if len(verschieden) != 1:
        return {}
    return dict(lesarten[0])


def segmente_aus_heads(channels, heads) -> dict[int, int]:
    """Zuordnung ``{kanal_index: segment}`` aus den Kopf-Gruppen einer QLC+-
    Datei (``<Mode><Head><Channel>n</Channel>…</Head>``) — FM-46, Etappe 3.

    ``heads`` ist eine Liste von Kanal-Index-Listen (0-basiert, Positionen in
    ``channels``); die Importer rechnen die ``<Head>``-Nummern vorher auf
    Positionen um. Anders als :func:`vorschlag_dimmer_segmente` ist das kein
    Raten aus der Reihenfolge: der Hersteller bzw. der Profil-Autor hat den
    Dimmer und das Weiss in DENSELBEN Kopf gelegt. Trotzdem gilt „nie raten“ —
    gesetzt wird nur, was eindeutig ist:

    * nur fuer Modi mit EIGENER Weiss-Achse (:func:`weiss_eigen`) und einem
      mehrfach vorkommenden Dimmer-Attribut — sonst ``{}``;
    * Koepfe ohne ``color_w`` zaehlen nicht (Pixel-Koepfe, Motor-Koepfe);
    * ein Kopf mit genau EINEM Dimmer-Kanal und genau EINEM ``color_w``
      ordnet diesen Dimmer dem Segment k zu, k = Rang dieses ``color_w``
      unter allen ``color_w`` des Modus;
    * mehrdeutig -> fuer die betroffenen Dimmer nichts: mehrere Dimmer oder
      mehrere Weiss in einem Kopf, ein Dimmer in mehreren Weiss-Koepfen, ein
      Weiss-Segment, das mehrere Dimmer bekaemen;
    * eine VORHANDENE Zuordnung bleibt: weder wird ein Dimmer mit Segment
      ueberschrieben noch ein schon vergebenes Segment ein zweites Mal
      vergeben (Re-Import, Nachtragen in einer bestehenden Bibliothek).
    """
    chans = list(channels or ())
    attrs = [_attr(c) for c in chans]
    mehrfach = _mehrfache_dimmer(attrs)
    if not mehrfach or "color_w" not in attrs or not weiss_eigen(chans):
        return {}
    zuordbar = {i for pos in mehrfach.values() for i in pos}
    weiss = [i for i, a in enumerate(attrs) if a == "color_w"]
    w_rang = {i: k for k, i in enumerate(weiss)}

    kandidat: dict[int, int] = {}
    in_koepfen: dict[int, int] = {}
    for head in heads or ():
        idx = {i for i in head
               if isinstance(i, int) and not isinstance(i, bool)
               and 0 <= i < len(chans)}
        ws = [i for i in idx if i in w_rang]
        if not ws:
            continue
        ds = [i for i in idx if attrs[i] in DIMMER_ATTRS]
        for d in ds:
            in_koepfen[d] = in_koepfen.get(d, 0) + 1
        if len(ws) == 1 and len(ds) == 1 and ds[0] in zuordbar:
            kandidat[ds[0]] = w_rang[ws[0]]

    out = {d: s for d, s in kandidat.items() if in_koepfen.get(d) == 1}
    anzahl: dict[int, int] = {}
    for s in out.values():
        anzahl[s] = anzahl.get(s, 0) + 1
    belegt = {segment_von(chans[i]) for i in zuordbar} - {None}
    return {d: s for d, s in sorted(out.items())
            if anzahl[s] == 1 and segment_von(chans[d]) is None
            and s not in belegt}


def weiss_eigen(channels) -> bool:
    """Hat dieser Kanalsatz eine EIGENE Weiss-Achse? Dieselbe Regel wie
    ``app_state.weiss_ist_eigene_achse_for_channels`` (ENG-25) — dorthin
    delegiert, nicht nachgebaut. Kanal-Dicts werden dafuer in leichte
    Objekte mit ``attribute`` verpackt."""
    from src.core.app_state import weiss_ist_eigene_achse_for_channels
    chans = [SimpleNamespace(attribute=_attr(c)) for c in (channels or ())]
    try:
        return bool(weiss_ist_eigene_achse_for_channels(chans, None))
    except Exception:
        return False


def zuordnung_fehlt(channels) -> bool:
    """Soll der Editor den Hinweis zeigen? Ja genau dann, wenn das Geraet eine
    eigene Weiss-Achse hat, ein Dimmer-Attribut mehrfach vorkommt und KEINER
    dieser Dimmer eine Zuordnung traegt."""
    chans = list(channels or ())
    attrs = [_attr(c) for c in chans]
    mehrfach = _mehrfache_dimmer(attrs)
    if not mehrfach or "color_w" not in attrs:
        return False
    if not weiss_eigen(chans):
        return False
    for positionen in mehrfach.values():
        if any(segment_von(chans[i]) is not None for i in positionen):
            return False
    return True


def ist_dimmer(attribute) -> bool:
    """Darf dieser Kanal eine Segment-Zuordnung tragen?"""
    return (attribute or "").lower() in DIMMER_ATTRS


def zuordnung_probleme(channels) -> list[str]:
    """Was an einer VORHANDENEN Zuordnung nicht stimmt — als lesbare Saetze
    fuer beide Editoren und ``validate_model``. Leer, wenn alles passt oder es
    gar keine Zuordnung gibt (das Fehlen meldet :func:`zuordnung_fehlt`).

    * ein Segment mehreren Dimmern zugeordnet — dann faehrt KEINER davon mit
      (``channels_for_axis`` raet nicht zwischen ihnen);
    * ein Segment, das es im Modus nicht gibt — wirkt nie;
    * ein mehrfacher Dimmer ohne Segment, waehrend andere eins haben —
      vielleicht gewollt (ein Dimmer, der kein Weiss dimmt), oft vergessen.

    Kanalnummern 1-basiert wie in der Tabelle."""
    chans = list(channels or ())
    attrs = [_attr(c) for c in chans]
    mehrfach = _mehrfache_dimmer(attrs)
    if not mehrfach or not weiss_eigen(chans):
        return []
    n_weiss = attrs.count("color_w")
    out: list[str] = []
    for positionen in mehrfach.values():
        segs = {i: segment_von(chans[i]) for i in positionen}
        if all(v is None for v in segs.values()):
            continue
        vergeben: dict[int, list[int]] = {}
        for i, seg in segs.items():
            if seg is not None:
                vergeben.setdefault(seg, []).append(i)
        for seg, idx in sorted(vergeben.items()):
            if seg >= n_weiss:
                for i in idx:
                    out.append(f"Kanal {i + 1}: Weiß-Segment {seg + 1} gibt es "
                               f"nicht ({n_weiss} Weiß-Kanäle) — die "
                               f"Zuordnung wirkt nicht.")
            elif len(idx) > 1:
                kanaele = ", ".join(str(i + 1) for i in idx)
                out.append(f"Weiß-Segment {seg + 1} ist mehrfach vergeben "
                           f"(Kanal {kanaele}) — die Zuordnung wirkt dort "
                           f"nicht.")
        for i, seg in segs.items():
            if seg is None:
                out.append(f"Dimmer auf Kanal {i + 1} hat kein Weiß-Segment — "
                           f"gewollt?")
    return out


def _segment_setzen(ch, wert) -> None:
    if isinstance(ch, dict):
        ch["segment"] = wert
    else:
        ch.segment = wert


class SegmentZiele:
    """Haelt die Zuordnung eines Editors an den Weiss-KANAELEN fest, nicht an
    ihrer Nummer (FM-46, Review).

    ★ Warum: gespeichert wird ``segment`` als Index ins ``color_w``-Vorkommen.
    Loescht, verschiebt oder ueberschreibt man im Editor einen Weiss-Kanal,
    zeigte derselbe Index stumm auf ein ANDERES Segment — der Dimmer dimmte
    danach das falsche Weiss. Diese Klasse merkt sich je Kanal das Weiss-
    OBJEKT, auf das er zeigt, und rechnet nach jeder Aenderung die Nummer neu:

    * Weiss-Kanal verschoben  -> neue Nummer;
    * Weiss-Kanal geloescht   -> ``None`` (keine Zuordnung);
    * Attribut eines Weiss-Kanals voruebergehend anders (Tippen in der
      editierbaren Combo des Generators) -> ``None``, und wieder ``color_w``
      -> die alte Zuordnung kommt zurueck.

    Kanaele duerfen Dicts (Editor) oder Objekte (``GenChannel``) sein; beide
    Listen halten ihre Eintraege beim Verschieben als dieselben Objekte."""

    def __init__(self):
        self._ziele: dict[int, tuple] = {}

    @staticmethod
    def _weiss(channels) -> list:
        return [c for c in channels if _attr(c) == "color_w"]

    def merken(self, channels) -> None:
        """Alle Ziele aus den aktuellen Nummern neu aufbauen (nach Laden)."""
        self._ziele = {}
        for c in channels:
            self.setzen(channels, c)

    def setzen(self, channels, ch) -> None:
        """Das Ziel EINES Kanals aus seiner aktuellen Nummer uebernehmen
        (nach einer Eingabe in der Spalte oder dem Vorschlag)."""
        seg = segment_von(ch)
        weiss = self._weiss(channels)
        if seg is None or seg >= len(weiss):
            self._ziele.pop(id(ch), None)
        else:
            self._ziele[id(ch)] = (ch, weiss[seg])

    def vergessen(self, ch) -> None:
        self._ziele.pop(id(ch), None)

    def nachziehen(self, channels) -> None:
        """Nach Loeschen/Verschieben/Attributwechsel die Nummern neu setzen."""
        da = {id(c) for c in channels}
        pos = {id(w): k for k, w in enumerate(self._weiss(channels))}
        for key, (ch, w) in list(self._ziele.items()):
            if id(ch) not in da:
                del self._ziele[key]
            elif id(w) not in da:
                _segment_setzen(ch, None)
                del self._ziele[key]
            else:
                _segment_setzen(ch, pos.get(id(w)))


def vorschlag_abweichungen(channels, vorschlag: dict) -> list[int]:
    """Kanal-Indizes, an denen der Vorschlag eine VORHANDENE Handzuordnung
    aendern wuerde (FM-46, Review: nicht ungefragt ueberschreiben)."""
    chans = list(channels or ())
    out = []
    for i, seg in sorted(vorschlag.items()):
        alt = segment_von(chans[i]) if 0 <= i < len(chans) else None
        if alt is not None and alt != seg:
            out.append(i)
    return out


def hinweis_fuer(channels) -> str:
    """Der Hinweis, den beide Editoren unter der Geometrie-Zeile zeigen:
    :data:`HINWEIS_TEXT`, wenn die Zuordnung fehlt, sonst die Probleme einer
    vorhandenen Zuordnung (:func:`zuordnung_probleme`), sonst ``""``."""
    if zuordnung_fehlt(channels):
        return HINWEIS_TEXT
    return "\n".join(zuordnung_probleme(channels))
