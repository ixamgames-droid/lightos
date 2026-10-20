"""IMP-2: Mitschnitt-Assistent — Szenen aus einem anderen Lichtprogramm
uebernehmen.

Das andere Programm gibt seine Szenen nacheinander aus, LightOS empfaengt das
ueber den Art-Net-/sACN-Eingang, und **Als Szene festhalten** macht aus dem
gerade empfangenen Bild eine Szene. Am Ende werden die festgehaltenen Szenen
auf Wunsch ein Chaser.

★ Der Dialog LIEST nur den Eingang. Er gibt nichts aus, startet und stoppt
keinen Empfaenger, aendert keine Merge-Zuordnung und fasst weder Programmer
noch laufende Funktionen an. Die Rechnung steht in ``src/core/mitschnitt.py``.

Der Assistent ist NICHT modal: er ist ein eigenes Fenster ueber dem
Hauptfenster, daneben bleiben DMX-Monitor, 3D-Fenster und Funktionsliste
bedienbar. Daraus folgt dreierlei, und alle drei stehen hier im Code:

* Es gibt nur EINE Instanz — :func:`zeige_assistent` holt die offene nach vorn.
* Die Leertaste haelt nur fest, solange der Assistent das aktive Fenster ist
  (``WindowShortcut``). Im Hauptfenster bleibt sie GO.
* Show und Patch koennen sich aendern, waehrend er offen ist. Der Patch wird
  bei jedem Festhalten frisch gelesen; nach einem Show-Wechsel beginnt die
  Liste neu (siehe :meth:`MitschnittDialog._lage_pruefen`).

Aufbau des Fensters: oben ein Rollbereich mit Eingang und Einstellungen, darunter
FEST (nie im Rollbereich) Name, „Als Szene festhalten“, die Meldung, die Liste
mit „Entfernen“ und der Chaser-Zeile sowie „Fertig“. Auf einem niedrigen
Bildschirm rollt nur der obere Teil.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

try:                                             # Gueltigkeit eines Qt-Objekts
    from shiboken6 import isValid as _qt_gueltig
except Exception:                                # pragma: no cover
    _qt_gueltig = None

from src.core import mitschnitt as M
from src.ui.widgets import dialog_groesse as DG

TITEL = "Mitschnitt-Assistent"
STAMM = "Mitschnitt"

#: Breite, mit der der Dialog aufgeht, wenn der Bildschirm sie hergibt. Die
#: HOEHE steht nirgends als Zahl: sie folgt dem umbrochenen Inhalt.
STARTBREITE = 640
#: Kleinste Breite. Die kleinste HOEHE rechnet `_masse_nachziehen` aus dem
#: festen Teil — so kann man das Fenster nie so klein ziehen, dass sich Knopf,
#: Meldung, Liste und „Fertig“ ueberlagern.
MINDESTBREITE = 420
#: Zeilen, die die Liste der festgehaltenen Szenen IMMER zeigt.
MINDESTZEILEN = 3
#: Zeilen, mit denen die Liste aufgeht, wenn der Bildschirm es hergibt.
LISTENZEILEN = 5
#: Zeilen, die die Meldung unter dem Knopf immer freihaelt (sie waechst, wenn
#: ein Text laenger ist — dann gibt der Rollbereich darueber Platz ab).
MELDUNGSZEILEN = 2
#: Hoehe, die der Rollbereich mindestens behaelt.
ROLLBEREICH_MINDESTHOEHE = 48

TEXT_FESTHALTEN = "Als Szene festhalten"
TEXT_ENTFERNEN = "Entfernen"
TEXT_FERTIG = "Fertig"
TEXT_CHASER = "Am Ende als Chaser zusammenfassen"
TEXT_LASER = "Laser mit aufnehmen"
TEXT_UNRUHIG = "Auch festhalten, wenn sich das Bild noch ändert"
TEXT_HILFE_ZEIGEN = "Hilfe zum Eingang einblenden"
TEXT_HILFE_WEG = "Hilfe zum Eingang ausblenden"

AUSWAHL_TEXT = {
    M.AUSWAHL_ALLE: "Alle gepatchten Kanäle",
    M.AUSWAHL_UNGLEICH_NULL: "Nur Kanäle ungleich 0",
    M.AUSWAHL_GEAENDERT: "Nur was sich seit dem letzten Festhalten geändert hat",
}

HILFE_EINGANG = (
    "Eingang einschalten: Menü „Ausgabe“ → „Konfigurieren...“ → "
    "Reiter „DMX-Eingang“. Dort „Art-Net-Eingang aktivieren“ oder „sACN-Eingang "
    "aktivieren“ anhaken, bei „Eingehendes Universum“ das Universum des anderen "
    "Programms und bei „Mischen in Universum“ das LightOS-Universum deines Patches "
    "eintragen, dann „Übernehmen“. Das andere Programm muss an diesen Rechner "
    "senden.")
HINWEIS_NUR_LESEN = (
    "Der Assistent liest nur den Eingang. Er gibt selbst nichts aus und ändert "
    "weder den Programmer noch laufende Funktionen.")
HINWEIS_LASER = (
    "Laser werden ausgelassen (Sicherheitsvorgabe). Nur mit dem Haken „"
    + TEXT_LASER + "“ kommen ihre Kanäle mit in die Szene.")

TIPP_FESTHALTEN = (
    "Hält das gerade empfangene Bild als Szene fest. Die Leertaste tut "
    "dasselbe, solange dieses Fenster das aktive ist. Knöpfe und Haken "
    "bedienst du hier per Tastatur deshalb mit der Eingabetaste.")

GRUND_KEIN_SIGNAL = "Kein Signal — es gibt nichts festzuhalten."
VERWEIS_HILFE = "Wie du den Eingang einschaltest, steht oben unter „Eingang“."
MELDUNG_SHOW_GEWECHSELT = (
    "Die Show wurde gewechselt oder neu geladen. Die Liste beginnt neu — was "
    "vorher festgehalten wurde, gehört zur vorherigen Show.")
MELDUNG_PATCH_GEAENDERT = (
    "Der Patch wurde geändert. Ab jetzt gilt der neue Patch; bereits "
    "festgehaltene Szenen bleiben, wie sie sind.")
GRUND_KEIN_PATCH = (
    "Es ist noch kein Gerät gepatcht. Lege zuerst den Patch an — ohne ihn "
    "weiß LightOS nicht, welche Kanäle zu welchem Gerät gehören.")
GRUND_UNRUHIG = (
    "Das Bild ändert sich noch (läuft eine Überblendung?). Warte, bis es "
    "ruhig steht, und drücke dann noch einmal.")
GRUND_KEINE_WERTE = (
    "Im empfangenen Bild liegt nichts auf gepatchten Adressen — es entsteht "
    "keine Szene.")


def _dauer(sekunden: float) -> str:
    s = int(sekunden)
    if s < 60:
        return f"{s} s"
    return f"{s // 60} min {s % 60:02d} s"


class _Lage:
    """Merkt sich, dass sich Show oder Patch geaendert haben.

    Haengt am Sync-Bus an Stelle des Dialogs. Die Meldungen koennen kommen,
    waehrend der Dialog gerade abgebaut wird — deshalb fasst diese Klasse KEIN
    Qt-Objekt an, sie setzt nur zwei Merker. Der Dialog liest sie an seinem
    Zeitgeber und vor jeder Aktion (`_lage_pruefen`)."""

    def __init__(self):
        self.show_gewechselt = False
        self.patch_geaendert = False
        self._sync = None

    def _bei_show(self, *_):
        self.show_gewechselt = True

    def _bei_patch(self, *_):
        self.patch_geaendert = True

    def verbinden(self, sync) -> None:
        if self._sync is not None or sync is None:
            return
        from src.core.sync import SyncEvent
        self._sync = sync
        sync.subscribe(SyncEvent.SHOW_LOADED, self._bei_show)
        sync.subscribe(SyncEvent.PATCH_CHANGED, self._bei_patch)

    def trennen(self) -> None:
        sync, self._sync = self._sync, None
        if sync is None:
            return
        from src.core.sync import SyncEvent
        sync.unsubscribe(SyncEvent.SHOW_LOADED, self._bei_show)
        sync.unsubscribe(SyncEvent.PATCH_CHANGED, self._bei_patch)

    @property
    def verbunden(self) -> bool:
        return self._sync is not None


class MitschnittDialog(QDialog):
    """Der Assistent. ``state`` und ``leser`` lassen sich fuer Tests
    hereinreichen; ohne Angabe gelten AppState und die echten Empfaenger.

    Geoeffnet wird er ueber :func:`zeige_assistent` (nicht modal, eine
    Instanz)."""

    def __init__(self, parent=None, *, state=None, leser: M.EingangsLeser | None = None):
        super().__init__(parent)
        self.setWindowTitle(TITEL)
        self.setModal(False)
        self._groesse_gesetzt = False
        self._abgebaut = False
        if state is None:
            from src.core.app_state import get_state
            state = get_state()
        self._state = state
        self._leser = leser or M.EingangsLeser()
        self._bezug: dict[int, bytes] | None = None
        self._zaehler = 1
        self._vorschlag = ""
        #: festgehaltene Szenen in Reihenfolge (Funktions-IDs) …
        self._szenen: list[int] = []
        #: … und die Objekte dazu. Eine ID allein reicht nicht: nach einem
        #: Show-Wechsel kann dieselbe Nummer eine FREMDE Funktion sein.
        self._szenen_obj: dict[int, object] = {}
        #: … und was hinter dem Namen steht („3 Geräte, 12 Kanäle“). Der Name
        #: selbst wird bei jeder Anzeige frisch gelesen: die Funktionsliste im
        #: Hauptfenster kann eine Szene umbenennen, waehrend der Assistent
        #: offen ist.
        self._szenen_text: dict[int, str] = {}
        self.chaser = None

        self._baue_oberflaeche()
        self._leser.verbinden()
        self._lage = _Lage()
        self._lage.verbinden(getattr(state, "sync", None))
        # Wird das Fenster zerstoert, OHNE vorher geschlossen zu werden (das
        # Hauptfenster reisst es beim Beenden mit), melden sich Zuhoerer und
        # Lage trotzdem ab. Die Lambda haelt nur Python-Objekte, kein `self`.
        self.destroyed.connect(
            lambda *_a, _l=self._leser, _g=self._lage: (_l.trennen(), _g.trennen()))
        # „Schliesst mit dem Hauptfenster“: verschwindet das Elternfenster,
        # schliesst der Assistent (und raeumt dabei ab).
        self._hauptfenster = parent.window() if parent is not None else None
        if self._hauptfenster is not None:
            self._hauptfenster.installEventFilter(self)
        self._name_vorschlagen()
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.aktualisiere)
        self._timer.start()
        self.aktualisiere()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _baue_oberflaeche(self):
        aussen = QVBoxLayout(self)

        # ── Oben: Eingang und Einstellungen. Nur DIESER Teil rollt, wenn der
        #    Bildschirm niedrig ist (`root` = Layout des Inhalts). ─────────────
        self._inhalt = QWidget()
        root = QVBoxLayout(self._inhalt)
        root.setContentsMargins(0, 0, 0, 0)
        self._rollbereich = DG.InhaltsRollbereich(self._inhalt)
        self._rollbereich.setMinimumHeight(ROLLBEREICH_MINDESTHOEHE)
        aussen.addWidget(self._rollbereich)

        kopf = QLabel(HINWEIS_NUR_LESEN)
        kopf.setWordWrap(True)
        root.addWidget(kopf)

        box = QGroupBox("Eingang")
        bl = QVBoxLayout(box)
        self._lbl_status = {}
        for protokoll in (M.ARTNET, M.SACN):
            lbl = QLabel()
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            self._lbl_status[protokoll] = lbl
            bl.addWidget(lbl)
        self._lbl_live = QLabel()
        self._lbl_live.setWordWrap(True)
        bl.addWidget(self._lbl_live)
        # Die Wegbeschreibung ist lang. Sie laesst sich einklappen und startet
        # eingeklappt, wenn der Bildschirm sonst nicht reicht (`showEvent`).
        zeile = QHBoxLayout()
        self._btn_hilfe = QPushButton(TEXT_HILFE_WEG)
        self._btn_hilfe.setCheckable(True)
        self._btn_hilfe.setChecked(True)
        self._btn_hilfe.setAutoDefault(False)
        self._btn_hilfe.setToolTip(
            "Blendet die Wegbeschreibung ein oder aus, wie du den Art-Net- "
            "oder sACN-Eingang einschaltest. Mit der Tastatur: mit der "
            "Tabulatortaste hierher, dann die Eingabetaste.")
        self._btn_hilfe.clicked.connect(self._hilfe_anwenden)
        zeile.addWidget(self._btn_hilfe)
        zeile.addStretch(1)
        bl.addLayout(zeile)
        self._lbl_hilfe = QLabel(HILFE_EINGANG)
        self._lbl_hilfe.setWordWrap(True)
        self._lbl_hilfe.setStyleSheet("color:#c9a227;")
        bl.addWidget(self._lbl_hilfe)
        self._hat_signal = False
        root.addWidget(box)

        box = QGroupBox("Einstellungen")
        form = QFormLayout(box)
        # Lange Eintraege der Kanalauswahl duerfen das Feld nicht aus dem
        # Fenster schieben; umbrochene Zeilen bekommen die volle Breite.
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._combo_auswahl = QComboBox()
        for schluessel in M.AUSWAHLEN:
            self._combo_auswahl.addItem(AUSWAHL_TEXT[schluessel], schluessel)
        self._combo_auswahl.setCurrentIndex(M.AUSWAHLEN.index(M.AUSWAHL_VORGABE))
        # Der laengste Eintrag soll nicht die Mindestbreite des Fensters
        # bestimmen; die Klappliste zeigt ihn trotzdem ganz.
        self._combo_auswahl.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._combo_auswahl.setMinimumContentsLength(22)
        self._combo_auswahl.setToolTip(
            "Welche Kanäle in die Szene kommen. „Alle gepatchten Kanäle“ hält "
            "das ganze Bild fest — auch, was dunkel ist. Die anderen beiden "
            "Regeln lassen Kanäle weg; solche Szenen lassen andere Funktionen "
            "auf diesen Kanälen durch. Die Dimmer-Kanäle eines aufgenommenen "
            "Geräts kommen immer mit, damit eine Farbe ohne Dimmer dunkel bleibt.")
        form.addRow("Kanäle:", self._combo_auswahl)
        self._check_laser = QCheckBox(TEXT_LASER)
        self._check_laser.setToolTip(HINWEIS_LASER)
        form.addRow(self._check_laser)
        self._lbl_laser = QLabel(HINWEIS_LASER)
        self._lbl_laser.setWordWrap(True)
        form.addRow(self._lbl_laser)
        self._spin_ruhe = QDoubleSpinBox()
        self._spin_ruhe.setRange(0.1, 10.0)
        self._spin_ruhe.setSingleStep(0.1)
        self._spin_ruhe.setDecimals(1)
        self._spin_ruhe.setSuffix(" s")
        self._spin_ruhe.setValue(M.RUHEZEIT_VORGABE)
        self._spin_ruhe.setToolTip("So lange darf sich das empfangene Bild nicht "
                                   "geändert haben, damit es als ruhig gilt.")
        form.addRow("Ruhig nach:", self._spin_ruhe)
        self._check_unruhig = QCheckBox(TEXT_UNRUHIG)
        self._check_unruhig.setToolTip(
            "Für Quellen, die nie stillstehen (laufender Effekt). Festgehalten "
            "wird dann der Augenblick des Knopfdrucks.")
        form.addRow(self._check_unruhig)
        root.addWidget(box)
        root.addStretch(1)

        # ── Darunter FEST: was man bei jeder Szene braucht. Liegt nie im
        #    Rollbereich und ist deshalb bei jeder Fensterhoehe zu sehen. ─────
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Name:"))
        self._edit_name = QLineEdit()
        self._edit_name.setToolTip("Name der nächsten Szene. Nach dem Festhalten "
                                   "zählt LightOS von selbst weiter.")
        zeile.addWidget(self._edit_name, 1)
        self._btn_festhalten = QPushButton(TEXT_FESTHALTEN)
        self._btn_festhalten.setMinimumHeight(36)
        self._btn_festhalten.setToolTip(TIPP_FESTHALTEN)
        self._btn_festhalten.clicked.connect(self.festhalten)
        zeile.addWidget(self._btn_festhalten)
        aussen.addLayout(zeile)
        self._lbl_meldung = QLabel()
        self._lbl_meldung.setWordWrap(True)
        self._lbl_meldung.setAlignment(Qt.AlignmentFlag.AlignLeft
                                       | Qt.AlignmentFlag.AlignTop)
        # Der Platz ist von Anfang an da — sonst springt die Liste bei der
        # ersten Meldung.
        self._lbl_meldung.setMinimumHeight(
            MELDUNGSZEILEN * self._lbl_meldung.fontMetrics().lineSpacing())
        aussen.addWidget(self._lbl_meldung)

        # Leertaste haelt fest — aber nur, solange DIESES Fenster das aktive
        # ist (`WindowShortcut`): im Hauptfenster bleibt die Leertaste GO, auch
        # waehrend der Assistent daneben offen ist. Tippt man gerade im
        # Namensfeld, nimmt das Feld die Taste und schreibt ein Leerzeichen.
        self._kuerzel = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._kuerzel.setContext(Qt.ShortcutContext.WindowShortcut)
        # Ohne das wiederholt eine gehaltene Leertaste das Kuerzel im Takt der
        # Tastenwiederholung — ein ruhiges Bild ergaebe dann Szene um Szene.
        self._kuerzel.setAutoRepeat(False)
        self._kuerzel.activated.connect(self.festhalten)

        box = QGroupBox("Festgehaltene Szenen")
        ll = QVBoxLayout(box)
        self._liste = QListWidget()
        self._liste.setUniformItemSizes(True)
        self._liste.addItem("X")
        self._zeilenhoehe = max(self._liste.sizeHintForRow(0),
                                self._liste.fontMetrics().height() + 2)
        self._liste.clear()
        self._liste.setMinimumHeight(
            MINDESTZEILEN * self._zeilenhoehe + 2 * self._liste.frameWidth())
        # Wird die Liste niedriger (laengere Meldung, eingeblendete Hilfe),
        # bleibt die markierte Szene zu sehen — siehe `eventFilter`.
        self._liste.viewport().installEventFilter(self)
        ll.addWidget(self._liste, 1)
        zeile = QHBoxLayout()
        self._btn_entfernen = QPushButton(TEXT_ENTFERNEN)
        self._btn_entfernen.setToolTip("Löscht die markierte Szene wieder "
                                       "(lässt sich rückgängig machen).")
        self._btn_entfernen.clicked.connect(self.entferne_markierte)
        zeile.addWidget(self._btn_entfernen)
        zeile.addStretch(1)
        ll.addLayout(zeile)
        zeile = QHBoxLayout()
        self._check_chaser = QCheckBox(TEXT_CHASER)
        self._check_chaser.setToolTip(
            "Beim Schließen über „Fertig“ entsteht ein Chaser, der die Szenen "
            "in dieser Reihenfolge abspielt.")
        zeile.addWidget(self._check_chaser)
        zeile.addWidget(QLabel("Schrittzeit:"))
        self._spin_schritt = QDoubleSpinBox()
        self._spin_schritt.setRange(0.1, 600.0)
        self._spin_schritt.setSingleStep(0.5)
        self._spin_schritt.setDecimals(1)
        self._spin_schritt.setSuffix(" s")
        self._spin_schritt.setValue(1.0)
        self._spin_schritt.setToolTip("So lange steht jeder Schritt des Chasers.")
        zeile.addWidget(self._spin_schritt)
        zeile.addStretch(1)
        ll.addLayout(zeile)
        aussen.addWidget(box, 1)

        zeile = QHBoxLayout()
        zeile.addStretch(1)
        self._btn_fertig = QPushButton(TEXT_FERTIG)
        self._btn_fertig.setToolTip("Schließt den Assistenten. Die Szenen "
                                    "bleiben in der Funktionsliste.")
        self._btn_fertig.setAutoDefault(False)
        self._btn_fertig.clicked.connect(self.fertig)
        zeile.addWidget(self._btn_fertig)
        aussen.addLayout(zeile)
        # Rollt den oberen Teil zur Wegbeschreibung, nachdem sie eingeblendet
        # wurde — erst nach dem Umbruch, deshalb ueber einen Null-Timer.
        self._sicht_timer = QTimer(self)
        self._sicht_timer.setSingleShot(True)
        self._sicht_timer.setInterval(0)
        self._sicht_timer.timeout.connect(self._hilfe_zeigen)
        self._markierung_timer = QTimer(self)
        self._markierung_timer.setSingleShot(True)
        self._markierung_timer.setInterval(0)
        self._markierung_timer.timeout.connect(self._markierung_zeigen)
        for knopf in (self._btn_festhalten, self._btn_entfernen):
            knopf.setAutoDefault(False)
        self._btn_festhalten.setFocus()
        # Mindestbreite: der feste Teil UND der Inhalt des Rollbereichs samt
        # Rollbalken — quer gerollt wird nie.
        aussen.activate()
        root.activate()
        raender = aussen.contentsMargins()
        balken = self._rollbereich.verticalScrollBar().sizeHint().width()
        innen = (self._inhalt.minimumSizeHint().width() + balken
                 + 2 * self._rollbereich.frameWidth()
                 + raender.left() + raender.right())
        self.setMinimumWidth(max(MINDESTBREITE, aussen.minimumSize().width(), innen))

    # ── Groesse ──────────────────────────────────────────────────────────────

    def _inhaltsbedarf(self, breite: int) -> int:
        """Hoehe, die der Inhalt des Rollbereichs bei ``breite`` braucht."""
        h = self._inhalt.heightForWidth(max(1, breite))
        if h < 0:
            h = self._inhalt.sizeHint().height()
        return max(h, self._inhalt.minimumSizeHint().height())

    def _feste_hoehe(self, breite: int) -> int:
        """Kleinste Fensterhoehe bei ``breite``: Raender, der feste Teil mit
        `MINDESTZEILEN` Listenzeilen und der Rest des Rollbereichs."""
        aussen = self.layout()
        h = aussen.minimumHeightForWidth(breite)
        if h < 0:
            h = aussen.minimumSize().height()
        return h

    def startbedarf(self, breite: int) -> int:
        """Fensterhoehe, bei der NICHTS rollt und die Liste `LISTENZEILEN`
        Zeilen zeigt."""
        raender = self.layout().contentsMargins()
        rahmen = 2 * self._rollbereich.frameWidth()
        innen = breite - raender.left() - raender.right() - rahmen
        return (self._feste_hoehe(breite) - ROLLBEREICH_MINDESTHOEHE
                + self._inhaltsbedarf(innen) + rahmen
                + (LISTENZEILEN - MINDESTZEILEN) * self._zeilenhoehe)

    def startgroesse(self) -> QSize:
        """Groesse, mit der der Dialog aufgeht: `STARTBREITE` breit und so
        hoch, wie der umbrochene Inhalt bei DIESER Breite braucht — hoechstens
        die verfuegbare Bildschirmflaeche. Reicht die nicht, gibt zuerst die
        Liste Zeilen ab (bis `MINDESTZEILEN`), dann rollt der obere Teil."""
        self.layout().activate()
        self._inhalt.layout().activate()
        grenze = DG.groesste_fenstergroesse(self)
        breite = min(max(STARTBREITE, self.minimumWidth()), grenze.width())
        return QSize(breite, min(self.startbedarf(breite), grenze.height()))

    def _masse_nachziehen(self):
        """Hoechstmass des Rollbereichs und Mindesthoehe des Fensters an den
        Inhalt anpassen (er aendert sich mit Breite, Meldung und Signal).

        Der Rollbereich wird nie hoeher als sein Inhalt — was uebrig ist,
        bekommt die Liste. Und das Fenster laesst sich nie so klein ziehen,
        dass der feste Teil nicht mehr passt: ein Fenster, das kleiner ist als
        sein Inhalt, schiebt Qt ineinander."""
        if self._abgebaut:
            return
        rahmen = 2 * self._rollbereich.frameWidth()
        bedarf = self._inhaltsbedarf(self._rollbereich.viewport().width()) + rahmen
        self._rollbereich.setMaximumHeight(max(bedarf, ROLLBEREICH_MINDESTHOEHE))
        grenze = DG.groesste_fenstergroesse(self).height()
        self.setMinimumHeight(min(self._feste_hoehe(self.width()), grenze))

    def showEvent(self, ev):
        # VOR super(): Qt mittet den Dialog dann mit der endgueltigen Groesse
        # ein. Wer vorher selbst resize() gerufen hat, behaelt seine Groesse.
        if not self._groesse_gesetzt:
            self._groesse_gesetzt = True
            eigene = self.testAttribute(Qt.WidgetAttribute.WA_Resized)
            ziel = self.size() if eigene else self.startgroesse()
            platz = (ziel.height() if eigene
                     else DG.groesste_fenstergroesse(self).height())
            # Passt nicht alles ohne Rollen, startet die Wegbeschreibung
            # eingeklappt — der Knopf darueber blendet sie wieder ein.
            if self._btn_hilfe.isChecked() and self.startbedarf(ziel.width()) > platz:
                self._btn_hilfe.setChecked(False)
                self._hilfe_anwenden()
                if not eigene:
                    ziel = self.startgroesse()
            if not eigene:
                self.resize(ziel)
            self._masse_nachziehen()
        super().showEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._masse_nachziehen()

    def _hilfe_anwenden(self, *_):
        """Knopf und Wegbeschreibung zeigen, was gilt: beides nur ohne Signal,
        die Wegbeschreibung nur ausgeklappt."""
        offen = self._btn_hilfe.isChecked()
        self._btn_hilfe.setText(TEXT_HILFE_WEG if offen else TEXT_HILFE_ZEIGEN)
        self._btn_hilfe.setVisible(not self._hat_signal)
        self._lbl_hilfe.setVisible(offen and not self._hat_signal)
        self._masse_nachziehen()

    def _hilfe_zeigen(self):
        if self._abgebaut or self._lbl_hilfe.isHidden():
            return
        self._rollbereich.ensureWidgetVisible(self._lbl_hilfe, 0, 8)

    def eventFilter(self, obj, ev):
        # Das Hauptfenster verschwindet (geschlossen oder versteckt, nicht
        # bloss minimiert): der Assistent schliesst mit und raeumt ab.
        if (obj is getattr(self, "_hauptfenster", None)
                and ev.type() == QEvent.Type.Hide and not ev.spontaneous()):
            self.close()
        liste = getattr(self, "_liste", None)
        if (liste is not None and ev.type() == QEvent.Type.Resize
                and not getattr(self, "_abgebaut", True)
                and getattr(self, "_markierung_timer", None) is not None
                and obj is liste.viewport()):
            # „Entfernen“ meint die markierte Zeile — sie darf nicht aus der
            # Sicht rutschen, wenn die Liste Platz abgibt. Erst NACH dem
            # Umbruch der Liste rollen, deshalb ueber einen Null-Timer.
            self._markierung_timer.start()
        return super().eventFilter(obj, ev)

    def _markierung_zeigen(self):
        if self._abgebaut:
            return
        item = self._liste.currentItem()
        if item is not None:
            self._liste.scrollToItem(item)

    def keyPressEvent(self, ev):
        # Die Leertaste haelt fest und ist damit fuer Knoepfe und Haken nicht
        # mehr frei (Qt bedient beide sonst NUR mit der Leertaste). Damit das
        # Fenster ohne Maus bedienbar bleibt, loest die Eingabetaste das Teil
        # aus, das den Fokus hat. Im Namensfeld und in den Zahlenfeldern tut
        # sie nichts — es gibt keinen Vorgabe-Knopf.
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                ev.modifiers() & ~Qt.KeyboardModifier.KeypadModifier):
            teil = self.focusWidget()
            if (isinstance(teil, QAbstractButton) and teil.isEnabled()
                    and teil.isVisible() and not self._abgebaut):
                if not ev.isAutoRepeat():
                    teil.click()
                ev.accept()
                return
        super().keyPressEvent(ev)

    # ── Abfragen ─────────────────────────────────────────────────────────────

    @property
    def szenen_ids(self) -> list[int]:
        """Die festgehaltenen Szenen, die es in der Show noch gibt — in der
        Reihenfolge des Festhaltens (so stehen sie in Liste und Chaser)."""
        return [sid for sid in self._szenen if self._lebt(sid)]

    def _fm(self):
        return self._state.function_manager

    def _patch(self):
        return list(self._state.get_patched_fixtures())

    def _lies(self, bild: M.Eingangsbild, auswahl=None) -> M.Mitschnitt:
        return M.lies_abbild(
            bild.abbild, self._patch(),
            auswahl=auswahl or self._combo_auswahl.currentData(),
            bezug=self._bezug,
            laser_mitnehmen=self._check_laser.isChecked())

    def grund_gesperrt(self, bild: M.Eingangsbild | None = None) -> str:
        """Warum jetzt nicht festgehalten werden kann — leer, wenn es geht."""
        bild = bild or self._leser.bild()
        if not bild.hat_signal:
            return GRUND_KEIN_SIGNAL
        if not self._patch():
            return GRUND_KEIN_PATCH
        if (not self._check_unruhig.isChecked()
                and not bild.ist_ruhig(self._spin_ruhe.value())):
            return GRUND_UNRUHIG
        return ""

    # ── Anzeige ──────────────────────────────────────────────────────────────

    def _status_text(self, protokoll: str, bild: M.Eingangsbild) -> str:
        if not self._leser.laeuft(protokoll):
            return f"{protokoll}: Eingang ist aus."
        zuordnung = self._leser.zuordnungen(protokoll)
        if not zuordnung:
            return (f"{protokoll}: Eingang läuft, aber es ist kein Universum "
                    f"zugeordnet.")
        staende = {(s.protokoll, s.universum): s for s in self._leser.puffer.stand()}
        teile = []
        for von, nach in sorted(zuordnung.items()):
            st = staende.get((protokoll, von))
            if st is None:
                lage = "kein Signal"
            elif not st.hat_signal:
                lage = f"kein Signal (letztes Paket vor {_dauer(st.letztes_paket_vor)})"
            else:
                lage = f"Signal seit {_dauer(st.signal_seit)}"
            teile.append(f"Universum {von} → LightOS-Universum {nach}: {lage}")
        text = f"{protokoll}: " + "; ".join(teile)
        fremd = sorted(u for p, u in bild.nicht_zugeordnet if p == protokoll)
        if fremd:
            text += (" — außerdem empfangen, aber nicht zugeordnet und deshalb "
                     "nicht mitgeschnitten: Universum "
                     + ", ".join(str(u) for u in fremd)
                     + " (es gilt ein Universum je Protokoll).")
        return text

    def _lebt(self, sid: int) -> bool:
        """Ist die festgehaltene Szene noch DIESELBE Funktion in der Show?"""
        szene = self._szenen_obj.get(sid)
        return szene is not None and self._fm().get(sid) is szene

    def _zeilentext(self, sid: int) -> str:
        szene = self._szenen_obj.get(sid)
        name = str(getattr(szene, "name", "") or sid)
        return f"{name} — {self._szenen_text.get(sid, '')}"

    def _lage_pruefen(self) -> bool:
        """Hat sich die Show oder der Patch geaendert, seit zuletzt geprueft
        wurde? Gibt zurueck, ob die Show gewechselt wurde.

        Entscheidung: der Assistent bleibt offen und zieht nach, statt sich zu
        schliessen. Er haengt nur am Eingang, und der laeuft ueber einen
        Show-Wechsel hinweg weiter; nichts im Fenster merkt sich Geraete — der
        Patch wird bei jedem Festhalten frisch gelesen, veraltete Geraete-IDs
        koennen so nicht in eine neue Szene kommen. Was NICHT uebernommen
        werden darf, ist die Liste: ihre Funktions-IDs gehoeren zur alten Show
        und koennen in der neuen eine fremde Funktion meinen. Sie beginnt
        deshalb neu, und die Meldung sagt es."""
        lage = self._lage
        if lage.show_gewechselt:
            lage.show_gewechselt = lage.patch_geaendert = False
            self._szenen.clear()
            self._szenen_obj.clear()
            self._szenen_text.clear()
            self._liste.clear()
            self._bezug = None
            self._zaehler = 1
            self._name_vorschlagen()
            self._melde(MELDUNG_SHOW_GEWECHSELT, fehler=True)
            return True
        if lage.patch_geaendert:
            lage.patch_geaendert = False
            laedt = getattr(self._state, "laedt_show", None)
            # Patch-Meldungen aus dem Nachlauf eines Show-Wechsels gehoeren
            # zu diesem — die Meldung dazu steht schon da.
            if not (callable(laedt) and laedt()):
                self._melde(MELDUNG_PATCH_GEAENDERT)
        return False

    def _liste_abgleichen(self):
        """Die Liste zeigt genau die festgehaltenen Szenen, die es noch gibt.
        Der Assistent sperrt die App nicht: Strg+Z im Hauptfenster kann eine
        Szene wegnehmen (und Strg+Y sie zurueckbringen), waehrend er offen ist."""
        soll = [sid for sid in self._szenen if self._lebt(sid)]
        ist = [self._liste.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(self._liste.count())]
        if soll == ist:
            for i, sid in enumerate(soll):       # umbenannt? Text nachziehen
                text = self._zeilentext(sid)
                if self._liste.item(i).text() != text:
                    self._liste.item(i).setText(text)
            return
        aktuell = self._liste.currentItem()
        gewaehlt = aktuell.data(Qt.ItemDataRole.UserRole) if aktuell else None
        self._liste.clear()
        for sid in soll:
            item = QListWidgetItem(self._zeilentext(sid))
            item.setData(Qt.ItemDataRole.UserRole, sid)
            self._liste.addItem(item)
            if sid == gewaehlt:
                self._liste.setCurrentItem(item)

    def aktualisiere(self):
        """Status, Live-Anzeige und Knopf neu setzen (laeuft am Timer)."""
        if self._abgebaut:
            return
        self._lage_pruefen()
        self._liste_abgleichen()
        bild = self._leser.bild()
        for protokoll, lbl in self._lbl_status.items():
            lbl.setText(self._status_text(protokoll, bild))
        self._hat_signal = bool(bild.hat_signal)
        self._hilfe_anwenden()

        if bild.hat_signal:
            m = self._lies(bild, auswahl=M.AUSWAHL_ALLE)
            text = (f"{m.geraete_mit_wert} von {m.geraete_gesehen} gepatchten "
                    f"Geräten bekommen gerade Werte.")
            text += (" Das Bild steht ruhig." if bild.ist_ruhig(self._spin_ruhe.value())
                     else " Das Bild ändert sich noch.")
            if m.ohne_bild:
                text += (f" {len(m.ohne_bild)} Gerät(e) liegen in einem Universum, "
                         f"das nicht empfangen wird — sie kommen nicht in die Szene.")
            if bild.doppelt:
                text += (" Achtung: Art-Net und sACN zeigen auf dasselbe "
                         "LightOS-Universum " + ", ".join(map(str, bild.doppelt))
                         + " — es gilt das zuletzt empfangene Bild.")
            laser = len(m.laser_ausgelassen)
        else:
            text = "Kein Signal."
            laser = 0
        self._lbl_live.setText(text)
        self._lbl_laser.setText(
            HINWEIS_LASER + (f" Gerade ausgelassen: {laser}." if laser else ""))
        self._lbl_laser.setVisible(not self._check_laser.isChecked())

        grund = self.grund_gesperrt(bild)
        # Der Knopf bleibt bedienbar und ERKLAERT, warum es nicht geht — ein
        # ausgegrauter Knopf sagt nichts. Nur der Tooltip traegt den Grund mit.
        self._btn_festhalten.setToolTip(grund or TIPP_FESTHALTEN)
        self._btn_entfernen.setEnabled(self._liste.currentRow() >= 0)
        self._check_chaser.setEnabled(True)
        self._masse_nachziehen()

    def _name_vorschlagen(self):
        self._vorschlag, self._zaehler = M.freier_name(self._fm(), STAMM, self._zaehler)
        self._edit_name.setText(self._vorschlag)

    def _melde(self, text: str, fehler: bool = False):
        self._lbl_meldung.setStyleSheet("color:#e0705a;" if fehler else "color:#7fc98f;")
        self._lbl_meldung.setText(text)
        self._masse_nachziehen()

    # ── Aktionen ─────────────────────────────────────────────────────────────

    def festhalten(self):
        """Das gerade empfangene Bild als Szene anlegen. Gibt die Szene zurueck
        oder ``None`` (die Meldungszeile nennt dann den Grund)."""
        if self._abgebaut:
            return None
        self._lage_pruefen()
        bild = self._leser.bild()
        grund = self.grund_gesperrt(bild)
        if grund:
            if grund == GRUND_KEIN_SIGNAL:
                # Die Wegbeschreibung steht oben; sie wird eingeblendet und
                # der obere Teil dorthin gerollt.
                grund += " " + VERWEIS_HILFE
                self._hat_signal = False
                self._btn_hilfe.setChecked(True)
                self._hilfe_anwenden()
                self._sicht_timer.start()
            self._melde(grund, fehler=True)
            return None
        m = self._lies(bild)
        if not m.kanalzahl:
            self._melde(GRUND_KEINE_WERTE, fehler=True)
            return None
        name = self._edit_name.text().strip() or f"{STAMM} {self._zaehler}"
        try:
            szene = M.baue_szene(self._fm(), name, m)
        except Exception as e:
            self._melde(str(e), fehler=True)
            return None
        self._bezug = dict(bild.abbild)
        self._szenen.append(szene.id)
        self._szenen_obj[szene.id] = szene
        self._szenen_text[szene.id] = (
            f"{len(m.geraete)} Geräte, {m.kanalzahl} Kanäle")
        item = QListWidgetItem(self._zeilentext(szene.id))
        item.setData(Qt.ItemDataRole.UserRole, szene.id)
        self._liste.addItem(item)
        self._liste.setCurrentItem(item)
        text = f"„{szene.name}“ festgehalten."
        if m.laser_ausgelassen:
            text += f" {len(m.laser_ausgelassen)} Laser ausgelassen."
        if not bild.ist_ruhig(self._spin_ruhe.value()):
            text += " Das Bild stand dabei nicht ruhig."
        self._melde(text)
        if szene.name == self._vorschlag:
            # Auch wenn die Szene wieder entfernt wird: die Nummer ist vergeben.
            self._zaehler += 1
        self._name_vorschlagen()
        self.aktualisiere()
        return szene

    def entferne_markierte(self):
        """Die markierte Szene wieder loeschen — eigener Rueckgaengig-Schritt."""
        if self._abgebaut or self._lage_pruefen():
            return
        zeile = self._liste.currentRow()
        if zeile < 0:
            return
        item = self._liste.takeItem(zeile)
        sid = item.data(Qt.ItemDataRole.UserRole)
        fm = self._fm()
        # Nur loeschen, was der Assistent selbst angelegt hat und was noch
        # dieselbe Funktion ist — nie eine fremde mit derselben Nummer.
        szene = fm.get(sid) if self._lebt(sid) else None
        if szene is None:
            # Gibt es nicht mehr (oder nicht mehr als dieselbe): vergessen.
            if sid in self._szenen:
                self._szenen.remove(sid)
            self._szenen_obj.pop(sid, None)
            self._szenen_text.pop(sid, None)
        else:
            # Codex-Review #1085: die Buchfuehrung bleibt stehen. Die Liste
            # zeigt ohnehin nur, was in der Show lebt (``_liste_abgleichen``);
            # holt Rueckgaengig die Szene zurueck, steht sie wieder an ihrem
            # Platz in der Liste und kommt in den Chaser. Vorher fehlte sie dort,
            # obwohl sie wieder in der Show war.
            from src.core.undo import Command, get_undo_stack
            get_undo_stack().push(Command(
                label=f"Mitschnitt „{szene.name}“ entfernen",
                do=lambda: fm.remove(sid),
                undo=lambda: fm.add(szene)))
            self._melde(f"„{szene.name}“ entfernt.")
        self.aktualisiere()

    def fertig(self):
        """Schliessen; mit Haken vorher den Chaser anlegen."""
        if self._abgebaut:
            return
        if self._lage_pruefen() and self._check_chaser.isChecked():
            # Die Show ist eben gewechselt worden: aus der alten Liste wird
            # kein Chaser. Offen bleiben, damit man die Meldung liest.
            return
        if self._check_chaser.isChecked() and self._szenen:
            fm = self._fm()
            ids = [sid for sid in self._szenen if self._lebt(sid)]
            if ids:
                name, _ = M.freier_name(fm, f"{STAMM} Chaser", 1)
                try:
                    self.chaser = M.baue_chaser(fm, name, ids,
                                                self._spin_schritt.value())
                except Exception as e:
                    self._melde(str(e), fehler=True)
                    return
        self.accept()

    # ── Abbau ────────────────────────────────────────────────────────────────

    def _abbauen(self):
        """Zeitgeber anhalten, Kuerzel abschalten, beim Eingang und am
        Sync-Bus abmelden. Darf mehrfach laufen (Fertig, Fenster-X, Esc,
        Hauptfenster zu). Danach tut kein Rueckruf mehr etwas — auch keiner,
        der schon in der Ereignisschleife liegt."""
        if self._abgebaut:
            return
        self._abgebaut = True
        self._timer.stop()
        self._sicht_timer.stop()
        self._markierung_timer.stop()
        self._kuerzel.setEnabled(False)
        self._leser.trennen()
        self._lage.trennen()
        fenster, self._hauptfenster = self._hauptfenster, None
        if fenster is not None and (_qt_gueltig is None or _qt_gueltig(fenster)):
            fenster.removeEventFilter(self)

    def done(self, ergebnis):
        self._abbauen()
        super().done(ergebnis)

    def closeEvent(self, ev):
        self._abbauen()
        super().closeEvent(ev)


# ── Oeffnen: nicht modal, eine Instanz ───────────────────────────────────────

_offen: MitschnittDialog | None = None


def offener_assistent() -> MitschnittDialog | None:
    """Der offene Assistent — oder ``None``."""
    dlg = _offen
    if dlg is None:
        return None
    if _qt_gueltig is not None and not _qt_gueltig(dlg):
        return None
    return None if dlg._abgebaut else dlg


def _vergiss(*_):
    global _offen
    dlg, _offen = _offen, None
    if dlg is not None and (_qt_gueltig is None or _qt_gueltig(dlg)):
        dlg.deleteLater()


def zeige_assistent(parent=None, **kw) -> MitschnittDialog:
    """Oeffnet den Assistenten als eigenes, NICHT modales Fenster ueber dem
    Fenster von ``parent`` — oder holt den schon offenen nach vorn. Es gibt
    nur eine Instanz: zwei Assistenten wuerden dieselben Namen vergeben und
    jeder seine eigene Liste fuer den Chaser fuehren."""
    global _offen
    dlg = offener_assistent()
    if dlg is None:
        _vergiss()                       # einen abgebauten Rest wegraeumen
        fenster = parent.window() if parent is not None else None
        dlg = MitschnittDialog(fenster, **kw)
        dlg.finished.connect(_vergiss)
        _offen = dlg
    if dlg.isMinimized():
        dlg.showNormal()
    else:
        dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
