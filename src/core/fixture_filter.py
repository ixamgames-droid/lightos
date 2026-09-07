"""UI-53 — EIN Einstieg fuer die Frage „wen darf dieses Widget anfassen?".

Vorher beantworteten VIER Fassungen dieselbe Frage, und jede Kachelreihe des
Programmers waehlte sich ihre Fassung selbst aus (``_fixtures_with_attr``,
``_fixtures_with_any_attr``, ``_range_compatible_fixtures`` und eine vierte,
INLINE in der Orientierungsleiste). Das ist kein Lesbarkeitsproblem gewesen:
gemessen stand die RESET-Reihe auf der falschen Fassung — sie filterte nur nach
Kanal-Existenz, obwohl ihr Knopf den Bereichs-Mittelwert der VORLAGE literal auf
alle Geraete schreibt. An einer ``CONTIMH`` (reset 0–255 = „Neustart") neben
einem ``Inno Scan LED`` bedeutete derselbe Wert 127 am zweiten Geraet
„Disable blackout while Gobo Change"; bibliotheksweit landen 82,2 % aller
448·447/2 = 100128 Modus-Paare mit ``reset``-Kanal in einem FREMDEN Bereich.

★ Der Parameter dieses Einstiegs benennt deshalb die Art der **NUTZLAST**, nicht
die Filter-Technik. „Range-Regel oder Kanal-Existenz?" ist eine Frage ueber die
Implementierung und war genau deshalb dreimal falsch zu beantworten; „schreibe
ich einen Literalwert aus einem Vorlagen-Bereich oder einen absoluten Wert?" ist
eine Frage ueber die Kachel, die ihr Bauer beantworten KANN. Die Zuordnung
Nutzlast -> Regel steht danach nur noch hier.

★ Warum in ``src/core`` und nicht in der View: die Frage ist keine
UI-Angelegenheit, und ein zweiter Aufrufer ausserhalb von ``_add_quick_select``
(die Farb-Synchronregler) stellt sie ebenso. Ein Einstieg, der nur eine Methode
bedient, laesst genau die Aufrufer draussen, die spaeter falsch abbiegen.
"""

from __future__ import annotations

from enum import Enum

from src.core.app_state import (attr_head_count_for_channels,
                                get_channels_for_patched)


class Nutzlast(Enum):
    """Was schreibt die Kachelreihe auf die Geraete?

    Es gibt genau drei Antworten, und jede zieht eine andere Geraete-Regel nach
    sich. Der Bauer einer neuen Reihe muss sich fuer eine entscheiden — es gibt
    keinen Vorgabewert (:func:`fixtures_fuer_nutzlast` verlangt ihn positionell).
    """

    #: (i) Ein LITERALWERT, der aus einem BEREICH der Vorlage stammt
    #: (Shutter/Strobe, Gobo-Slot, Farbrad-Slot, Reset-Mittelwert). Derselbe
    #: DMX-Wert bedeutet an einem Geraet mit anderem Bereichs-Layout etwas
    #: ANDERES -> nur Geraete mit gleichem Layout (UI-07).
    LITERAL_AUS_VORLAGEN_BEREICH = "literal_aus_vorlagen_bereich"

    #: (ii) Ein ABSOLUTER Wert auf EINEM Kanal (Pan/Tilt-Speed, ein
    #: Farb-Synchronregler). 0..255 heisst dort ueberall dasselbe -> es genuegt,
    #: dass das Geraet den Kanal hat (FM-27).
    ABSOLUTWERT_EIN_KANAL = "absolutwert_ein_kanal"

    #: (iii) ABSOLUTE Werte auf einer KANALMENGE (RGB-Kacheln schreiben
    #: ``color_r/g/b/w`` in einem Klick; die Orientierungsleiste gilt fuer
    #: Pan ODER Tilt). Wer MINDESTENS EINEN der Kanaele hat, gehoert dazu
    #: (FM-34); die uebrigen Schluessel werden beim Anwenden je Geraet noch
    #: einmal geprueft (``_apply_payload_on``).
    ABSOLUTWERTE_KANALMENGE = "absolutwerte_kanalmenge"


def range_signature(ch) -> tuple:
    """Stabile Signatur des Bereichs-Layouts eines Kanals (Grenzen + kind).

    Zwei Kanaele sind range-kompatibel <=> gleiche Signatur. Range-lose Kanaele
    haben die leere Signatur und sind untereinander kompatibel."""
    rs = getattr(ch, "ranges", None) or []
    return tuple(sorted(
        (int(getattr(r, "range_from", 0)), int(getattr(r, "range_to", 0)),
         (getattr(r, "kind", "") or ""))
        for r in rs))


