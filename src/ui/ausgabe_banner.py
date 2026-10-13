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
statt den Inhalt nach unten zu schieben (siehe :class:`AusgabeBanner`):

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
from PySide6.QtWidgets import QLabel                            # noqa: E402

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
# Bewusst OHNE Leertaste: sie ist im Hauptfenster das Kuerzel fuer „GO“ und
# muss das auch bleiben, wenn Banner oder Chip gerade den Fokus haben.
_KLAPP_TASTEN = (Qt.Key.Key_Return, Qt.Key.Key_Enter)

#: Abstand des Chips zum Rand seines Platzes (px).
CHIP_RAND = 4


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


class AusgabeBanner(QLabel):
    """Nicht-modale Zeile oben im Hauptfenster. Kennt nur Darstellung.

    **VCB-47: ueberlagert, verschiebt nicht.** Das Banner lag frueher im
    Wurzel-Layout und schob beim Erscheinen und Verschwinden den ganzen Inhalt
    samt Virtual Console um seine Hoehe — mitten in der Show rutschten damit
    alle Tasten. Nach :meth:`ueberlagere` liegt es als freies Kind ueber dem
    oberen Rand des Inhaltsbereichs (``anker``), in voller Breite, und folgt
    dessen Lage und Groesse per Ereignisfilter. Es bleibt immer EINE Zeile hoch:
    ein zu langer Text wird mit „…“ gekuerzt, der volle Text steht im Tooltip.

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
            return
        self._voll = z.text
        self._tip = z.tooltip
        self._stil(_STIL_KLEIN if z.klein else _STIL[z.art], rahmen=not z.klein)
        self._kuerze()
        self.show()
        self.lege_an()

    def _stil(self, stil, rahmen: bool) -> None:
        rumpf, oben, links, knopf_px, farbe = stil
        font = QFont(self.font())
        font.setBold(False)
        font.setPixelSize(knopf_px)
        self._knopf_font = font
        self._knopf_farbe = QColor(farbe)
        self._knopf_rahmen = rahmen
        self._knopf_breite = (
            QFontMetrics(font).horizontalAdvance(TEXT_EINKLAPPEN) + 14)
        rechts = self._knopf_breite + links + 6
        self.setStyleSheet(
            f"QLabel#ausgabeBanner {{ {rumpf} padding:{oben}px {rechts}px"
            f" {oben}px {links}px; }}")

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
        self._anker = anker
        anker.installEventFilter(self)
        self.lege_an()

    def lege_an(self) -> None:
        anker, eltern = self._anker, self.parentWidget()
        if anker is None or eltern is None or self.isHidden():
            return
        ecke = anker.mapTo(eltern, QPoint(0, 0))
        hoehe = min(self.sizeHint().height(), max(anker.height(), 0))
        self.setGeometry(ecke.x(), ecke.y(), anker.width(), hoehe)
        self._kuerze()
        self.raise_()

    def eventFilter(self, obj, ev):  # noqa: N802 (Qt-Name)
        if obj is self._anker and ev.type() in _ANKER_EREIGNISSE:
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


class AusgabeChip(QLabel):
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
            wechsel = getattr(self._anker, "currentChanged", None)
            if wechsel is not None:
                try:
                    wechsel.disconnect(self._ansicht_gewechselt)
                except (RuntimeError, TypeError):
                    pass
        self._anker = anker
        anker.installEventFilter(self)
        wechsel = getattr(anker, "currentChanged", None)
        if wechsel is not None:
            wechsel.connect(self._ansicht_gewechselt)
        self.lege_an()

    def _ansicht_gewechselt(self, *_a) -> None:
        self.lege_an()

    def _suche_platz(self):
        """Das Widget, in dem der Chip nichts verdeckt — oder ``None``."""
        anker, eltern = self._anker, self.parentWidget()
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

    def lege_an(self) -> None:
        anker, eltern = self._anker, self.parentWidget()
        if anker is None or eltern is None or self.isHidden():
            return
        platz = self._suche_platz()
        self._merke_platz(platz)
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
                or (obj is self._platz and ev.type() in _PLATZ_EREIGNISSE)):
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
            self._gesehen = {a: jetzt for a in (self._schluessel or {z.text})}
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
