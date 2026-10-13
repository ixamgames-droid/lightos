"""ENG-35 Schritt 1: Ansicht „Prioritäten“ — welcher Effekt gewinnt?

Eine Liste aller Effekte der Show, gruppiert nach den fuenf Stufen (staerkste
oben). Darueber steht fest und ausgegraut die Zeile der Snap-Tasten und des
Programmers: die liegen immer ueber allen Stufen und lassen sich nicht
einsortieren. Je Zeile: Name, Art, was der Effekt anfasst (Dimmer / Farbe /
Bewegung / Gobo) und ob er gerade laeuft.

Die Stufe aendert man durch Ziehen in eine andere Stufe, ueber „Stufe höher /
tiefer“, ueber das Auswahlfeld oder per Rechtsklick — auch fuer mehrere Zeilen
auf einmal. Jede Aenderung ist ein Rueckgaengig-Schritt.

Die Ansicht rechnet nichts neu: sie schreibt nur die Zahl ``priority``, die der
Engine-Merge ohnehin auswertet (``FunctionManager.tick``).

Aufbau-Regel dieses Moduls: die Liste wird NIE aus einem ihrer eigenen Signale
heraus neu gebaut — jede Aenderung meldet nur „veraltet“ an, gebaut wird im
naechsten Durchlauf der Ereignisschleife.
"""
from __future__ import annotations

import weakref

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMenu, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from src.core.engine import stufen
from src.core.engine.function_manager import get_function_manager
from src.ui.widgets.stufe_auswahl import (StufeAuswahl, setze_stufen,
                                          stufen_melder)

_ROLLE_FID = Qt.ItemDataRole.UserRole          # Funktions-ID einer Effekt-Zeile
_ROLLE_ZAHL = Qt.ItemDataRole.UserRole + 1     # Zahl einer Stufen-Zeile
_SPALTEN = ("Effekt", "Art", "Fasst an", "Zustand")
_BERNSTEIN = QColor("#ffb000")
_GRAU = QColor("#7d8590")