def attr_head_count(fixture, attr: str, kanaele=None) -> int:
    """Kopfzahl dieses Geraets fuer dieses Attribut — ``0`` = hat es nicht.

    Eine Zeile Kapselung, damit **jeder** Bauweg dieselbe Antwort bekommt. Der
    ``except``-Rueckfall auf ``1`` ist Absicht: „nicht messbar" darf ein Geraet
    nicht aus dem Bestandspfad werfen.

    ``kanaele`` ist der Kanal-Zugriff (``fixture -> Kanalliste``); ohne Angabe
    :func:`~src.core.app_state.get_channels_for_patched`."""
    hole = kanaele or get_channels_for_patched
    try:
        return int(attr_head_count_for_channels(fixture, hole(fixture), attr))
    except Exception:
        return 1


def hat_kanal(fixture, attr: str, kanaele=None) -> bool:
    """Hat dieses Geraet diesen Kanal wirklich (mindestens ein Kopf)?"""
    return attr_head_count(fixture, attr, kanaele) >= 1


def fixtures_fuer_nutzlast(nutzlast: Nutzlast, fixtures, ziel,
                           kanaele=None) -> list:
    """Die Geraete, die diese Nutzlast wirklich ausfuehren koennen.

    :param nutzlast: eine der drei :class:`Nutzlast`-Antworten. Positionell und
        ohne Vorgabewert — eine neue Kachelreihe laesst sich damit nicht bauen,
        ohne die Frage zu beantworten.
    :param fixtures: die Auswahl, aus der gefiltert wird.
    :param ziel: WAS geschrieben wird — je nach ``nutzlast``:
        (i) der VORLAGEN-KANAL (traegt die Bereiche, aus denen der Literalwert
        stammt), (ii) der Attributname als ``str``, (iii) die Attributnamen als
        Folge von ``str``.
    :param kanaele: optionaler Kanal-Zugriff (``fixture -> Kanalliste``).

    Ein ``ziel``, das nicht zur Nutzlast passt, ist ein :class:`ValueError` und
    kein stiller Sonderfall: die vier alten Fassungen unterschieden sich genau
    darin, was sie als ``ziel`` akzeptierten, und ein Vertippen fiel niemandem
    auf, weil jede Fassung mit jedem Argument IRGENDEINE Liste zurueckgab."""
    if not isinstance(nutzlast, Nutzlast):
        raise ValueError(
            f"nutzlast muss eine Nutzlast sein, nicht {nutzlast!r} — die Art "
            f"der Nutzlast entscheidet ueber die Geraete-Regel")
    fixtures = list(fixtures)

    if nutzlast is Nutzlast.LITERAL_AUS_VORLAGEN_BEREICH:
        attr = getattr(ziel, "attribute", None)
        if attr is None:
            raise ValueError(
                "LITERAL_AUS_VORLAGEN_BEREICH braucht den VORLAGEN-KANAL als "
                f"ziel (er traegt die Bereiche), bekommen: {ziel!r}")
        return _range_kompatible(fixtures, ziel, attr, kanaele)

    if nutzlast is Nutzlast.ABSOLUTWERT_EIN_KANAL:
        if not isinstance(ziel, str) or not ziel:
            raise ValueError(
                "ABSOLUTWERT_EIN_KANAL braucht GENAU EIN Attribut als str, "
                f"bekommen: {ziel!r}")
        attrs = (ziel,)
    else:                       # ABSOLUTWERTE_KANALMENGE
        if isinstance(ziel, str) or ziel is None:
            raise ValueError(
                "ABSOLUTWERTE_KANALMENGE braucht eine FOLGE von Attributen "
                f"(ein einzelner Kanal ist ABSOLUTWERT_EIN_KANAL), "
                f"bekommen: {ziel!r}")
        attrs = tuple(ziel)
        if not attrs:
            raise ValueError("ABSOLUTWERTE_KANALMENGE mit leerer Kanalmenge "
                             "wuerde jedes Geraet wegwerfen")
    # (ii) ist (iii) mit einer einelementigen Menge — EINE Stelle, die
    # „hat den Kanal" beantwortet, damit die beiden nie auseinanderlaufen.
    return [f for f in fixtures
            if any(hat_kanal(f, a, kanaele) for a in attrs)]


def _range_kompatible(fixtures, template_channel, attr: str, kanaele) -> list:
    """UI-07: nur Geraete, deren Kanal fuer dieses Attribut DASSELBE
    Bereichs-Layout hat wie die Vorlage.

    Eine range-basierte Reihe backt die DMX-Werte aus den Vorlagen-Bereichen
    fest ein und schreibt denselben Literal-Wert auf ALLE Geraete
    (``_set_on_fixtures``); ein Geraet mit abweichendem Layout bekaeme so den
    Vorlagen-Wert in einen semantisch fremden Bereich. Die Vorlage selbst (und
    jedes Geraet mit gleichem Layout) bleibt erhalten.

    Strikt staerker als die Kanal-Existenz: fehlt der Kanal ganz, ist ``ch is
    None`` — die Regel deckt FM-34 also mit ab."""
    hole = kanaele or get_channels_for_patched
    sig = range_signature(template_channel)
    out = []
    for f in fixtures:
        ch = next((c for c in hole(f)
                   if getattr(c, "attribute", None) == attr), None)
        if ch is not None and range_signature(ch) == sig:
            out.append(f)
    return out
