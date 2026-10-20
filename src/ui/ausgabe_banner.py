"""OUT-67: Ausgabe-Ausfall laut melden, Probenmodus sichtbar machen.

**Was es schon gab — und was fehlte.** Seit HW-5b/OUT-51/OUT-56 sagt die
Statusleiste die Wahrheit: ``_lbl_enttec`` kennt die vier Geraetezustaende,
``_lbl_universe`` (Regel in ``ausgabe_label.py``) faerbt rot, sobald ein Weg
nicht sendet. Nur steht das unten links in kleiner Schrift — und im Kiosk-Modus
ist die Statusleiste ausgeblendet, dort stand also **gar nichts**. Ein Ausfall
mitten in der Show, den man erst sieht, wenn man unten links nachliest, ist
nicht gemeldet.

Dieses Modul rechnet nichts neu. Es nimmt dieselbe Quelle
(``OutputManager.ausgabe_status()``, in der ``sende_probleme()`` und der echte
Portstatus schon zusammengefuehrt sind) und macht daraus ein Banner oben im
Hauptfenster. Seit VCB-47 UEBERLAGERT es den oberen Rand des Inhaltsbereichs,
statt den Inhalt nach unten zu schieben — seit UI-103 aber nie die Unterreiter
einer Sektion und nie die Bedienleiste der Virtual Console (siehe
:class:`AusgabeBanner`):

* ``ART_STOERUNG`` — „Ausgabe gestört: <Weg> — <Grund>". Kommt sofort, geht von
  selbst, sobald die Ausgabe :data:`HALTE_S` lang wieder laeuft.
* ``ART_PROBE`` — „Probenmodus — es wird kein DMX gesendet", wenn kein einziger
  Ausgang eingerichtet ist. Dezent, im Kiosk-Modus nur als schmale Zeile.

**VCB-47, Nachtrag 2: einklappbar, aber nie weg.** Das ueberlagernde Banner
verdeckt waehrend einer Stoerung dauerhaft die oberste Zeile der Ansicht (bei
1024x600 die ganze Werkzeugleiste der Virtual Console). Beide Banner lassen
sich deshalb auf einen kleinen Chip einklappen (:class:`AusgabeChip`) — die
Stoerung in Rot, der Probenhinweis gedeckt. Ein voelliges Verschwinden gibt es
nicht, solange der Zustand anliegt. Eine NEUE Stoerung klappt das Banner von
selbst wieder auf; was „neu" heisst, steht an :data:`NACHSICHT_S`. Nichts davon
wird gespeichert: nach einem Neustart ist jedes Banner wieder voll da.

Aufbau wie ``ausgabe_label.py``: die Regel (:func:`ausgabe_banner`) und die
Drossel (:class:`BannerDrossel`) sind reine Rechnung ohne Qt und ohne Uhr; nur
:class:`AusgabeBanner`/:class:`AusgabeBannerSteuerung` fassen Widgets an.

⚠️ Bewusst NICHT im Banner: Tick-/Modifier-Stoerungen (kein Ausgang faellt aus,
die Statusleiste nennt sie weiter) und Universen ohne Ausgang neben sendenden
(OUT-56, ebenfalls Statusleiste) — das Banner bleibt fuer „es kommt nichts an".
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

ART_KEIN = ""
ART_STOERUNG = "stoerung"
ART_PROBE = "probe"

#: So lange muss ein ruhigerer Zustand anhalten, bevor das Banner ihm folgt
#: (Sekunden). Zwei Abfragen des 2-s-Hardware-Takts: ein Wackelkontakt, der
#: zwischen „sendet" und „tot" pendelt, laesst das Banner stehen statt blinken.
HALTE_S = 4.0

#: VCB-47: Wie lange eine eingeklappte Stoerung „dieselbe" bleibt, nachdem sie
#: zuletzt als Ausfall gesehen wurde (Sekunden). Eingeklappt bleibt die Meldung
#: nur fuer genau die Ausfaelle, die der Bediener vor sich hatte — gleicher
#: Ausgang (Universum, Weg, Ziel) UND gleicher Grund. Alles andere klappt auf:
#: ein weiterer oder anderer Ausgang, ein anderer Grund, oder derselbe Ausfall,
#: der laenger als diese Frist weg war.
#:
#: Warum 10 s: Ein Wackelkontakt darf das Banner nicht im Sekundentakt ueber die
#: Tasten werfen. Die laengste Runde „weg und wieder da", die LightOS an EINEM
#: Wackler ueberhaupt sehen kann, ist ein Wiederverbindungsversuch des Adapters
#: (Enttec alle 3 s, uDMX alle 2 s) plus eine Abfrage des 2-s-Hardware-Takts,
#: also 5 s. Die Frist deckt zwei solche Runden. Sie liegt damit ueber
#: :data:`HALTE_S` (bis dahin ist die Meldung ohnehin noch nicht verschwunden)
#: und laesst Banner samt Chip hoechstens 6 s lang weg sein, bevor die
#: Rueckkehr als neue Stoerung zaehlt. Im Zweifel wird aufgeklappt.
NACHSICHT_S = 10.0

#: Schluessel fuer ``diagnose_log.merke`` (Sitzungs-Log + Diagnosepaket).
LOG_SCHLUESSEL = "ausgabe-banner"
#: Eigener Schluessel fuer Ein-/Ausklappen — ``merke`` schreibt je Schluessel
#: nur Aenderungen; im selben Schluessel wuerde jede Klappbewegung den
#: Stoerungstext erneut ins Log druecken.
LOG_SCHLUESSEL_ANSICHT = "ausgabe-banner-ansicht"

TEXT_CHIP_STOERUNG = "⚠ Ausgabe gestört ▾"
TEXT_CHIP_PROBE = "Probenmodus ▾"
TEXT_EINKLAPPEN = "▴ einklappen"

TEXT_PROBE = "Probenmodus — es wird kein DMX gesendet"


@dataclass(frozen=True)
class BannerZustand:
    art: str = ART_KEIN
    text: str = ""
    tooltip: str = ""
    klein: bool = False     # schmale Zeile (Probenhinweis im Kiosk-Modus)


KEIN_BANNER = BannerZustand()


def _weg_name(w) -> str:
    name = f"U{w.get('universum')} {w.get('weg')}"
    ziel = str(w.get("ziel") or "")
    return f"{name} ({ziel})" if ziel else name


def _grund(w) -> str:
    problem = str(w.get("problem") or "")
    if problem:
        return problem
    if w.get("weg") == "Enttec":
        return "Adapter nicht verbunden (USB-Kabel/Port prüfen)"
    if w.get("weg") == "uDMX":                       # OUT-68
        return "Adapter nicht verbunden (USB-Kabel prüfen)"
    return "es wird nichts gesendet"


def ausgabe_banner(wege, kiosk: bool = False,
                   probe_aus: bool = False) -> BannerZustand:
    """Was das Banner JETZT zeigen sollte (ungedrosselt).

    ``wege`` — ``OutputManager.ausgabe_status()``. ``verbunden is False`` ist
    ein Ausfall; ``None`` (UDP weiss es nicht, Port verbindet gerade) ist
    keiner. ``probe_aus`` — den Probenhinweis ganz weglassen; ein Ausfall
    laesst sich nie weglassen. (Die Steuerung nutzt das seit VCB-47 nicht
    mehr: sie klappt den Hinweis auf einen Chip ein, statt ihn zu streichen.)
    """
    wege = list(wege or [])
    kaputt = [w for w in wege if w.get("verbunden") is False]
    if kaputt:
        erster = kaputt[0]
        text = f"Ausgabe gestört: {_weg_name(erster)} — {_grund(erster)}"
        if len(kaputt) > 1:
            text += f"  (+{len(kaputt) - 1} weitere)"
        zeilen = [f"{_weg_name(w)}: {_grund(w)}" for w in kaputt]
        zeilen += ["", "Verschwindet von selbst, sobald die Ausgabe wieder läuft.",
                   "„▴ einklappen“ (rechts im Balken, per Tastatur die "
                   "Eingabetaste) verkleinert die Meldung zu einem roten "
                   "Chip. Bei einer neuen Störung klappt sie von selbst "
                   "wieder auf."]
        return BannerZustand(ART_STOERUNG, text, "\n".join(zeilen))
    if not wege and not probe_aus:
        return BannerZustand(
            ART_PROBE, TEXT_PROBE,
            "Kein Universum hat einen Ausgang — alles wird nur gerechnet.\n"
            "Ausgänge: Output-Einstellungen. Ein Klick klappt den Hinweis "
            "zu einem kleinen Chip ein; ein Klick auf den Chip holt ihn "
            "zurück.",
            klein=bool(kiosk))
    return KEIN_BANNER


def stoer_schluessel(wege) -> frozenset:
    """Woran eine Stoerung wiedererkannt wird: je ausgefallenem Ausgang
    ``(Universum, Weg, Ziel, Grund)``. Siehe :data:`NACHSICHT_S`."""
    return frozenset(
        (w.get("universum"), w.get("weg"), str(w.get("ziel") or ""), _grund(w))
        for w in (wege or []) if w.get("verbunden") is False)


class BannerDrossel:
    """Kein Flackern: lauter wird es sofort, leiser erst nach :data:`HALTE_S`.

    Ein Ausfall erscheint mit der ersten Abfrage, die ihn sieht (die Schwelle
    gegen einzelne Hickups sitzt schon im OutputManager). Jeder Wechsel WEG vom
    gezeigten Zustand — Erholung, aber auch „ploetzlich keine Ausgaenge", wie
    es beim Show-Laden fuer einen Moment vorkommt — muss erst ``HALTE_S`` lang
    ununterbrochen anliegen.
    """

    def __init__(self, halte_s: float = HALTE_S):
        self._halte = float(halte_s)
        self._aktuell = KEIN_BANNER
        self._wartet_art = None
        self._wartet_seit = 0.0

    @property
    def aktuell(self) -> BannerZustand:
        return self._aktuell

    def setze(self, zustand: BannerZustand) -> BannerZustand:
        """Ohne Wartezeit uebernehmen (Klick des Bedieners)."""
        self._aktuell = zustand
        self._wartet_art = None
        return zustand

    def schritt(self, neu: BannerZustand, jetzt: float) -> BannerZustand:
        if neu.art == ART_STOERUNG or neu.art == self._aktuell.art:
            return self.setze(neu)          # sofort; Text darf sich aendern
        if self._wartet_art != neu.art:
            self._wartet_art = neu.art
            self._wartet_seit = jetzt
        if jetzt - self._wartet_seit >= self._halte:
            return self.setze(neu)
        return self._aktuell


# ── Qt ───────────────────────────────────────────────────────────────────────
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal    # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter  # noqa: E402
from PySide6.QtWidgets import QLabel, QTabWidget                # noqa: E402

# Je Darstellung: (Stylesheet-Rumpf ohne padding, Polster oben/unten, Polster
# links, Schriftgroesse des Einklapp-Knopfs in px, Farbe des Knopfs).
_STIL = {
    ART_STOERUNG: ("background:#8a1414; color:#ffffff; font-weight:bold;"
                   " font-size:13px; border-bottom:1px solid #ff4444;",
                   5, 12, 11, "#ffffff"),
    ART_PROBE: ("background:#26231a; color:#c9b46a; font-size:11px;"
                " border-bottom:1px solid #4a4326;", 2, 12, 10, "#c9b46a"),
}
_STIL_KLEIN = ("background:#1c1b17; color:#8f8458; font-size:9px;",
               0, 8, 8, "#8f8458")

_STIL_CHIP = {
    ART_STOERUNG: ("QLabel#ausgabeChip { background:#c81e1e; color:#ffffff;"
                   " font-weight:bold; font-size:11px; padding:2px 8px;"
                   " border:1px solid #ff8a8a; border-radius:4px; }"
                   " QLabel#ausgabeChip:focus { border:2px solid #ffffff;"
                   " padding:1px 7px; }"),
    ART_PROBE: ("QLabel#ausgabeChip { background:#26231a; color:#c9b46a;"
                " font-size:10px; padding:2px 8px;"
                " border:1px solid #4a4326; border-radius:4px; }"
                " QLabel#ausgabeChip:focus { border:2px solid #c9b46a;"
                " padding:1px 7px; }"),
}

_ANKER_EREIGNISSE = (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show)
_PLATZ_EREIGNISSE = _ANKER_EREIGNISSE + (QEvent.Type.Hide,)
_REITER_EREIGNISSE = _PLATZ_EREIGNISSE + (QEvent.Type.LayoutRequest,)
# Bewusst OHNE Leertaste: sie ist im Hauptfenster das Kuerzel fuer „GO“ und
# muss das auch bleiben, wenn Banner oder Chip gerade den Fokus haben.
_KLAPP_TASTEN = (Qt.Key.Key_Return, Qt.Key.Key_Enter)

#: Abstand des Chips zum Rand seines Platzes (px).
CHIP_RAND = 4

#: UI-103: Abstand des Banners zum letzten Unterreiter (px).
REITER_LUECKE = 12


def _unterreiter(anker, eltern):
    """UI-103: die Unterreiter-Zeile der gezeigten Ansicht — oder ``None``.

    Fast jede Sektion des Hauptfensters ist ein ``QTabWidget`` mit Reitern
    oben (Attribute/Snapshots/…, Output/DMX Monitor/MIDI/Musik, …). Diese
    Reiter sind Navigation: Banner und Chip duerfen sie nie verdecken.

    Rueckgabe ``(zeile, belegt_bis, frei_bis)`` in Koordinaten von ``eltern``:
    ``zeile`` ist die ganze Reiterzeile ueber die Breite des Inhaltsbereichs,
    ``belegt_bis`` die x-Koordinate hinter dem letzten Reiter (laufen die
    Reiter ueber, mit Pfeilknoepfen: das Ende der Leiste), ``frei_bis`` das
    Ende des freien Felds rechts davon (vor einem etwaigen Eck-Widget).
    """
    try:
        ansicht = getattr(anker, "currentWidget", lambda: None)()
        if (not isinstance(ansicht, QTabWidget) or eltern is None
                or ansicht.tabPosition() != QTabWidget.TabPosition.North):
            return None
        leiste = ansicht.tabBar()
        if (leiste is None or not leiste.isVisibleTo(eltern)
                or leiste.height() <= 0 or leiste.count() <= 0):
            return None
        bereich_links = anker.mapTo(eltern, QPoint(0, 0)).x()
        lo = leiste.mapTo(eltern, QPoint(0, 0))
        zeile = QRect(bereich_links, lo.y(), anker.width(), leiste.height())
        # Passen die Reiter nicht, ist die Leiste so breit wie moeglich und
        # traegt Pfeilknoepfe — dann gilt sie ganz als belegt.
        belegt_bis = lo.x() + min(leiste.sizeHint().width(), leiste.width())
        frei_bis = zeile.left() + zeile.width()
        ecke = ansicht.cornerWidget(Qt.Corner.TopRightCorner)
        if ecke is not None and ecke.isVisibleTo(eltern):
            frei_bis = min(frei_bis, ecke.mapTo(eltern, QPoint(0, 0)).x())
        return zeile, belegt_bis, frei_bis
    except Exception:
        return None


def _trenne_wechsel(anker, slot) -> None:
    wechsel = getattr(anker, "currentChanged", None)
    if wechsel is not None:
        try:
            wechsel.disconnect(slot)
        except (RuntimeError, TypeError):
            pass


def _hat_fokus(w) -> bool:
    """Ist ``w`` das Fokus-Kind seines Fensters (auch wenn dieses gerade nicht
    das aktive Fenster ist)?"""
    fenster = w.window()
    return fenster is not None and fenster.focusWidget() is w


def _verstecke(w) -> None:
    """Verstecken, ohne dass der Fokus weiterwandert. Qt gibt den Fokus eines
    verschwindenden Widgets sonst an das naechste in der Tab-Kette — die
    naechste Eingabe- oder Leertaste traefe dann irgendeinen Knopf."""
    if w.isHidden():
        return
    if _hat_fokus(w):
        w.clearFocus()
    w.hide()


def _hinweis_platz(anker, eltern):
    """Das Widget, das die gezeigte Ansicht fuer Banner und Chip freigibt —
    oder ``None``.

    Eine Ansicht ohne Unterreiter (Virtual Console) nennt mit
    ``ausgabe_chip_platz()`` eine Flaeche ohne Bedienfunktion (VC: die Zeile
    „Aktiver Effekt“ zwischen Werkzeugleiste und Konsole). Seit UI-103 legen
    sich dort Chip UND Banner hin — oben am Stapel lagen sonst die
    Bank-Blaetterknoepfe und die Beschriftungen der VC-Werkzeugleiste."""
    ansicht = getattr(anker, "currentWidget", lambda: None)()
    frage = getattr(ansicht, "ausgabe_chip_platz", None)
    if not callable(frage):
        return None
    try:
        platz = frage()
        if (platz is not None and eltern is not None
                and eltern.isAncestorOf(platz)
                and platz.isVisibleTo(eltern)
                and platz.width() > 0 and platz.height() > 0):
            return platz
    except Exception:
        pass
    return None


class _FolgtAnsicht:
    """UI-103: der Unterreiter-Leiste und dem freigegebenen Platz der
    gezeigten Ansicht folgen.

    Kommen Reiter hinzu oder waechst die Schrift, aendert sich die Breite der
    Reiter, ohne dass der Inhaltsbereich (``anker``) ein Ereignis bekommt.
    Beobachtet werden deshalb auch die Ansicht (``LayoutRequest``, wenn die
    Leiste neu vermessen werden muss), die Leiste selbst und der Platz aus
    :func:`_hinweis_platz`."""

    def _merke_platz(self, platz) -> None:
        if platz is self._platz:
            return
        if self._platz is not None:
            try:
                self._platz.removeEventFilter(self)
            except RuntimeError:            # Ansicht schon abgebaut
                pass
        self._platz = platz
        if platz is not None:
            platz.installEventFilter(self)

    def _ist_platz_ereignis(self, obj, ev) -> bool:
        return obj is self._platz and ev.type() in _PLATZ_EREIGNISSE

    def _merke_reiter(self, ansicht) -> None:
        neu = (ansicht, ansicht.tabBar()) if ansicht is not None else ()
        if neu == self._reiter:
            return
        for obj in self._reiter:
            try:
                obj.removeEventFilter(self)
            except RuntimeError:            # Ansicht schon abgebaut
                pass
        self._reiter = neu
        for obj in neu:
            obj.installEventFilter(self)

    def _ist_reiter_ereignis(self, obj, ev) -> bool:
        return (bool(self._reiter) and any(obj is o for o in self._reiter)
                and ev.type() in _REITER_EREIGNISSE)


class AusgabeBanner(_FolgtAnsicht, QLabel):
    """Nicht-modale Zeile oben im Hauptfenster. Kennt nur Darstellung.

    **VCB-47: ueberlagert, verschiebt nicht.** Das Banner lag frueher im
    Wurzel-Layout und schob beim Erscheinen und Verschwinden den ganzen Inhalt
    samt Virtual Console um seine Hoehe — mitten in der Show rutschten damit
    alle Tasten. Nach :meth:`ueberlagere` liegt es als freies Kind ueber dem
    oberen Rand des Inhaltsbereichs (``anker``), in voller Breite, und folgt
    dessen Lage und Groesse per Ereignisfilter. Es bleibt immer EINE Zeile hoch:
    ein zu langer Text wird mit „…“ gekuerzt, der volle Text steht im Tooltip.

    **UI-103: nie ueber den Unterreitern.** Der obere Rand des Inhaltsbereichs
    ist in fast jeder Sektion die Unterreiter-Zeile (Attribute/Snapshots/…,
    Output/DMX Monitor/MIDI/Musik, Playback/Show Manager/Kurven) — das Banner
    lag halb ueber den Beschriftungen. Hat die gezeigte Ansicht Unterreiter,
    steht es rechts neben dem letzten Reiter in derselben Zeile (passt der
    Text nicht ganz, gekuerzt; nur wenn nicht einmal „Probenmodus…“ passt,
    direkt unter der Reiterzeile). Ansichten ohne Reiter, die mit
    ``ausgabe_chip_platz()`` eine freie Zeile nennen (Virtual Console, auch
    im Kiosk), bekommen es rechtsbuendig in diese Zeile — nicht mehr ueber
    Bank-Blaetterknoepfe und Werkzeugleiste. Siehe :meth:`ziel_rechteck`.
    Es ueberlagert weiter, verschiebt also nichts.

    Mausklicks enden am Banner (Qt reicht sie nie an verdeckte Geschwister
    weiter; die Ereignisse werden zusaetzlich angenommen, damit auch das
    Elternfenster nichts davon sieht) — eine verdeckte Taste loest nicht aus.

    **Einklappen (Nachtrag 2).** Rechts im Balken steht der Knopf
    „▴ einklappen“. Er ist GEMALT, kein Kind-Widget: das Banner bleibt ein
    einziges Widget, ``childAt`` liefert ueberall das Banner selbst. Ein Klick
    in dieses Feld meldet :attr:`einklappen`, ein Klick auf den uebrigen Balken
    wie bisher :attr:`geklickt`. Per Tastatur: das Banner ist ein Halt in der
    Tab-Reihenfolge (ein Mausklick nimmt den Fokus NICHT), die Eingabetaste
    klappt ein.
    """

    geklickt = Signal()
    einklappen = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ausgabeBanner")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._voll = ""             # ungekuerzter Text (siehe text())
        self._tip = ""
        self._anker = None
        self._reiter = ()
        self._platz = None
        self._polster = None        # (stil, rahmen, oben) wie zuletzt gesetzt
        self._kuerzt = False
        self._knopf_font = QFont(self.font())
        self._knopf_breite = 0
        self._knopf_farbe = QColor("#ffffff")
        self._knopf_rahmen = True
        self.hide()

    # -- Text: aussen immer der volle, gezeigt wird ggf. der gekuerzte --------

    def text(self) -> str:  # noqa: D401 (Qt-Name)
        """Der VOLLE Bannertext — auch wenn die Zeile ihn gekuerzt zeigt."""
        return self._voll

    def gezeigter_text(self) -> str:
        return super().text()

    def zeige(self, z: BannerZustand) -> None:
        if not z.art:
            self._voll = self._tip = ""
            super().setText("")
            self.setToolTip("")
            _verstecke(self)
            self._merke_platz(None)
            return
        self._voll = z.text
        self._tip = z.tooltip
        self._stil(_STIL_KLEIN if z.klein else _STIL[z.art], rahmen=not z.klein)
        self._kuerze()
        self.show()
        self.lege_an()

    def _stil(self, stil, rahmen: bool) -> None:
        _rumpf, oben, _links, knopf_px, farbe = stil
        font = QFont(self.font())
        font.setBold(False)
        font.setPixelSize(knopf_px)
        self._knopf_font = font
        self._knopf_farbe = QColor(farbe)
        self._knopf_rahmen = rahmen
        self._knopf_breite = (
            QFontMetrics(font).horizontalAdvance(TEXT_EINKLAPPEN) + 14)
        if self._polster is None or self._polster[:2] != (stil, rahmen):
            self._setze_polster(stil, rahmen, oben)
        # sonst bleibt ein (fuer eine niedrige Zeile) verkleinertes Polster
        # stehen; lege_an() rechnet es ohnehin neu — kein Neu-Stylen im Takt.

    def _setze_polster(self, stil, rahmen: bool, oben: int) -> None:
        if self._polster == (stil, rahmen, oben):
            return
        self._polster = (stil, rahmen, oben)
        rumpf, _oben, links = stil[0], stil[1], stil[2]
        rechts = self._knopf_breite + links + 6
        self.setStyleSheet(
            f"QLabel#ausgabeBanner {{ {rumpf} padding:{oben}px {rechts}px"
            f" {oben}px {links}px; }}")

    def _hoehe_hoechstens(self, max_h: int) -> int:
        """UI-103: die Bannerhoehe fuer eine Zeile von ``max_h`` px.

        Ist die Zeile (Reiterzeile, VC-Zeile „Aktiver Effekt“) niedriger als
        das Banner, wird nur das Polster oben/unten kleiner — Schrift, Farben
        und Rahmen bleiben. Sonst gilt das volle Polster der Darstellung."""
        if self._polster is None:
            return min(self.sizeHint().height(), max(max_h, 0))
        stil, rahmen, jetzt = self._polster
        voll = stil[1]
        self.ensurePolished()
        hoehe_voll = self.sizeHint().height() + 2 * (voll - jetzt)
        oben = voll
        if hoehe_voll > max_h:
            oben = max(voll - (hoehe_voll - max_h + 1) // 2, 0)
        self._setze_polster(stil, rahmen, oben)
        return self.sizeHint().height()

    def knopf_rechteck(self) -> QRect:
        """Das Feld „▴ einklappen“ (Trefferflaeche: volle Hoehe, bis zum
        rechten Rand)."""
        breite = min(self._knopf_breite + 12, max(self.width(), 0))
        return QRect(self.width() - breite, 0, breite, self.height())

    def paintEvent(self, ev):  # noqa: N802 (Qt-Name)
        super().paintEvent(ev)
        if not self._knopf_breite:
            return
        feld = self.knopf_rechteck().adjusted(6, 2, -6, -3)
        if feld.width() <= 0 or feld.height() <= 0:
            return
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            farbe = QColor(self._knopf_farbe)
            if self._knopf_rahmen:
                fuellung = QColor(farbe)
                fuellung.setAlpha(70 if self.hasFocus() else 36)
                p.setPen(farbe)
                p.setBrush(fuellung)
                p.drawRoundedRect(feld, 3, 3)
            p.setPen(farbe)
            p.setFont(self._knopf_font)
            p.drawText(feld, Qt.AlignmentFlag.AlignCenter, TEXT_EINKLAPPEN)
        finally:
            p.end()

    def _kuerze(self) -> None:
        """Eine Zeile, nie breiter als das Banner: sonst „…“ + Tooltip."""
        if self._kuerzt:
            return
        self._kuerzt = True
        try:
            zeile = " ".join(self._voll.splitlines())
            self.ensurePolished()
            fm = self.fontMetrics()
            super().setText(zeile)
            breite = fm.horizontalAdvance(zeile)
            rand = max(super().sizeHint().width() - breite, 0)
            platz = self.width() - rand
            gekuerzt = bool(zeile) and platz < breite
            if gekuerzt:
                super().setText(fm.elidedText(
                    zeile, Qt.TextElideMode.ElideRight, max(platz, 0)))
            if gekuerzt or zeile != self._voll:
                self.setToolTip(f"{self._voll}\n\n{self._tip}".strip())
            else:
                self.setToolTip(self._tip)
        finally:
            self._kuerzt = False

    # -- Lage: ueber dem oberen Rand des Inhaltsbereichs ---------------------

    def ueberlagere(self, anker) -> None:
        """Ab jetzt frei ueber dem oberen Rand von ``anker`` liegen.

        ``anker`` muss im selben Elternwidget liegen wie das Banner (im
        Hauptfenster: der Ansichtsstapel unter Kopf- und Sektionsleiste)."""
        if self._anker is not None:
            self._anker.removeEventFilter(self)
            _trenne_wechsel(self._anker, self._ansicht_gewechselt)
        self._anker = anker
        anker.installEventFilter(self)
        # UI-103: beim Sektionswechsel neu legen — die neue Ansicht hat
        # vielleicht Unterreiter, die alte nicht (oder andersherum).
        wechsel = getattr(anker, "currentChanged", None)
        if wechsel is not None:
            wechsel.connect(self._ansicht_gewechselt)
        self.lege_an()

    def _ansicht_gewechselt(self, *_a) -> None:
        self.lege_an()

    def _volle_breite(self) -> int:
        """So breit muss das Banner sein, damit der Text NICHT gekuerzt wird
        (samt Polster und Einklapp-Knopf)."""
        self.ensurePolished()
        fm = self.fontMetrics()
        gezeigt = super().text()
        rand = max(super().sizeHint().width() - fm.horizontalAdvance(gezeigt), 0)
        # +2: sizeHint() rundet die Textbreite anders als horizontalAdvance();
        # ohne Zugabe fehlte dem ungekuerzten Text mitunter 1 px.
        return fm.horizontalAdvance(" ".join(self._voll.splitlines())) + rand + 2

    def _mindest_breite(self) -> int:
        """UI-103: so schmal darf das Banner in der Reiterzeile werden — der
        Anfang der Meldung bis zum ersten „:“/„—“ (also „Probenmodus…“ bzw.
        „Ausgabe gestört…“) muss lesbar bleiben; der Rest wird gekuerzt und
        steht im Tooltip."""
        self.ensurePolished()
        fm = self.fontMetrics()
        gezeigt = super().text()
        rand = max(super().sizeHint().width() - fm.horizontalAdvance(gezeigt), 0)
        kopf = re.split(r"\s*[:—]", " ".join(self._voll.splitlines()), maxsplit=1)[0]
        return fm.horizontalAdvance(kopf.strip() + "…") + rand

    def ziel_rechteck(self) -> QRect:
        """Wo das Banner liegen soll (Koordinaten des Elternwidgets).

        UI-103: Hat die gezeigte Ansicht Unterreiter, liegt es NIE darueber —
        rechts neben dem letzten Reiter in derselben Zeile (passt der volle
        Text dort nicht, gekuerzt mit „…“, der volle Text steht im Tooltip).
        Nur wenn dort nicht einmal „Probenmodus…“/„Ausgabe gestört…“ Platz
        hat, liegt es direkt unter der Reiterzeile. Ohne Unterreiter nennt die
        Ansicht ihren freien Platz (Virtual Console, auch im Kiosk: die Zeile
        „Aktiver Effekt“, rechtsbuendig), sonst wie bisher am oberen Rand."""
        anker, eltern = self._anker, self.parentWidget()
        ecke = anker.mapTo(eltern, QPoint(0, 0))
        bereich = QRect(ecke, anker.size())
        reiter = _unterreiter(anker, eltern)
        self._merke_reiter(anker.currentWidget() if reiter is not None else None)
        platz = _hinweis_platz(anker, eltern) if reiter is None else None
        self._merke_platz(platz)
        if platz is not None:
            feld = QRect(platz.mapTo(eltern, QPoint(0, 0)), platz.size())
            if bereich.contains(feld):
                hoehe = min(self._hoehe_hoechstens(feld.height()), feld.height())
                breite = min(self._volle_breite(), feld.width())
                oben = feld.top() + (feld.height() - hoehe) // 2
                return QRect(feld.left() + feld.width() - breite, oben,
                             breite, hoehe)
        if reiter is None:
            hoehe = min(self._hoehe_hoechstens(1 << 20), max(anker.height(), 0))
            return QRect(bereich.left(), bereich.top(), bereich.width(), hoehe)
        zeile, belegt_bis, frei_bis = reiter
        links = belegt_bis + REITER_LUECKE
        breite = frei_bis - links
        hoehe = self._hoehe_hoechstens(zeile.height())
        if breite >= self._mindest_breite() and zeile.height() >= hoehe:
            oben = zeile.top() + (zeile.height() - hoehe) // 2
            return QRect(links, oben, breite, hoehe)
        hoehe = min(self._hoehe_hoechstens(1 << 20), max(anker.height(), 0))
        oben = zeile.top() + zeile.height()
        rest = bereich.top() + bereich.height() - oben
        return QRect(bereich.left(), oben, bereich.width(),
                     max(min(hoehe, rest), 0))

    def lege_an(self) -> None:
        anker, eltern = self._anker, self.parentWidget()
        if anker is None or eltern is None or self.isHidden():
            return
        ziel = self.ziel_rechteck()
        if self.geometry() != ziel:
            self.setGeometry(ziel)
        self._kuerze()
        self.raise_()

    def eventFilter(self, obj, ev):  # noqa: N802 (Qt-Name)
        if ((obj is self._anker and ev.type() in _ANKER_EREIGNISSE)
                or self._ist_platz_ereignis(obj, ev)
                or self._ist_reiter_ereignis(obj, ev)):
            self.lege_an()
        return False

    def resizeEvent(self, ev):  # noqa: N802 (Qt-Name)
        super().resizeEvent(ev)
        self._kuerze()

    # -- Maus und Tastatur: enden hier ---------------------------------------

    def mousePressEvent(self, ev):  # noqa: N802 (Qt-Name)
        if self.knopf_rechteck().contains(ev.position().toPoint()):
            self.einklappen.emit()
        else:
            self.geklickt.emit()
        ev.accept()

    def mouseReleaseEvent(self, ev):  # noqa: N802 (Qt-Name)
        ev.accept()

    def mouseDoubleClickEvent(self, ev):  # noqa: N802 (Qt-Name)
        ev.accept()

    def keyPressEvent(self, ev):  # noqa: N802 (Qt-Name)
        if ev.key() in _KLAPP_TASTEN:
            self.einklappen.emit()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def focusInEvent(self, ev):  # noqa: N802 (Qt-Name)
        super().focusInEvent(ev)
        self.update()

    def focusOutEvent(self, ev):  # noqa: N802 (Qt-Name)
        super().focusOutEvent(ev)
        self.update()


class AusgabeChip(_FolgtAnsicht, QLabel):
    """VCB-47 (Nachtrag 2): das eingeklappte Banner.

    Ein kleines Schild, das an der Stelle des Banners steht, solange der
    Bediener die Meldung eingeklappt hat: rot bei „Ausgabe gestört“, gedeckt
    beim Probenhinweis. Klick oder Eingabetaste klappen wieder auf; der
    Tooltip traegt den vollen Text.

    **Lage.** Wie das Banner ein freies, oberstes Kind neben dem Inhaltsbereich
    (``anker``) — nie ueber Laser-NOT-AUS, STOP ALL, BLACKOUT, Grand Master,
    die alle ausserhalb davon liegen. Innerhalb sucht er sich den Platz, an dem
    er nichts verdeckt: Nennt die gezeigte Ansicht mit ``ausgabe_chip_platz()``
    ein Widget ohne Bedienfunktion, sitzt der Chip rechtsbuendig darin (Virtual
    Console: die Zeile „Aktiver Effekt“ zwischen Werkzeugleiste und Tasten —
    dort verdeckt er in keiner Fensterbreite einen Knopf oder eine Taste).
    Sonst liegt er in der oberen rechten Ecke des Inhaltsbereichs.
    """

    geklickt = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ausgabeChip")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._anker = None
        self._platz = None
        self._reiter = ()
        self.hide()

    def zeige(self, z: BannerZustand) -> None:
        if not z.art:
            self.verstecke()
            return
        text = TEXT_CHIP_STOERUNG if z.art == ART_STOERUNG else TEXT_CHIP_PROBE
        stil = _STIL_CHIP[z.art]
        if self.styleSheet() != stil:
            self.setStyleSheet(stil)
        if self.text() != text:
            self.setText(text)
        tip = (f"{z.text}\n\n{z.tooltip}\n\nEingeklappt. Ein Klick (per "
               "Tastatur die Eingabetaste) klappt die Meldung wieder auf.")
        if self.toolTip() != tip:
            self.setToolTip(tip)
        self.show()
        self.lege_an()

    def verstecke(self) -> None:
        _verstecke(self)
        self._merke_platz(None)

    # -- Lage ----------------------------------------------------------------

    def ueberlagere(self, anker) -> None:
        if self._anker is not None:
            self._anker.removeEventFilter(self)
            _trenne_wechsel(self._anker, self._ansicht_gewechselt)
        self._anker = anker
        anker.installEventFilter(self)
        wechsel = getattr(anker, "currentChanged", None)
        if wechsel is not None:
            wechsel.connect(self._ansicht_gewechselt)
        self.lege_an()

    def _ansicht_gewechselt(self, *_a) -> None:
        self.lege_an()

    def lege_an(self) -> None:
        anker, eltern = self._anker, self.parentWidget()
        if anker is None or eltern is None or self.isHidden():
            return
        platz = _hinweis_platz(anker, eltern)
        self._merke_platz(platz)
        reiter = _unterreiter(anker, eltern)
        self._merke_reiter(anker.currentWidget() if reiter is not None else None)
        wunsch = self.sizeHint()
        bereich = QRect(anker.mapTo(eltern, QPoint(0, 0)), anker.size())
        ziel = None
        if platz is not None:
            feld = QRect(platz.mapTo(eltern, QPoint(0, 0)), platz.size())
            hoehe = min(wunsch.height(), feld.height())
            oben = feld.top() + (feld.height() - hoehe) // 2
            ziel = self._rechts_in(feld, oben, hoehe, wunsch.width())
            # Der Chip ist kein Kind des Inhaltsbereichs und wird von ihm
            # nicht beschnitten. Liegt der genannte Platz (bei zu kleinem
            # Fenster) ausserhalb, stuende der Chip ueber fremden Leisten oder
            # jenseits des Fensterrands — dann lieber die sichere Ecke.
            if (not bereich.contains(ziel) or ziel.width() < wunsch.width()
                    or ziel.height() < wunsch.height()):
                ziel = None
        if ziel is None:
            hoehe = min(wunsch.height(), max(bereich.height() - CHIP_RAND, 0))
            ziel = self._rechts_in(bereich, bereich.top() + CHIP_RAND, hoehe,
                                   wunsch.width())
            # UI-103: in der Unterreiter-Zeile nur rechts neben den Reitern;
            # reicht der Platz dort nicht, unter die Zeile.
            if reiter is not None:
                zeile, belegt_bis, frei_bis = reiter
                if ziel.left() < belegt_bis + CHIP_RAND or ziel.right() >= frei_bis:
                    unten = zeile.top() + zeile.height()
                    rest = bereich.top() + bereich.height() - unten
                    ziel = self._rechts_in(
                        bereich, unten + CHIP_RAND,
                        min(wunsch.height(), max(rest - CHIP_RAND, 0)),
                        wunsch.width())
        if self.geometry() != ziel:
            self.setGeometry(ziel)
        self.raise_()

    @staticmethod
    def _rechts_in(feld: QRect, oben: int, hoehe: int, wunsch_b: int) -> QRect:
        breite = min(wunsch_b, max(feld.width() - 2 * CHIP_RAND, 0))
        links = feld.left() + feld.width() - CHIP_RAND - breite
        return QRect(links, oben, breite, hoehe)

    def eventFilter(self, obj, ev):  # noqa: N802 (Qt-Name)
        if ((obj is self._anker and ev.type() in _ANKER_EREIGNISSE)
                or self._ist_platz_ereignis(obj, ev)
                or self._ist_reiter_ereignis(obj, ev)):
            self.lege_an()
        return False

    # -- Maus und Tastatur: enden hier ---------------------------------------

    def mousePressEvent(self, ev):  # noqa: N802 (Qt-Name)
        self.geklickt.emit()
        ev.accept()

    def mouseReleaseEvent(self, ev):  # noqa: N802 (Qt-Name)
        ev.accept()

    def mouseDoubleClickEvent(self, ev):  # noqa: N802 (Qt-Name)
        ev.accept()

    def keyPressEvent(self, ev):  # noqa: N802 (Qt-Name)
        if ev.key() in _KLAPP_TASTEN:
            self.geklickt.emit()
            ev.accept()
            return
        super().keyPressEvent(ev)


class AusgabeBannerSteuerung:
    """Haelt Banner, Chip, Drossel und „eingeklappt“ zusammen.

    Das Hauptfenster ruft :meth:`aktualisiere` aus seinem bestehenden
    2-s-Hardware-Takt (``_check_hardware`` -> ``_update_ausgabe_label``) — es
    gibt keinen zweiten Timer und keine zweite Abfrage der Hardware.

    **Eingeklappt (VCB-47, Nachtrag 2).** Statt des Banners steht dann der
    :class:`AusgabeChip`. Fuer den Probenhinweis ist das der Schalter
    :attr:`probe_aus` (bleibt fuer die Sitzung). Fuer eine Stoerung gibt es
    bewusst KEINEN Schalter, sondern das Gedaechtnis ``_gesehen``: welche
    Ausfaelle der Bediener beim Einklappen vor sich hatte und wann jeder davon
    zuletzt anlag. Eingeklappt ist die Stoerung nur, solange jeder gerade
    anliegende Ausfall darin frisch ist (:data:`NACHSICHT_S`) — ein neuer
    Ausfall kann so nicht hinter einem alten Klick verschwinden. Nichts davon
    wird gespeichert.
    """

    def __init__(self, kiosk: bool = False, uhr=time.monotonic, parent=None):
        self.kiosk = bool(kiosk)
        #: Probenhinweis eingeklappt (Name aus OUT-67: damals „ausgeblendet“).
        self.probe_aus = False
        #: Was ein Klick auf den Text einer Stoerung tut (das Fenster haengt
        #: hier die Output-Einstellungen ein). ``None`` (Kiosk) = der Klick
        #: klappt ein wie der Knopf.
        self.bei_stoerung_klick = None
        self._uhr = uhr
        self._drossel = BannerDrossel()
        self._letzte_art = ART_KEIN
        self._schluessel = frozenset()      # Ausfaelle der gezeigten Stoerung
        self._gesehen = {}                  # Ausfall -> zuletzt anliegend (Uhr)
        # Ausfall -> wann er zuletzt WIRKLICH anlag (nicht: zuletzt gezeigt —
        # die Drossel haelt eine Meldung noch HALTE_S nach).
        self._anliegend = {}
        self.widget = AusgabeBanner(parent)
        self.chip = AusgabeChip(parent)
        self.widget.geklickt.connect(self._klick)
        self.widget.einklappen.connect(self.klappe_ein)
        self.chip.geklickt.connect(self.klappe_aus)

    @property
    def zustand(self) -> BannerZustand:
        return self._drossel.aktuell

    @property
    def eingeklappt(self) -> bool:
        """Steht gerade der Chip statt des Banners?"""
        art = self._drossel.aktuell.art
        if art == ART_STOERUNG:
            return bool(self._gesehen)
        return art == ART_PROBE and self.probe_aus

    def ueberlagere(self, anker) -> None:
        """Banner und Chip ueber den Inhaltsbereich ``anker`` legen."""
        self.widget.ueberlagere(anker)
        self.chip.ueberlagere(anker)

    def aktualisiere(self, om, wege=None) -> None:
        """Darf nie werfen — das Banner haengt im Takt der Statusleiste."""
        try:
            if wege is None:
                wege = om.ausgabe_status()
            roh = ausgabe_banner(wege, kiosk=self.kiosk)
            jetzt = self._uhr()
            if roh.art == ART_STOERUNG:
                # ★ Steht VOR dem Anzeigen und darf es nie verhindern: kann
                # die Stoerung nicht wiedererkannt werden, ist sie neu.
                try:
                    self._schluessel = stoer_schluessel(wege)
                    self._pruefe_neue_stoerung(jetzt)
                    self._anliegend = {a: jetzt for a in self._schluessel}
                except Exception:
                    self._schluessel = frozenset()
                    self._gesehen.clear()
            self._zeige(self._drossel.schritt(roh, jetzt))
        except Exception as exc:
            try:
                from src.core import diagnose_log
                diagnose_log.melde_still("ausgabe-banner", exc)
            except Exception:
                pass

    def _pruefe_neue_stoerung(self, jetzt: float) -> None:
        """Eingeklappt bleibt nur, was der Bediener gesehen hat."""
        if not self._gesehen:
            return
        for ausfall in self._schluessel:
            zuletzt = self._gesehen.get(ausfall)
            # Auch ein „zuletzt“ in der Zukunft (Uhr lief rueckwaerts) ist
            # nicht frisch — im Zweifel aufklappen.
            if zuletzt is None or not 0.0 <= jetzt - zuletzt <= NACHSICHT_S:
                self._gesehen.clear()
                self._logge_ansicht("Neue Störung — Meldung klappt wieder auf")
                return
        for ausfall in self._schluessel:
            self._gesehen[ausfall] = jetzt

    # -- Bedienung -----------------------------------------------------------

    def _klick(self) -> None:
        z = self._drossel.aktuell
        if z.art == ART_STOERUNG and callable(self.bei_stoerung_klick):
            self.bei_stoerung_klick()
        else:
            self.klappe_ein()

    def klappe_ein(self) -> None:
        """Das gezeigte Banner auf den Chip verkleinern."""
        z = self._drossel.aktuell
        if not z.art or self.eingeklappt:
            return
        fokus = _hat_fokus(self.widget)
        if z.art == ART_PROBE:
            self.probe_aus = True
            self._logge_ansicht("Probenhinweis eingeklappt")
        else:
            jetzt = self._uhr()
            # Codex-Review #1089: je Ausfall der Zeitpunkt, an dem er zuletzt
            # ANLAG — nicht der Klick. Eingeklappt waehrend der Nachhaltezeit
            # zaehlte NACHSICHT_S sonst ab dem Klick, und eine Stoerung, die
            # nach mehr als NACHSICHT_S zurueckkam, blieb nur ein Chip.
            self._gesehen = {a: self._anliegend.get(a, jetzt)
                             for a in (self._schluessel or {z.text})}
            self._logge_ansicht("Störungsmeldung eingeklappt")
        self._zeige(z)
        if fokus:
            self.chip.setFocus(Qt.FocusReason.TabFocusReason)

    def klappe_aus(self) -> None:
        """Wieder das volle Banner zeigen (auch: Gedaechtnis vergessen)."""
        war = self.eingeklappt
        fokus = _hat_fokus(self.chip)
        self.probe_aus = False
        self._gesehen.clear()
        if war:
            self._logge_ansicht("Meldung wieder ausgeklappt")
        self._zeige(self._drossel.aktuell)
        if fokus and not self.widget.isHidden():
            self.widget.setFocus(Qt.FocusReason.TabFocusReason)

    def _zeige(self, z: BannerZustand, log_text: str = "") -> None:
        if z.art and self.eingeklappt and self._zeige_chip(z):
            self.widget.zeige(KEIN_BANNER)
        else:
            if z.art and self.eingeklappt:
                # Der Chip waere die einzige Anzeige — steht er nicht, gilt
                # die Meldung als ausgeklappt.
                self.probe_aus = False
                self._gesehen.clear()
                self._logge_ansicht("Chip nicht darstellbar — Meldung "
                                    "klappt wieder auf")
            try:
                self.chip.verstecke()
            except Exception:
                pass
            self.widget.zeige(z)
        vorher, self._letzte_art = self._letzte_art, z.art
        if z.art == ART_STOERUNG:
            self._logge(z.text)             # auch bei geaendertem Grund
            return
        if vorher == z.art:
            return
        if vorher == ART_STOERUNG:
            self._logge("Ausgabe läuft wieder")
        if z.art == ART_PROBE:
            self._logge(z.text)
        elif vorher == ART_PROBE:
            self._logge(log_text or "Probenmodus beendet — ein Ausgang ist "
                        "eingerichtet")

    def _zeige_chip(self, z: BannerZustand) -> bool:
        """Den Chip zeigen. ``False``, wenn er danach nicht wirklich steht
        (Fehler, versteckt oder ohne Flaeche) — dann muss das Banner her."""
        try:
            self.chip.zeige(z)
            return (not self.chip.isHidden() and self.chip.width() > 0
                    and self.chip.height() > 0)
        except Exception:
            return False

    @staticmethod
    def _logge(text: str) -> None:
        """Eine ``[diagnose]``-Zeile im Sitzungs-Log — ``merke`` schreibt nur
        bei AENDERUNG, die Abfrage alle 2 s flutet das Log also nicht."""
        try:
            from src.core import diagnose_log
            diagnose_log.merke(LOG_SCHLUESSEL, text)
        except Exception:
            pass

    @staticmethod
    def _logge_ansicht(text: str) -> None:
        try:
            from src.core import diagnose_log
            diagnose_log.merke(LOG_SCHLUESSEL_ANSICHT, text)
        except Exception:
            pass