class _StufenBaum(QTreeWidget):
    """Baum mit Ziehen zwischen den Stufen. Qt verschiebt hier selbst NICHTS:
    ein Abwurf meldet nur „diese Zeilen in jene Stufe“ an die Ansicht."""

    def __init__(self, ansicht: "PrioritaetenView"):
        super().__init__()
        self._ansicht = weakref.ref(ansicht)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def _ziel_zahl(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return None
        if item.data(0, _ROLLE_FID) is not None:
            item = item.parent()
        if item is None:
            return None
        return item.data(0, _ROLLE_ZAHL)

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self and self._ziel_zahl(
                event.position().toPoint()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        zahl = self._ziel_zahl(event.position().toPoint())
        # Immer ablehnen: sonst wuerde Qt die Zeilen selbst umhaengen. Die
        # Ansicht baut sich nach der Aenderung aus den Daten neu auf.
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.ignore()
        ansicht = self._ansicht()
        if zahl is not None and event.source() is self and ansicht is not None:
            ansicht.auswahl_in_stufe(int(zahl))


class PrioritaetenView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fm = get_function_manager()
        self._veraltet = True
        self._baue = False
        self._setup_ui()

        self._neu_timer = QTimer(self)
        self._neu_timer.setSingleShot(True)
        self._neu_timer.setInterval(0)
        self._neu_timer.timeout.connect(self._neu_aufbauen_wenn_sichtbar)

        # Laufzustand nachziehen (wie die Funktionsliste: alle 500 ms, nur
        # wenn die Ansicht zu sehen ist).
        self._lauf_timer = QTimer(self)
        self._lauf_timer.setInterval(500)
        self._lauf_timer.timeout.connect(self._laufzustand_nachziehen)
        self._lauf_timer.start()

        stufen_melder().geaendert.connect(self._melde_veraltet)
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            ref = weakref.ref(self)

            def _veraltet(*_a, _ref=ref):
                w = _ref()
                if w is not None:
                    w._melde_veraltet()

            for ev in (SyncEvent.FUNCTION_CHANGED, SyncEvent.REFRESH_ALL,
                       SyncEvent.SHOW_LOADED, SyncEvent.PATCH_CHANGED):
                sync.subscribe_widget(ev, self, _veraltet)
        except Exception as e:
            print(f"[prioritaeten_view] sync subscribe error: {e}")

    # ── Aufbau ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        kopf = QLabel(
            "<b>Welcher Effekt gewinnt?</b> Schreiben zwei Effekte denselben "
            "Kanal, gewinnt die höhere Stufe. In derselben Stufe gewinnt, wer "
            "zuletzt gestartet wurde. Farbe und Dimmer sind getrennte Kanäle — "
            "ein Farb-Effekt und ein Dimmer-Effekt nehmen sich nichts weg.")
        kopf.setWordWrap(True)
        root.addWidget(kopf)

        leiste = QHBoxLayout()
        leiste.setSpacing(6)
        self._btn_hoeher = QPushButton("▲ Stufe höher")
        self._btn_hoeher.setToolTip("Ausgewählte Effekte eine Stufe stärker machen")
        self._btn_hoeher.clicked.connect(self._hoeher)
        leiste.addWidget(self._btn_hoeher)
        self._btn_tiefer = QPushButton("▼ Stufe tiefer")
        self._btn_tiefer.setToolTip("Ausgewählte Effekte eine Stufe schwächer machen")
        self._btn_tiefer.clicked.connect(self._tiefer)
        leiste.addWidget(self._btn_tiefer)
        leiste.addSpacing(12)
        leiste.addWidget(QLabel("Auswahl in Stufe:"))
        self._ziel_combo = StufeAuswahl()
        self._ziel_combo.setToolTip("Stufe für die ausgewählten Effekte wählen")
        self._ziel_combo.stufe_gewaehlt.connect(self.auswahl_in_stufe)
        leiste.addWidget(self._ziel_combo)
        leiste.addStretch(1)
        self._lbl_auswahl = QLabel("")
        self._lbl_auswahl.setStyleSheet("color:#7d8590;")
        leiste.addWidget(self._lbl_auswahl)
        root.addLayout(leiste)

        self._baum = _StufenBaum(self)
        self._baum.setColumnCount(len(_SPALTEN))
        self._baum.setHeaderLabels(list(_SPALTEN))
        self._baum.setRootIsDecorated(True)
        self._baum.setUniformRowHeights(True)
        self._baum.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._baum.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._baum.customContextMenuRequested.connect(self._kontextmenue)
        self._baum.itemSelectionChanged.connect(self._auswahl_geaendert)
        kopfzeile = self._baum.header()
        kopfzeile.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for spalte in (1, 2, 3):
            kopfzeile.setSectionResizeMode(
                spalte, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._baum, 1)

        fuss = QLabel(
            "Zeilen in eine andere Stufe ziehen — oder auswählen und oben die "
            "Stufe setzen (Strg/Umschalt für mehrere). Die Stufe einer Sammlung, "
            "eines Chasers oder einer Show gilt für alles, was darin läuft.")
        fuss.setWordWrap(True)
        fuss.setStyleSheet("color:#7d8590;")
        root.addWidget(fuss)
        self._auswahl_geaendert()

    # ── Daten ─────────────────────────────────────────────────────────────────

    def _funktionen(self) -> list:
        """Alle Effekte der Show, die DMX schreiben koennen. Nicht gelistet:
        ungespeicherte Entwuerfe und Audio-Funktionen (die schreiben kein DMX,
        eine Stufe haette dort keine Wirkung)."""
        aus = []
        for f in self._fm.all():
            if getattr(f, "committed", True) is False:
                continue
            if getattr(getattr(f, "function_type", None), "value", "") == "Audio":
                continue
            aus.append(f)
        return aus

    def _kanal_attribut(self):
        """(Geraete-ID, Kanal-Nr.) -> Attribut, fuer die Bausteine von Szenen.
        Faul und mit Zwischenspeicher: ein Geraet wird nur nachgeschlagen, wenn
        eine Szene es wirklich nennt."""
        cache: dict[int, dict[int, str] | None] = {}
        geraete: dict[int, object] = {}
        try:
            from src.core.app_state import get_state
            for fx in get_state().get_patched_fixtures():
                geraete[int(fx.fid)] = fx
        except Exception as e:
            print(f"[prioritaeten_view] patch error: {e}")

        def nachschlagen(fid: int, kanal: int):
            if fid not in cache:
                fx = geraete.get(fid)
                tabelle = None
                if fx is not None:
                    try:
                        from src.core.app_state import get_channels_for_patched
                        tabelle = {int(ch.channel_number): str(ch.attribute or "")
                                   for ch in get_channels_for_patched(fx)}
                    except Exception:
                        tabelle = None
                cache[fid] = tabelle
            tabelle = cache[fid]
            return tabelle.get(kanal) if tabelle else None

        return nachschlagen

    def _mitglied_von(self, funktionen) -> dict[int, list[str]]:
        """Funktions-ID -> Namen der Chaser/Sammlungen/Shows, in denen sie
        steckt (dort gilt die Stufe des Behaelters)."""
        aus: dict[int, list[str]] = {}
        for f in funktionen:
            typ = getattr(getattr(f, "function_type", None), "value", "")
            if typ == "Chaser":
                kinder = [getattr(s, "function_id", None)
                          for s in getattr(f, "steps", None) or ()]
            elif typ == "Collection":
                kinder = list(getattr(f, "function_ids", None) or ())
            elif typ == "Show":
                kinder = [getattr(sf, "function_id", None)
                          for spur in getattr(f, "tracks", None) or ()
                          for sf in getattr(spur, "show_functions", None) or ()]
            else:
                continue
            for kid in kinder:
                try:
                    liste = aus.setdefault(int(kid), [])
                except (TypeError, ValueError):
                    continue
                if f.name not in liste:
                    liste.append(f.name)
        return aus

    def _ueberschneidungs_tipps(self) -> dict[int, list[str]]:
        """ENG-39: je Effekt, der auf einer Taste oder einem Fader der Virtual
        Console liegt, dieselben Saetze wie die gelbe Hinweiszeile an der Taste
        („Dieser Effekt und … steuern beide …“). Leer, wenn die Ansicht nicht
        im selben Fenster wie eine Virtual Console steckt. Laeuft nur beim
        Neuaufbau der Liste."""
        try:
            from src.core.engine import ueberschneidung
            from src.ui.virtualconsole.vc_canvas import VCCanvas
            from src.ui.widgets.ueberschneidung_hinweis import (
                konsolen_funktions_ids, rechen_umgebung)
            ids: list[int] = []
            for flaeche in self.window().findChildren(VCCanvas):
                for fid in konsolen_funktions_ids(flaeche):
                    if fid not in ids:
                        ids.append(fid)
            if len(ids) < 2:
                return {}
            umgebung = rechen_umgebung()
            funktionen = [f for f in (self._fm.get(i) for i in ids)
                          if f is not None]
            aus: dict[int, list[str]] = {}
            for f in funktionen:
                zeilen = ueberschneidung.hinweis_zeilen(
                    ueberschneidung.ueberschneidungen(f, funktionen, **umgebung),
                    "Effekt")
                if zeilen:
                    aus[int(f.id)] = zeilen
            return aus
        except Exception as e:
            print(f"[prioritaeten_view] Überschneidungen: {e}")
            return {}

    # ── Liste bauen ───────────────────────────────────────────────────────────

    def gruppen_zahlen(self, funktionen=None) -> list[int]:
        """Die Zahlen aller gezeigten Gruppen, staerkste zuerst: die fuenf
        Stufen immer, eigene Zahlen nur, wenn ein Effekt sie traegt."""
        if funktionen is None:
            funktionen = self._funktionen()
        zahlen = {s.zahl for s in stufen.STUFEN}
        zahlen |= {stufen.zahl_von(getattr(f, "priority", 0)) for f in funktionen}
        return sorted(zahlen, reverse=True)

    def _melde_veraltet(self, *_a):
        self._veraltet = True
        try:
            self._neu_timer.start()
        except RuntimeError:
            pass

    def _neu_aufbauen_wenn_sichtbar(self):
        if self._veraltet and self.isVisible():
            self.neu_aufbauen()

    def showEvent(self, event):
        super().showEvent(event)
        if self._veraltet:
            self._neu_timer.start()

    def neu_aufbauen(self):
        """Liste aus den Funktionen neu bauen; Auswahl bleibt erhalten."""
        if self._baue:
            return
        self._baue = True
        try:
            self._veraltet = False
            gewaehlt = set(self.ausgewaehlte_ids())
            zugeklappt = set()
            wurzel = self._baum.invisibleRootItem()
            for i in range(wurzel.childCount()):
                it = wurzel.child(i)
                z = it.data(0, _ROLLE_ZAHL)
                if z is not None and not it.isExpanded():
                    zugeklappt.add(int(z))

            funktionen = self._funktionen()
            nachschlagen = self._kanal_attribut()
            mitglied = self._mitglied_von(funktionen)
            laufend = set(self._fm.running_ids())
            self._ueberschn = self._ueberschneidungs_tipps()    # ENG-39

            self._baum.blockSignals(True)
            self._baum.clear()

            fest = QTreeWidgetItem(self._baum, [stufen.SNAP_ZEILE, "fest", "", ""])
            fest.setFlags(Qt.ItemFlag.NoItemFlags)       # ausgegraut, nicht waehlbar
            fest.setToolTip(
                0, "Snap-Tasten der virtuellen Konsole und der Programmer liegen "
                   "immer über allen Stufen. Ausnahme: Treibt ein laufender "
                   "Effekt den Dimmer, behält er ihn — außer die Taste hat den "
                   "Haken „übersteuert laufende Dimmer-Effekte“.")
            for spalte in range(len(_SPALTEN)):
                fest.setForeground(spalte, QBrush(_GRAU))

            fett = QFont()
            fett.setBold(True)
            for zahl in self.gruppen_zahlen(funktionen):
                stufe = stufen.stufe_fuer_zahl(zahl)
                zeilen = [f for f in funktionen
                          if stufen.zahl_von(getattr(f, "priority", 0)) == zahl]
                zeilen.sort(key=lambda f: (str(getattr(f, "name", "")).lower(),
                                           getattr(f, "id", 0)))
                kopf = QTreeWidgetItem(self._baum, [
                    f"{stufen.stufen_name(zahl)}  ({len(zeilen)})", "", "", ""])
                kopf.setData(0, _ROLLE_ZAHL, zahl)
                kopf.setFont(0, fett)
                kopf.setFlags(Qt.ItemFlag.ItemIsEnabled
                              | Qt.ItemFlag.ItemIsDropEnabled)
                kopf.setToolTip(0, stufe.hinweis if stufe is not None else (
                    "Zahl aus einer älteren Show, die auf keine Stufe passt. "
                    "Sie bleibt erhalten, bis du die Effekte in eine Stufe legst."))
                for f in zeilen:
                    self._zeile(kopf, f, nachschlagen, mitglied,
                                f.id in laufend, f.id in gewaehlt)
                kopf.setExpanded(zahl not in zugeklappt)
        finally:
            self._baum.blockSignals(False)
            self._baue = False
        self._auswahl_geaendert()

    def _zeile(self, kopf, f, nachschlagen, mitglied, laeuft, gewaehlt):
        art = stufen.art_von(f)
        if stufen.ist_modify(f):
            art = f"{art} · {stufen.MODIFY_HINWEIS}"
        bausteine = stufen.bausteine_von(f, self._fm.get, nachschlagen)
        it = QTreeWidgetItem(kopf, [str(getattr(f, "name", "")), art,
                                    bausteine.text(), ""])
        it.setData(0, _ROLLE_FID, int(f.id))
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled)
        tipps = []
        if stufen.ist_modify(f):
            tipps.append("Modify-Effekt: rechnet NACH allen normalen Effekten "
                         "auf das fertige Bild. Die Stufe ordnet ihn nur unter "
                         "den Modify-Effekten ein.")
        if bausteine.unbekannt:
            tipps.append("Was dieser Effekt anfasst, lässt sich nicht "
                         "vollständig aus der Show ablesen.")
        if art.startswith("Kanal-Kopplung"):
            tipps.append("Kanal-Kopplung: liest die Bewegung der Effekte "
                         "darunter und muss deshalb nach ihnen rechnen.")
        if int(f.id) in mitglied:
            tipps.append("Läuft auch in: " + ", ".join(mitglied[int(f.id)])
                         + " — dort gilt deren Stufe, nicht diese.")
        tipps.extend(getattr(self, "_ueberschn", {}).get(int(f.id), ()))
        if tipps:
            for spalte in range(len(_SPALTEN)):
                it.setToolTip(spalte, "\n".join(tipps))
        self._setze_laufzustand(it, laeuft)
        if gewaehlt:
            it.setSelected(True)
        return it

    def _setze_laufzustand(self, it, laeuft: bool):
        it.setText(3, "● läuft" if laeuft else "")
        it.setForeground(3, QBrush(_BERNSTEIN))
        schrift = QFont()
        schrift.setBold(bool(laeuft))
        it.setFont(0, schrift)

    def _effekt_zeilen(self):
        wurzel = self._baum.invisibleRootItem()
        for i in range(wurzel.childCount()):
            kopf = wurzel.child(i)
            for j in range(kopf.childCount()):
                yield kopf.child(j)

    def _laufzustand_nachziehen(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        if self._veraltet:
            return
        laufend = set(self._fm.running_ids())
        for it in self._effekt_zeilen():
            fid = it.data(0, _ROLLE_FID)
            laeuft = fid in laufend
            if (it.text(3) != "") != laeuft:
                self._setze_laufzustand(it, laeuft)

    # ── Auswahl und Aendern ───────────────────────────────────────────────────

    def ausgewaehlte_ids(self) -> list[int]:
        aus = []
        for it in self._baum.selectedItems():
            fid = it.data(0, _ROLLE_FID)
            if fid is not None:
                aus.append(int(fid))
        return aus

    def waehle(self, ids) -> None:
        """Zeilen nach Funktions-ID auswaehlen (ersetzt die Auswahl)."""
        ids = {int(i) for i in ids}
        self._baum.clearSelection()
        for it in self._effekt_zeilen():
            if it.data(0, _ROLLE_FID) in ids:
                it.setSelected(True)

    def _ausgewaehlte_funktionen(self) -> list:
        return [f for f in (self._fm.get(i) for i in self.ausgewaehlte_ids())
                if f is not None]

    def _auswahl_geaendert(self):
        if self._baue:
            return
        fs = self._ausgewaehlte_funktionen()
        hat = bool(fs)
        self._btn_hoeher.setEnabled(hat and any(
            stufen.naechste_stufe(getattr(f, "priority", 0), +1) for f in fs))
        self._btn_tiefer.setEnabled(hat and any(
            stufen.naechste_stufe(getattr(f, "priority", 0), -1) for f in fs))
        self._ziel_combo.setEnabled(hat)
        if hat:
            zahlen = {stufen.zahl_von(getattr(f, "priority", 0)) for f in fs}
            if len(zahlen) == 1:
                self._ziel_combo.setze_zahl(next(iter(zahlen)))
            self._lbl_auswahl.setText(
                "1 Effekt ausgewählt" if len(fs) == 1
                else f"{len(fs)} Effekte ausgewählt")
        else:
            self._lbl_auswahl.setText("Kein Effekt ausgewählt")

    def auswahl_in_stufe(self, zahl: int) -> int:
        """Alle ausgewaehlten Effekte auf ``zahl`` legen — ein
        Rueckgaengig-Schritt. Liefert die Zahl der geaenderten Effekte."""
        fs = self._ausgewaehlte_funktionen()
        return setze_stufen([(f, int(zahl)) for f in fs])

    def _schieben(self, richtung: int) -> int:
        plan = []
        for f in self._ausgewaehlte_funktionen():
            ziel = stufen.naechste_stufe(getattr(f, "priority", 0), richtung)
            if ziel is not None:
                plan.append((f, ziel.zahl))
        return setze_stufen(plan)

    def _hoeher(self):
        self._schieben(+1)

    def _tiefer(self):
        self._schieben(-1)

    def _kontextmenue(self, pos):
        it = self._baum.itemAt(pos)
        if it is None or it.data(0, _ROLLE_FID) is None:
            return
        if not it.isSelected():
            self._baum.clearSelection()
            it.setSelected(True)
        menue = QMenu(self)
        for s in reversed(stufen.STUFEN):
            aktion = menue.addAction(f"In Stufe „{s.name}“")
            aktion.setData(s.zahl)
        gewaehlt = menue.exec(self._baum.viewport().mapToGlobal(pos))
        if gewaehlt is not None and gewaehlt.data() is not None:
            self.auswahl_in_stufe(int(gewaehlt.data()))
