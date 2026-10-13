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
  Ausgang eingerichtet ist. Dezent, per Klick fuer die Sitzung abschaltbar, im
  Kiosk-Modus nur als schmale Zeile.

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

#: Schluessel fuer ``diagnose_log.merke`` (Sitzungs-Log + Diagnosepaket).
LOG_SCHLUESSEL = "ausgabe-banner"

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
    keiner. ``probe_aus`` — der Probenhinweis wurde weggeklickt; ein Ausfall
    laesst sich nicht wegklicken.
    """
    wege = list(wege or [])
    kaputt = [w for w in wege if w.get("verbunden") is False]
    if kaputt:
        erster = kaputt[0]
        text = f"Ausgabe gestört: {_weg_name(erster)} — {_grund(erster)}"
        if len(kaputt) > 1:
            text += f"  (+{len(kaputt) - 1} weitere)"
        zeilen = [f"{_weg_name(w)}: {_grund(w)}" for w in kaputt]
        zeilen += ["", "Verschwindet von selbst, sobald die Ausgabe wieder läuft."]
        return BannerZustand(ART_STOERUNG, text, "\n".join(zeilen))
    if not wege and not probe_aus:
        return BannerZustand(
            ART_PROBE, TEXT_PROBE,
            "Kein Universum hat einen Ausgang — alles wird nur gerechnet.\n"
            "Ausgänge: Output-Einstellungen. Klick blendet den Hinweis für "
            "diese Sitzung aus.",
            klein=bool(kiosk))
    return KEIN_BANNER


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
from PySide6.QtCore import QEvent, QPoint, Qt, Signal    # noqa: E402
from PySide6.QtWidgets import QLabel                     # noqa: E402

_STIL = {
    ART_STOERUNG: ("QLabel#ausgabeBanner { background:#8a1414; color:#ffffff;"
                   " font-weight:bold; font-size:13px; padding:5px 12px;"
                   " border-bottom:1px solid #ff4444; }"),
    ART_PROBE: ("QLabel#ausgabeBanner { background:#26231a; color:#c9b46a;"
                " font-size:11px; padding:2px 12px;"
                " border-bottom:1px solid #4a4326; }"),
}
_STIL_KLEIN = ("QLabel#ausgabeBanner { background:#1c1b17; color:#8f8458;"
               " font-size:9px; padding:0 8px; }")

_ANKER_EREIGNISSE = (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show)


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
    """

    geklickt = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ausgabeBanner")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voll = ""             # ungekuerzter Text (siehe text())
        self._tip = ""
        self._anker = None
        self._kuerzt = False
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
            self.hide()
            return
        self._voll = z.text
        self._tip = z.tooltip
        self.setStyleSheet(_STIL_KLEIN if z.klein else _STIL[z.art])
        self._kuerze()
        self.show()
        self.lege_an()

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

    # -- Maus: Klicks enden hier ---------------------------------------------

    def mousePressEvent(self, ev):  # noqa: N802 (Qt-Name)
        self.geklickt.emit()
        ev.accept()

    def mouseReleaseEvent(self, ev):  # noqa: N802 (Qt-Name)
        ev.accept()

    def mouseDoubleClickEvent(self, ev):  # noqa: N802 (Qt-Name)
        ev.accept()


class AusgabeBannerSteuerung:
    """Haelt Banner, Drossel und „Probenhinweis weggeklickt" zusammen.

    Das Hauptfenster ruft :meth:`aktualisiere` aus seinem bestehenden
    2-s-Hardware-Takt (``_check_hardware`` -> ``_update_ausgabe_label``) — es
    gibt keinen zweiten Timer und keine zweite Abfrage der Hardware.
    """

    def __init__(self, kiosk: bool = False, uhr=time.monotonic, parent=None):
        self.kiosk = bool(kiosk)
        self.probe_aus = False
        #: Was ein Klick auf eine Stoerung tut (das Fenster haengt hier die
        #: Output-Einstellungen ein). ``None`` = nichts.
        self.bei_stoerung_klick = None
        self._uhr = uhr
        self._drossel = BannerDrossel()
        self._letzte_art = ART_KEIN
        self.widget = AusgabeBanner(parent)
        self.widget.geklickt.connect(self._klick)

    @property
    def zustand(self) -> BannerZustand:
        return self._drossel.aktuell

    def aktualisiere(self, om, wege=None) -> None:
        """Darf nie werfen — das Banner haengt im Takt der Statusleiste."""
        try:
            if wege is None:
                wege = om.ausgabe_status()
            roh = ausgabe_banner(wege, kiosk=self.kiosk,
                                 probe_aus=self.probe_aus)
            self._zeige(self._drossel.schritt(roh, self._uhr()))
        except Exception as exc:
            try:
                from src.core import diagnose_log
                diagnose_log.melde_still("ausgabe-banner", exc)
            except Exception:
                pass

    def _klick(self) -> None:
        z = self._drossel.aktuell
        if z.art == ART_PROBE:
            self.probe_aus = True
            self._zeige(self._drossel.setze(KEIN_BANNER), "Probenhinweis "
                        "für diese Sitzung ausgeblendet")
        elif z.art == ART_STOERUNG and callable(self.bei_stoerung_klick):
            self.bei_stoerung_klick()

    def _zeige(self, z: BannerZustand, log_text: str = "") -> None:
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

    @staticmethod
    def _logge(text: str) -> None:
        """Eine ``[diagnose]``-Zeile im Sitzungs-Log — ``merke`` schreibt nur
        bei AENDERUNG, die Abfrage alle 2 s flutet das Log also nicht."""
        try:
            from src.core import diagnose_log
            diagnose_log.merke(LOG_SCHLUESSEL, text)
        except Exception:
            pass
