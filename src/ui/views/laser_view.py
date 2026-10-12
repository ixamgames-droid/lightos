"""Laser View — Steuer-UI für DMX-Laser (LAS-02).

Eingebettet als Programmer-Tab (``follow_selection=True``), sichtbar nur wenn
die Auswahl Laser-Fixtures enthält (siehe ``fixture_has_laser_capability``).
Sektionen:

- **Mustergruppe A/B/A+B**: Laser wie der Ehaho L2600 doppeln ihre Kanäle für
  eine zweite Mustergruppe — im Patch als 2. Vorkommen derselben Attribute
  (Mehrkopf-Konvention, Kopf 0 = A, Kopf 1 = B / ``attr#1``).
- **Modus-Schnellwahl**: die Shutter-Ranges (Aus/Auto/Sound/Muster) als Kacheln.
- **Regler**: ein Range-beschrifteter Slider pro Laser-Kanal des Templates.
- **Muster-Paletten**: benannte Presets der Laser-Werte (``PaletteType.LASER``),
  gespeichert über die bestehende Palette-Engine (verwalten im Paletten-Tab).

LAS-34: liefert das Geräteprofil Laser-Angaben (``laser_profilangaben``:
Betriebsart, Musterliste, Farbtabelle, Richtungen), stehen statt der Regler
BAUSTEINE da — Sicherheitsleiste, Betriebsart-Umschalter, Vorschau & Position,
Muster-Galerie, Farbfelder, Regler mit sprechenden Enden, gemerkte Muster.
Jeder Baustein fällt EINZELN auf die bisherige Bedienung (Kacheln, Regler)
zurück, wenn das Profil dafür nichts sagt oder die gewählten Laser sich darin
unterscheiden. Kein Kanal geht dabei verloren (``bedienbare_attribute``).

Werte fließen ausschließlich über ``set_programmer_value(fid, attr, head=)`` —
kein eigener Render-Pfad. Laser-Safety: diese View schreibt nur auf explizite
Nutzeraktion; es gibt keinen Auto-Start.
"""
from __future__ import annotations

import html
import importlib
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSlider,
    QSpinBox, QComboBox, QPushButton, QRadioButton, QButtonGroup,
    QScrollArea, QGroupBox, QInputDialog, QFrame, QMenu, QToolButton,
)
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap

from src.core.app_state import get_state, get_channels_for_patched
from src.core.attr_groups import attr_label
from src.core.laser.capability import (laser_capability, LaserClass,
                                       is_laser_fixture)
from src.core.laser.profilangaben import FARBEN, laser_profilangaben
from src.ui.weak_slots import weak_slot, weak_slot_fwd
from src.ui.widgets.laser_tab_bausteine import (
    TOUCH, BetriebsartUmschalter, FarbFelder, LageAnzeige, LageFeld,
    MusterGalerie, SprechRegler, farbe_als_qt, lage_text, nebentext,
    ueberschrift)

# Nicht-``laser_*``-Attribute, die auf einem Laser-Fixture zur Laser-Steuerung
# gehören (Musterauswahl = gobo_wheel, Rotation = gobo_rotation usw.).
LASER_EXTRA_ATTRS = ("shutter", "gobo_wheel", "gobo_rotation", "zoom",
                     "color_wheel", "macro", "speed",
                     # LAS-VIEW (2026-08-05): Profi-Laser bringen einen ganz
                     # gewoehnlichen Master-Dimmer und RGB mit — der Pangolin
                     # FB4 hat `intensity`, `color_r/g/b` und `strobe`
                     # (fixture_db.py, 16ch UND 39ch), der PARTYLASER
                     # ebenfalls. Keines davon begann mit `laser_`, keines
                     # stand hier: sie erschienen damit weder in einer
                     # _ROW_GROUPS-Gruppe noch unter „Weitere Kanaele" (das
                     # baut sich ausschliesslich aus dem gefilterten Template).
                     # Praktisch war der MASTER-DIMMER eines FB4 auf der
                     # Laser-Seite nicht bedienbar — ausgerechnet der Regler,
                     # den man zuerst sucht.
                     "intensity", "color_r", "color_g", "color_b", "strobe",
                     # LAS-26: Mustergeschwindigkeit der Show-Laser
                     # (EL-400RGB MK2, ZQ-B370: „Dynamic Pattern Speed“) — fiel
                     # hier durch und war auf der Laser-Seite nicht bedienbar.
                     "effect_speed")

# LAS-11: Die Laser-Regler werden nach Bedeutung gruppiert statt als flache
# Kanal-Liste gezeigt — die WICHTIGEN Achsen (Muster, Farbe, Geschwindigkeit)
# prominent, die technischen Kanäle einklappbar. Reihenfolge = Anzeige.
# `shutter` steckt in den Modus-Kacheln, taucht hier NICHT auf.
_ROW_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Muster", ("gobo_wheel", "laser_bank")),
    # Helligkeit steht bewusst GANZ OBEN: Dimmer und Strobe sind das, was man
    # am Laser als Erstes braucht, und beim FB4 waren sie bis 2026-08-05 gar
    # nicht erreichbar.
    ("Helligkeit", ("intensity", "strobe")),
    ("Farbe", ("laser_color_change", "laser_color", "color_wheel",
               "color_r", "color_g", "color_b")),
    ("Bewegung & Geschwindigkeit",
     ("speed", "effect_speed", "laser_scan_rate", "gobo_rotation",
      "laser_x", "laser_y",
      "zoom", "laser_zoom_x", "laser_zoom_y")),
    ("Zeichnen", ("laser_draw_mode", "laser_draw")),
]
# Alles Übrige (laser_boundary, laser_twist, laser_grating, laser_dots, macro,
# raw, …) landet in der einklappbaren „Weitere Kanäle"-Gruppe.
_ADVANCED_GROUP = "Weitere Kanäle"
_GROUPED_ATTRS = frozenset(a for _n, attrs in _ROW_GROUPS for a in attrs)


# UI-89: Dimmer, RGB-Mischung und Strobe bedeuten an einem Laser dasselbe wie
# an jedem anderen Geraet. Ein Laser, der sie mitbringt, ist ein Kombi-Geraet
# und bekommt im Programmer zusaetzlich die allgemeinen Reiter (Intensity,
# Color, Matrix). Alles andere, was der Laser-Reiter fuehrt, ist auf einem
# Laser laser-eigen (``shutter`` = Betriebsart, ``gobo_wheel`` = Musterauswahl,
# ``zoom`` = Bildgroesse …) und zaehlt dort NICHT als Intensity/Gobo/Weitere.
LASER_KOMBI_ATTRS = frozenset(
    {"intensity", "color_r", "color_g", "color_b", "strobe"})


def im_laser_reiter(attr: str) -> bool:
    """True, wenn der Laser-Reiter dieses Attribut eines Lasers bedient —
    die EINE Regel fuer Regler-Aufbau, Kopf-Zaehlung und (UI-89) die
    Reiter-Sichtbarkeit des Programmers."""
    attr = attr or ""
    return attr.startswith("laser_") or attr in LASER_EXTRA_ATTRS


def nur_im_laser_reiter(attr: str) -> bool:
    """True fuer Attribute, die auf einem Laser allein in den Laser-Reiter
    gehoeren (siehe ``LASER_KOMBI_ATTRS``). Was hier False liefert, zaehlt
    auch bei einem Laser fuer die allgemeinen Reiter des Programmers — so
    verschwindet kein Kanal, den der Laser-Reiter nicht selbst traegt."""
    return im_laser_reiter(attr) and (attr or "") not in LASER_KOMBI_ATTRS


def fixture_has_laser_capability(fx) -> bool:
    """True, wenn das gepatchte Gerät als Laser steuerbar ist. Delegiert an den
    kanonischen Klassifikator (:func:`capability.is_laser_fixture`); der Name
    bleibt für die Programmer-Tab-Sichtbarkeit (programmer_view) erhalten."""
    return is_laser_fixture(fx)


# LAS-26: Spaltenbreiten der Regler-Zeilen (Beschriftung, Bereichs-Auswahl).
LABEL_BREITE = 170
BEREICH_BREITE = 230


def row_label(channel) -> str:
    """LAS-26: Beschriftung einer Regler-Zeile = Kanalname aus dem Profil.

    Vorher stand dort die allgemeine Attribut-Beschriftung — am Laser hiess
    die Musterauswahl „Gobo-Rad“ und die Farbsegmente „Muster-Farbwechsel“.
    Der Kanalname ist das, was im Handbuch steht. Ein Gruppen-Praefix
    („A: Musterauswahl“ beim L2600) faellt weg: die Zeile gilt je nach
    Mustergruppe fuer A, B oder beide. Ohne Namen bleibt die Attribut-
    Beschriftung."""
    import re
    attr = getattr(channel, "attribute", "") or ""
    name = (getattr(channel, "name", "") or "").strip()
    name = re.sub(r"^[A-Z]\d?:\s*", "", name)
    if not name or name == attr:
        return attr_label(attr)
    return name


def _range_value(rng) -> int:
    """Anfahr-Wert für einen ChannelRange: Punktbereich → der Wert selbst,
    Band → Bandmitte (liegt sicher im Bereich, egal wie die Grenzen fallen)."""
    lo = int(getattr(rng, "range_from", 0) or 0)
    hi = int(getattr(rng, "range_to", lo) or lo)
    return lo if lo == hi else (lo + hi) // 2


def _sorted_ranges(ch) -> list:
    return sorted(getattr(ch, "ranges", None) or (),
                  key=lambda r: int(getattr(r, "range_from", 0) or 0))


# ── LAS-34: Bausteine aus den Profilangaben ─────────────────────────────────

#: Regler der rechten Spalte: Attribut -> (Titel, Zusatz, Zusatz OHNE
#: Richtungsangabe, eigene Worte fuer die Enden). Sie stehen dort nur, wenn das
#: Profil ueberhaupt Laser-Angaben macht; mit ``Richtung`` laufen sie richtig
#: herum und tragen sprechende Enden, ohne sind es gewoehnliche Regler 0..255
#: — und es steht dabei, dass das Profil die Richtung nicht nennt.
OHNE_RICHTUNG = "Richtung nicht im Profil"
SPRECH_REGLER: tuple[tuple[str, str, str, str, dict | None], ...] = (
    ("zoom", "Größe", "", OHNE_RICHTUNG, None),
    # Das Zeichentempo ist die Scangeschwindigkeit: langsam heisst hier „ruhig“.
    ("laser_scan_rate", "Zeichentempo", "", OHNE_RICHTUNG,
     {"langsam": "ruhig"}),
    ("effect_speed", "Mustertempo", "nur bei dynamischen Mustern",
     "nur bei dynamischen Mustern", None),
    ("laser_color_change", "Farbsegmente", "", "Profil ohne Stufen", None),
)

#: Modul der Sperrzonen-Anzeige (LAS-32). Auf einem Stand ohne diese Funktion
#: gibt es das Modul nicht — dann bleibt das Abzeichen der Sicherheitsleiste
#: weg. Bewusst KEIN Import am Dateianfang.
SPERRZONEN_MODUL = "src.core.laser.sperrzonen"
NUR_ANZEIGE = "Nur Anzeige · schaltet nicht ab"
#: Meldung je Laser (LAS-32) und Planer (LAS-35) — ebenfalls nur als Text
#: genannt und erst zur Laufzeit gesucht: fehlt eines der Module, fehlt im
#: Tab genau das zugehoerige Bedienelement (kein toter Knopf).
SPERRZONEN_UI_MODUL = "src.ui.visualizer.sperrzonen_ui"
SPERRZONEN_PLANER_MODUL = "src.ui.visualizer.sperrzonen_planer"


def _modul_oder_none(name: str):
    """Das Modul ``name`` oder ``None``, wenn es auf diesem Stand fehlt
    oder sich nicht laden laesst."""
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def sperrzonen_hinweis(state, fids) -> tuple[str, str] | None:
    """Schnittstelle zur Sperrzonen-Anzeige: ``(Kurztext, Einzelheiten)`` fuer
    die gewaehlten Laser — oder ``None``, wenn es nichts zu sagen gibt oder
    die Funktion auf diesem Stand fehlt.

    Der Text ist ein HINWEIS. Die Sperrzonen sind eine reine Anzeige; sie
    schalten keinen Laser ab und ersetzen keinen Laserschutz."""
    try:
        modul = importlib.import_module(SPERRZONEN_MODUL)
        kopf, befunde = modul.state_befunde(state)
    except Exception:
        return None
    try:
        frei = getattr(modul, "STATUS_FREI", "frei")
        fids = {int(f) for f in fids}
        eigene = [b for b in befunde if int(getattr(b, "fid", -1)) in fids
                  and getattr(b, "status", frei) != frei]
        if eigene:
            wort = "Hinweis" if len(eigene) == 1 else "Hinweise"
            return (f"⚠ Sperrzonen: {len(eigene)} {wort}",
                    "\n".join(str(getattr(b, "text", "")) for b in eigene))
        if kopf and not befunde:
            return str(kopf), str(kopf)
    except Exception as e:
        print(f"[laser_view] Sperrzonen-Hinweis: {e}")
    return None


@dataclass
class _Plan:
    """Welche Bausteine die Auswahl bekommt (``None``/leer = Rueckfall auf die
    bisherige Bedienung dieses Teils)."""
    betriebsart: object = None      # KanalAngaben mit .betriebsart
    muster: object = None           # KanalAngaben mit .muster
    farben: object = None           # KanalAngaben mit .farben
    lage: tuple | None = None       # (Richtung laser_x, Richtung laser_y)
    regler: tuple = ()              # ((Attribut, Richtung | None), …)

    @property
    def neu(self) -> bool:
        return bool(self.betriebsart or self.muster or self.farben
                    or self.lage or self.regler)

    def abgedeckt(self) -> set[str]:
        """Attribute, die ein Baustein bedient (statt einer Regler-Zeile)."""
        out = {a for a, _r in self.regler}
        for k in (self.betriebsart, self.muster, self.farben):
            if k is not None:
                out.add(k.attribut)
        if self.lage is not None:
            out |= {"laser_x", "laser_y"}
        return out

    def kennung(self) -> str:
        return repr((self.betriebsart, self.muster, self.farben, self.lage,
                     self.regler))


_MODELL_NAMEN: dict[int, str] = {}


def _modell_name(fx) -> str:
    """Modellname eines gepatchten Lasers (aus dem Profil; je Profil einmal
    nachgeschlagen)."""
    pid = getattr(fx, "fixture_profile_id", None)
    if pid is None:
        return str(getattr(fx, "fixture_name", None)
                   or getattr(fx, "name", None) or "")
    if pid not in _MODELL_NAMEN:
        name = ""
        try:
            from sqlalchemy.orm import Session
            from src.core.database.fixture_db import engine
            from src.core.database.models import FixtureProfile
            with Session(engine()) as s:
                prof = s.get(FixtureProfile, int(pid))
                name = str(getattr(prof, "name", "") or "")
        except Exception as e:
            print(f"[laser_view] Modellname nicht lesbar: {e}")
        _MODELL_NAMEN[pid] = name
    return _MODELL_NAMEN[pid]


def farb_name(farbe) -> str:
    """Anzeigename einer Farbe der Farbtabelle („gruen“ -> „Grün“)."""
    name = (getattr(farbe, "name", "") or "").strip()
    bekannt = FARBEN.get(name.casefold())
    if bekannt is not None:
        return bekannt[0]
    return name[:1].upper() + name[1:]


class _ChannelRow(QWidget):
    """Eine Regler-Zeile: Label + Slider + Spin + Range-Auswahl (ComboBox).

    ``kompakt`` (LAS-34): nur Schieber und Zahlenfeld — die Zeile hinter
    „alle 0–255“ unter der Muster-Galerie bzw. den Farbfeldern."""

    def __init__(self, channel, on_change, parent=None, kompakt: bool = False):
        super().__init__(parent)
        self.attribute = channel.attribute
        self._on_change = on_change
        self._ranges = _sorted_ranges(channel)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl = QLabel(row_label(channel))
        # LAS-26: feste Spaltenbreiten — vorher sass jeder Regler je nach
        # Namens- und Bereichslaenge woanders, die Zeilen fluchteten nicht.
        lbl.setFixedWidth(LABEL_BREITE)
        lbl.setWordWrap(True)
        lbl.setToolTip(f"{attr_label(self.attribute)} ({self.attribute})")
        lay.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 255)
        lay.addWidget(self._slider, stretch=1)

        self._spin = QSpinBox()
        self._spin.setRange(0, 255)
        self._spin.setFixedWidth(56)
        lay.addWidget(self._spin)

        self._combo = QComboBox()
        self._combo.setFixedWidth(BEREICH_BREITE)
        # Ohne Bereiche bleibt der Platz frei (Regler gleich lang wie die
        # Nachbarzeilen).
        pol = self._combo.sizePolicy()
        pol.setRetainSizeWhenHidden(True)
        self._combo.setSizePolicy(pol)
        self._combo.addItem("— Bereich wählen —", None)
        for r in self._ranges:
            lo = int(getattr(r, "range_from", 0) or 0)
            hi = int(getattr(r, "range_to", lo) or lo)
            name = getattr(r, "name", "") or f"{lo}-{hi}"
            self._combo.addItem(f"{lo}-{hi}  {name}", _range_value(r))
        self._combo.setVisible(bool(self._ranges))
        lay.addWidget(self._combo)
        if kompakt:
            lbl.setVisible(False)
            pol.setRetainSizeWhenHidden(False)
            self._combo.setSizePolicy(pol)
            self._combo.setVisible(False)

        self._slider.valueChanged.connect(self._slider_changed)
        self._spin.valueChanged.connect(self._spin_changed)
        self._combo.currentIndexChanged.connect(self._combo_changed)

    # -- interne Sync-Helfer (Signale beim Spiegeln blocken) ------------------
    def _sync_widgets(self, value: int):
        for w in (self._slider, self._spin):
            w.blockSignals(True)
            w.setValue(value)
            w.blockSignals(False)
        self._combo.blockSignals(True)
        idx = 0
        for i, r in enumerate(self._ranges, start=1):
            lo = int(getattr(r, "range_from", 0) or 0)
            hi = int(getattr(r, "range_to", lo) or lo)
            if lo <= value <= hi:
                idx = i
                break
        self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

    def _emit(self, value: int):
        self._sync_widgets(value)
        self._on_change(self.attribute, value)

    def _slider_changed(self, v: int):
        self._emit(int(v))

    def _spin_changed(self, v: int):
        self._emit(int(v))

    def _combo_changed(self, _idx: int):
        val = self._combo.currentData()
        if val is not None:
            self._emit(int(val))

    def set_value(self, value: int):
        """Wert von außen anzeigen (ohne zu schreiben)."""
        self._sync_widgets(max(0, min(255, int(value))))


class _PatternTile(QWidget):
    """Werksmuster-Kachel (LAS-18b): Nutzer-Foto als Vorschau oder — solange
    keins zugewiesen ist — eine nummerierte Kachel (Bank/Muster-Wert). Links-
    klick ruft das Muster ab, Rechtsklick löscht den Slot. Plain-Callbacks
    statt Qt-Signalen (kein STAB-09-Pin über die C++-Connection)."""

    W, H = 92, 88

    def __init__(self, slot, on_click, on_delete, parent=None):
        super().__init__(parent)
        self._slot = slot
        self._on_click = on_click        # callback(slot)
        self._on_delete = on_delete      # callback(slot)
        self._pm = None
        path = getattr(slot, "image_path", "") or ""
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                self._pm = pm.scaled(
                    self.W - 8, self.H - 26,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{slot.label}  (Bank {slot.bank} / Muster "
                        f"{slot.pattern})\nLinksklick: abrufen · "
                        "Rechtsklick: Slot löschen")

    def paintEvent(self, event):  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#161b22"))
        p.setPen(QPen(QColor("#30363d"), 1))
        thumb = QRect(4, 4, self.W - 8, self.H - 26)
        p.drawRect(thumb.adjusted(-1, -1, 0, 0))
        if self._pm is not None:
            p.setClipRect(thumb)
            p.drawPixmap(thumb.topLeft(), self._pm)
            p.setClipping(False)
        else:
            # Kein Foto: dunkle Kachel mit Bank/Muster-Nummer.
            p.fillRect(thumb, QColor("#0d1117"))
            p.setPen(QColor("#7d8590"))
            f = QFont(); f.setPixelSize(13); f.setBold(True); p.setFont(f)
            p.drawText(thumb, Qt.AlignmentFlag.AlignCenter,
                       f"B{self._slot.bank}\nM{self._slot.pattern}")
        p.setPen(QColor("#c9d1d9"))
        f = QFont(); f.setPixelSize(10); p.setFont(f)
        name = self._slot.label
        p.drawText(QRect(0, self.H - 20, self.W, 16),
                   Qt.AlignmentFlag.AlignCenter,
                   name[:13] + ("…" if len(name) > 13 else ""))
        p.end()

    def mousePressEvent(self, ev):  # noqa: N802 (Qt-API)
        if ev is not None and ev.button() == Qt.MouseButton.RightButton:
            if self._on_delete is not None:
                self._on_delete(self._slot)
        elif self._on_click is not None:
            self._on_click(self._slot)


class LaserView(QWidget):
    """Laser-Steuerseite (Programmer-Tab). Arbeitet auf der Programmer-Auswahl."""

    def __init__(self, parent=None, follow_selection: bool = False):
        super().__init__(parent)
        self._follow = bool(follow_selection)
        self._fixtures: list = []
        self._network_fids: list[int] = []
        self._rows: dict[str, _ChannelRow] = {}
        self._collapsible_groups: dict[str, list[str]] = {}
        self._template_sig: tuple = ()
        self._head_mode: str = "A"          # "A" | "B" | "AB"
        # LAS-34: aktive Bausteine und ihre Regler.
        self._plan = _Plan()
        self._sprech: dict[str, SprechRegler] = {}
        self._kanal_je_attr: dict[str, object] = {}

        self._build_ui()
        self._subscribe()
        self.refresh_from_selection()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 6)
        root.setSpacing(8)

        self._info = QLabel("Kein Laser in der Auswahl.")
        self._info.setStyleSheet("color:#8b949e;")
        root.addWidget(self._info)

        # ── Sicherheit (Netzwerk-Streaming-Laser) ─────────────────────────
        # Scharfschalten + Not-Aus + Framequelle. Nur sichtbar, wenn ein
        # Netzwerk-Laser (Ether Dream / IDN) in der Auswahl ist — DMX-Laser
        # geben über die normale DMX-Pipeline aus, nicht über den Streamer.
        self._safety_box = QGroupBox("Laser-Ausgabe (Netzwerk)")
        sb = QVBoxLayout(self._safety_box)
        arm_row = QHBoxLayout()
        self._btn_arm = QPushButton("🔒 UNSCHARF — Ausgabe geblockt")
        self._btn_arm.setCheckable(True)
        self._btn_arm.setMinimumHeight(40)
        # toggled(bool) traegt den Zustand — weak_slot WUERDE ihn verwerfen und
        # der Slot stuerbe mit TypeError, ohne je set_armed() zu erreichen.
        self._btn_arm.toggled.connect(weak_slot_fwd(self._on_arm_toggled))
        arm_row.addWidget(self._btn_arm, stretch=1)
        self._btn_estop = QPushButton("⏹ NOT-AUS")
        self._btn_estop.setMinimumHeight(40)
        self._btn_estop.setStyleSheet(
            "QPushButton{background:#8b0000;color:#fff;font-weight:bold;"
            "border:1px solid #b30000;border-radius:5px;padding:6px 14px;}"
            "QPushButton:hover{background:#b30000;}")
        self._btn_estop.clicked.connect(weak_slot(self._on_estop))
        arm_row.addWidget(self._btn_estop)
        sb.addLayout(arm_row)
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Ausgabe:"))
        self._combo_figure = QComboBox()
        # weak_slot verwirft den Index — den braucht der Slot auch nicht.
        self._combo_figure.currentIndexChanged.connect(
            weak_slot(self._on_figure_changed))
        src_row.addWidget(self._combo_figure, stretch=1)
        self._btn_draw = QPushButton("✏️ Zeichnen…")
        self._btn_draw.setToolTip("Eigenes Laser-Muster zeichnen (Punkte, "
                                  "Farben) — live sichtbar bei scharfem Laser.")
        self._btn_draw.clicked.connect(weak_slot(self._on_draw))
        src_row.addWidget(self._btn_draw)
        sb.addLayout(src_row)
        self._rebuild_figure_combo()
        self._arm_hint = QLabel(
            "Beim Scharfschalten tritt echtes Laserlicht aus. "
            "Publikum/Augen schützen, Not-Aus bereithalten.")
        self._arm_hint.setWordWrap(True)
        self._arm_hint.setStyleSheet("color:#8b949e;font-size:10px;")
        sb.addWidget(self._arm_hint)
        root.addWidget(self._safety_box)
        self._update_arm_button()

        # LAS-34: Sicherheitsleiste — EINE Zeile statt der beiden Kaesten
        # „Laser-Sicherheit“ und „Sperrzonen“. Links der Zustand (Laser AN/AUS
        # laut Betriebsart bzw. NOT-AUS aktiv, Modell, Anzahl), rechts das
        # Sperrzonen-Abzeichen (nur wo es die Funktion gibt) und der NOT-AUS.
        # Der Knopf geht denselben Weg wie bisher (``_on_estop``): ``estop_all``
        # setzt den DMX-Latch (UXT-12) und verriegelt die Netzwerk-Ausgabe.
        # Die Namen ``_dmx_safety_box``/``_btn_dmx_estop``/``_lbl_dmx_estop``
        # bleiben (LAS-26) — sichtbar ist die Leiste, sobald ein DMX-Laser in
        # der Auswahl ist.
        self._dmx_safety_box = QFrame()
        self._dmx_safety_box.setObjectName("laserSicherheitsleiste")
        self._dmx_safety_box.setStyleSheet(
            "#laserSicherheitsleiste{background:#1c1c1c;border:1px solid "
            "#3a3a3a;border-radius:4px;}")
        self._dmx_safety_box.setFixedHeight(44)
        dsb = QHBoxLayout(self._dmx_safety_box)
        dsb.setContentsMargins(12, 0, 4, 0)
        dsb.setSpacing(8)
        self._zustand_punkt = QLabel()
        self._zustand_punkt.setFixedSize(10, 10)
        dsb.addWidget(self._zustand_punkt)
        self._lbl_dmx_estop = QLabel("")
        dsb.addWidget(self._lbl_dmx_estop)
        self._lbl_modell = QLabel("")
        self._lbl_modell.setStyleSheet("color:#8b949e;background:transparent;")
        dsb.addWidget(self._lbl_modell)
        dsb.addStretch(1)
        self._sperrzonen_abzeichen = QLabel("")
        self._sperrzonen_abzeichen.setTextFormat(Qt.TextFormat.RichText)
        self._sperrzonen_abzeichen.setFixedHeight(TOUCH)
        self._sperrzonen_abzeichen.setStyleSheet(
            "QLabel{background:#2e2600;border:1px solid #f0c000;color:#f0c000;"
            "border-radius:18px;padding:0 11px;font-size:12px;}")
        self._sperrzonen_abzeichen.setVisible(False)
        dsb.addWidget(self._sperrzonen_abzeichen)
        # LAS-32/LAS-35 im neuen Tab: die Meldung je Laser klappt unter der
        # Leiste auf (zu = der Tab passt weiter ohne Scrollen), der Planer
        # hat einen eigenen Knopf. Beide gibt es nur, wenn ihr Modul da ist.
        self._btn_sperrzonen_details = QToolButton()
        self._btn_sperrzonen_details.setObjectName("laserSperrzonenDetails")
        self._btn_sperrzonen_details.setText("Meldung ▾")
        self._btn_sperrzonen_details.setCheckable(True)
        self._btn_sperrzonen_details.setFixedHeight(TOUCH)
        self._btn_sperrzonen_details.setToolTip(
            "Sperrzonen-Meldung je Laser ein- oder ausblenden. "
            f"{NUR_ANZEIGE}. Kein Laserschutz.")
        self._btn_sperrzonen_details.toggled.connect(
            weak_slot_fwd(self._sperrzonen_details_zeigen))
        self._btn_sperrzonen_details.setVisible(False)
        dsb.addWidget(self._btn_sperrzonen_details)
        self._btn_sperrzonen_planen = QPushButton("Sperrzonen planen…")
        self._btn_sperrzonen_planen.setObjectName("laserSperrzonenPlanen")
        self._btn_sperrzonen_planen.setFixedHeight(TOUCH)
        self._btn_sperrzonen_planen.setToolTip(
            "Öffnet den Planer: Zonen ziehen, Laser-Felder eintragen oder "
            f"einmessen. {NUR_ANZEIGE}. Kein Laserschutz.")
        self._btn_sperrzonen_planen.clicked.connect(
            weak_slot(self._sperrzonen_planer_oeffnen))
        self._btn_sperrzonen_planen.setVisible(
            _modul_oder_none(SPERRZONEN_PLANER_MODUL) is not None)
        dsb.addWidget(self._btn_sperrzonen_planen)
        self._btn_dmx_estop = QPushButton("■ LASER NOT-AUS")
        self._btn_dmx_estop.setFixedHeight(TOUCH)
        self._btn_dmx_estop.setMinimumWidth(138)
        self._btn_dmx_estop.setStyleSheet(
            "QPushButton{background:#8b0000;color:#fff;font-weight:bold;"
            "border:1px solid #d02020;border-radius:3px;padding:0 12px;}"
            "QPushButton:hover{background:#b30000;}")
        self._btn_dmx_estop.setToolTip(
            "Schaltet ALLE Laser sofort dunkel: DMX-Laser auf ihren Aus-Wert "
            "(bis Betriebsart oder Muster neu gewählt wird), Netzwerk-Laser "
            "werden unscharf. Blackout und Grand Master 0 schalten ebenfalls "
            "über den Aus-Wert der Betriebsart dunkel.")
        self._btn_dmx_estop.clicked.connect(weak_slot(self._on_estop))
        dsb.addWidget(self._btn_dmx_estop)
        self._dmx_safety_box.setVisible(False)
        root.addWidget(self._dmx_safety_box)

        # LAS-32 (S1): Sperrzonen-Meldung je Laser — nur Anzeige, schaltet
        # nichts ab. Das Widget kommt aus der Sperrzonen-Bedienung (weich
        # angebunden, s. SPERRZONEN_UI_MODUL) und liegt eingeklappt unter der
        # Sicherheitsleiste; „Meldung ▾“ klappt es auf. Es blendet sich selbst
        # aus, wenn es nichts zu sagen hat — darum steckt es in einem eigenen
        # Rahmen, dessen Sichtbarkeit allein der Knopf bestimmt.
        self._sperrzonen_details = QWidget()
        sdl = QVBoxLayout(self._sperrzonen_details)
        sdl.setContentsMargins(0, 0, 0, 0)
        self._sperrzonen_hinweis = None
        ui_modul = _modul_oder_none(SPERRZONEN_UI_MODUL)
        if ui_modul is not None:
            try:
                self._sperrzonen_hinweis = ui_modul.SperrzonenHinweis(
                    get_state(), self._sperrzonen_details)
                sdl.addWidget(self._sperrzonen_hinweis)
            except Exception as e:                       # noqa: BLE001
                self._sperrzonen_hinweis = None
                print(f"[laser_view] Sperrzonen-Hinweis: {e}")
        self._btn_sperrzonen_details.setVisible(
            self._sperrzonen_hinweis is not None)
        self._sperrzonen_details.setVisible(False)
        root.addWidget(self._sperrzonen_details)

        # Mustergruppe (Kopf 0/1) — nur sichtbar, wenn das Gerät doppelte
        # Laser-Attribute hat (z. B. L2600 34ch: Gruppe A + B).
        self._head_box = QGroupBox("Mustergruppe")
        hb = QHBoxLayout(self._head_box)
        self._head_group = QButtonGroup(self)
        for label, key in (("Gruppe A", "A"), ("Gruppe B", "B"),
                           ("A + B", "AB")):
            rb = QRadioButton(label)
            rb.setChecked(key == "A")
            self._head_group.addButton(rb)
            rb.toggled.connect(weak_slot_fwd(self._on_head_mode_toggled, key))
            hb.addWidget(rb)
        hb.addStretch(1)
        root.addWidget(self._head_box)

        # LAS-34: Betriebsart als Umschalter (Segmente aus den Profilangaben).
        # Daneben der Hinweis, wenn das Gerät selbst läuft (Musik/Auto).
        self._seg_box = QWidget()
        sgl = QVBoxLayout(self._seg_box)
        sgl.setContentsMargins(0, 0, 0, 0)
        sgl.setSpacing(4)
        seg_kopf = QHBoxLayout()
        seg_kopf.addWidget(ueberschrift("Betriebsart"))
        self._lbl_gesperrt = QLabel(
            "Gerät läuft selbst — Muster, Lage und Farbe wirken in dieser "
            "Betriebsart nicht.")
        self._lbl_gesperrt.setStyleSheet(
            "color:#f0c000;font-size:11px;background:transparent;")
        self._lbl_gesperrt.setVisible(False)
        seg_kopf.addStretch(1)
        seg_kopf.addWidget(self._lbl_gesperrt)
        sgl.addLayout(seg_kopf)
        self._umschalter = BetriebsartUmschalter(self._betriebsart_gewaehlt)
        sgl.addWidget(self._umschalter)
        self._seg_box.setVisible(False)
        root.addWidget(self._seg_box)

        # Betriebsart-Schnellwahl (Shutter-Ranges als Kacheln: Aus/Auto/Sound/
        # Muster-an) — die bisherige Bedienung, wenn das Profil keine
        # Betriebsart-Angaben macht. Bewusst „Betriebsart", damit „Muster"
        # eindeutig die Musterauswahl meint (nicht den Shutter-Modus).
        self._mode_box = QGroupBox("Betriebsart")
        self._mode_lay = QHBoxLayout(self._mode_box)
        self._mode_lay.setSpacing(6)
        root.addWidget(self._mode_box)

        # LAS-34: die drei Spalten der Bausteine.
        self._bausteine = self._baue_bausteine()

        # Muster-Paletten (PaletteType.LASER) — Anlegen hier, Verwalten im
        # Paletten-Tab. Mit Bausteinen stehen sie als „Gemerkte Muster“ in der
        # mittleren Spalte (dieselbe Ablage); dieser Kasten ist der Rückfall.
        self._pal_box = QGroupBox("Muster-Paletten")
        pv = QVBoxLayout(self._pal_box)
        self._pal_grid = QGridLayout()
        self._pal_grid.setSpacing(6)
        pv.addLayout(self._pal_grid)
        pal_btns = QHBoxLayout()
        btn_save = QPushButton("💾 Muster speichern…")
        btn_save.setToolTip("Aktuelle Laser-Werte der Auswahl als benanntes "
                            "Muster ablegen (Verwalten im Paletten-Tab).")
        btn_save.clicked.connect(self._save_palette)
        pal_btns.addWidget(btn_save)
        pal_btns.addStretch(1)
        pv.addLayout(pal_btns)

        # LAS-18b: Werksmuster-Picker für DMX-Muster-Laser (Klasse A) — vom
        # Nutzer gemerkte (Bank, Muster)-Slots als Kacheln, optional mit Foto
        # vom realen Laser-Output (die Werksmuster sind herstellerseitig
        # unbenannt; die Vorschau-Bibliothek baut sich der Nutzer selbst).
        self._pattern_box = QGroupBox("Werksmuster (Gerät)")
        pat_v = QVBoxLayout(self._pattern_box)
        self._pattern_grid = QGridLayout()
        self._pattern_grid.setSpacing(6)
        pat_v.addLayout(self._pattern_grid)
        pat_btns = QHBoxLayout()
        btn_pat_add = QPushButton("➕ Muster merken…")
        btn_pat_add.setToolTip(
            "Aktuelle Bank-/Muster-Werte als Werksmuster-Slot merken — mit "
            "Name und optionalem Foto vom Laser-Output (Rechtsklick auf eine "
            "Kachel löscht sie).")
        btn_pat_add.clicked.connect(self._add_pattern_slot)
        pat_btns.addWidget(btn_pat_add)
        pat_btns.addStretch(1)
        pat_v.addLayout(pat_btns)

        # Scrollbereich: Bausteine, darunter die Regler (alles, was kein
        # Baustein bedient), Muster-Paletten und Werksmuster. LAS-26: die
        # Regler stehen VOR den Paletten. LAS-34: mit Bausteinen passt der
        # Inhalt ohne Rollen; der Scrollbereich fängt nur auf, was ein Profil
        # darüber hinaus mitbringt.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inhalt = QWidget()
        inhalt_lay = QVBoxLayout(inhalt)
        inhalt_lay.setContentsMargins(0, 0, 0, 0)
        inhalt_lay.setSpacing(6)
        inhalt_lay.addWidget(self._bausteine)
        self._rows_host = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(4)
        self._rows_lay.addStretch(1)
        inhalt_lay.addWidget(self._rows_host)
        inhalt_lay.addWidget(self._pal_box)
        inhalt_lay.addWidget(self._pattern_box)
        inhalt_lay.addStretch(1)
        scroll.setWidget(inhalt)
        self._scroll = scroll
        root.addWidget(scroll, stretch=1)

    def _baue_bausteine(self) -> QWidget:
        """LAS-34: Vorschau & Position | Muster + gemerkte Muster | Farbe +
        Regler. Jede Spalte bzw. jeder Teil ist einzeln ausblendbar."""
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(15)

        # ── Spalte 1: Vorschau & Position ────────────────────────────────
        self._lage_box = QWidget()
        l1 = QVBoxLayout(self._lage_box)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(5)
        kopf = QHBoxLayout()
        kopf.addWidget(ueberschrift("Vorschau & Position"))
        kopf.addStretch(1)
        self._lbl_lage_hinweis = nebentext("ziehen zum Verschieben")
        kopf.addWidget(self._lbl_lage_hinweis)
        l1.addLayout(kopf)
        self._lage_feld = LageFeld(self._lage_gezogen)
        l1.addWidget(self._lage_feld)
        fuss = QHBoxLayout()
        fuss.setContentsMargins(0, 0, 16, 0)
        fuss.setSpacing(6)
        self._lage_x = LageAnzeige("X")
        self._lage_y = LageAnzeige("Y")
        fuss.addWidget(self._lage_x, stretch=1)
        fuss.addWidget(self._lage_y, stretch=1)
        self._btn_mitte = QPushButton("Mitte")
        self._btn_mitte.setFixedSize(60, TOUCH)
        self._btn_mitte.setToolTip("Lage zurück in die Mitte.")
        self._btn_mitte.clicked.connect(weak_slot(self._lage_mitte))
        fuss.addWidget(self._btn_mitte)
        l1.addLayout(fuss)
        l1.addStretch(1)
        self._lage_box.setFixedWidth(LageFeld.SEITE + 16)
        lay.addWidget(self._lage_box)

        # ── Spalte 2: Muster-Galerie + gemerkte Muster ───────────────────
        self._spalte_muster = QWidget()
        l2 = QVBoxLayout(self._spalte_muster)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(5)
        self._muster_box = QWidget()
        mb = QVBoxLayout(self._muster_box)
        mb.setContentsMargins(0, 0, 0, 0)
        mb.setSpacing(5)
        kopf = QHBoxLayout()
        kopf.addWidget(ueberschrift("Muster"))
        kopf.addStretch(1)
        self._lbl_muster_zahl = nebentext("")
        kopf.addWidget(self._lbl_muster_zahl)
        self._btn_muster_alle = self._alle_knopf(self._muster_alle_umschalten)
        kopf.addWidget(self._btn_muster_alle)
        mb.addLayout(kopf)
        self._galerie = MusterGalerie(self._muster_gewaehlt)
        mb.addWidget(self._galerie)
        self._muster_alle_host = QWidget()
        mah = QVBoxLayout(self._muster_alle_host)
        mah.setContentsMargins(0, 0, 0, 0)
        self._muster_alle_host.setVisible(False)
        mb.addWidget(self._muster_alle_host)
        l2.addWidget(self._muster_box)

        self._gemerkt_box = QWidget()
        gb = QVBoxLayout(self._gemerkt_box)
        gb.setContentsMargins(0, 6, 0, 0)
        gb.setSpacing(5)
        gb.addWidget(ueberschrift("Gemerkte Muster"))
        self._gemerkt_lay = QHBoxLayout()
        self._gemerkt_lay.setSpacing(4)
        gb.addLayout(self._gemerkt_lay)
        l2.addWidget(self._gemerkt_box)
        self._lbl_schema = nebentext(
            "Musterbilder sind Schemazeichnungen aus dem Geräteprofil — am "
            "Gerät kann es anders aussehen.")
        self._lbl_schema.setWordWrap(True)
        l2.addWidget(self._lbl_schema)
        l2.addStretch(1)
        self._spalte_muster.setFixedWidth(296)
        lay.addWidget(self._spalte_muster)

        # ── Spalte 3: Farbe + Regler ─────────────────────────────────────
        self._spalte_farbe = QWidget()
        l3 = QVBoxLayout(self._spalte_farbe)
        l3.setContentsMargins(0, 0, 0, 0)
        l3.setSpacing(3)
        self._farbe_box = QWidget()
        fb = QVBoxLayout(self._farbe_box)
        fb.setContentsMargins(0, 0, 0, 0)
        fb.setSpacing(4)
        kopf = QHBoxLayout()
        kopf.addWidget(ueberschrift("Farbe"))
        kopf.addStretch(1)
        self._lbl_farbe = QLabel("")
        self._lbl_farbe.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_farbe.setStyleSheet("font-size:11px;background:transparent;")
        kopf.addWidget(self._lbl_farbe)
        self._btn_farbe_alle = self._alle_knopf(self._farbe_alle_umschalten)
        kopf.addWidget(self._btn_farbe_alle)
        fb.addLayout(kopf)
        self._farbfelder = FarbFelder(self._farbe_gewaehlt)
        fb.addWidget(self._farbfelder)
        self._farbe_alle_host = QWidget()
        fah = QVBoxLayout(self._farbe_alle_host)
        fah.setContentsMargins(0, 0, 0, 0)
        self._farbe_alle_host.setVisible(False)
        fb.addWidget(self._farbe_alle_host)
        # Farbe und Helligkeit bleiben getrennt — das steht dabei.
        fb.addWidget(nebentext("Farbe ändert die Helligkeit nicht."))
        l3.addWidget(self._farbe_box)
        self._regler_box = QWidget()
        self._regler_lay = QVBoxLayout(self._regler_box)
        self._regler_lay.setContentsMargins(0, 0, 0, 0)
        self._regler_lay.setSpacing(4)
        l3.addWidget(self._regler_box)
        l3.addStretch(1)
        self._spalte_farbe.setFixedWidth(308)
        lay.addWidget(self._spalte_farbe)
        lay.addStretch(1)
        host.setVisible(False)
        return host

    def _alle_knopf(self, slot) -> QToolButton:
        """„alle 0–255“: klappt den bisherigen Regler auf — für Werte, zu
        denen das Profil keinen Eintrag hat."""
        btn = QToolButton()
        btn.setText("alle 0–255 ▸")
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("QToolButton{color:#6ab0ff;font-size:11px;border:0;"
                          "background:transparent;padding:0 0 0 4px;}")
        btn.setToolTip("Den Regler 0–255 aufklappen — für Werte, zu denen "
                       "das Profil keinen Eintrag hat.")
        btn.toggled.connect(weak_slot_fwd(slot))
        return btn

    def _subscribe(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            if self._follow:
                sync.subscribe_widget(SyncEvent.SELECTION_CHANGED, self,
                                      lambda *_: self._on_selection_changed())
            sync.subscribe_widget(SyncEvent.PALETTE_CHANGED, self,
                                  lambda *_: self._rebuild_palettes())
            sync.subscribe_widget(SyncEvent.SHOW_LOADED, self,
                                  lambda *_: self._on_show_loaded())
            # LAS-10: Scharf/Unscharf-Änderung von VC/MIDI sofort spiegeln —
            # sonst könnte der Safety-Indikator stale „unscharf" zeigen, während
            # der Laser scharf ist (Täuschung in die gefährliche Richtung).
            sync.subscribe_widget(SyncEvent.LASER_ARMED_CHANGED, self,
                                  lambda *_: self._sync_arm_from_manager())
            # LAS-26: NOT-AUS von einer VC-Taste -> Anzeige sofort mitziehen.
            sync.subscribe_widget(SyncEvent.LASER_ESTOP, self,
                                  lambda *_: self._update_dmx_estop_label())
            # LAS-34: Die Bausteine zeigen einen ZUSTAND (Laser AN/AUS,
            # gewähltes Muster, Lage). Ändert ihn jemand anderes (Clear,
            # Palette, VC, Befehlszeile), ziehen sie nach — gebündelt, damit
            # ein Zug im Feld (zwei Werte) nur einmal nachlädt.
            # Der Zustand „Laser AN/AUS“ folgt auch der laufenden Ausgabe
            # (Szene, Blackout) — nur solange der Reiter zu sehen ist.
            self._zustand_takt = QTimer(self)
            self._zustand_takt.setInterval(500)
            self._zustand_takt.timeout.connect(self._update_dmx_estop_label)
            self._werte_takt = QTimer(self)
            self._werte_takt.setSingleShot(True)
            self._werte_takt.setInterval(30)
            self._werte_takt.timeout.connect(self._werte_nachziehen)
            sync.subscribe_widget(SyncEvent.PROGRAMMER_CHANGED, self,
                                  lambda *_: self._werte_takt.start())
        except Exception as e:
            print(f"[laser_view] sync subscribe error: {e}")

    def _werte_nachziehen(self):
        try:
            if not self.isVisible():
                return
            # Wer gerade eine Zahl eintippt, wird nicht überschrieben.
            from PySide6.QtWidgets import QApplication
            fokus = QApplication.focusWidget()
            if (fokus is not None and self.isAncestorOf(fokus)
                    and fokus.inherits("QLineEdit")):
                self._bausteine_laden()
            else:
                self._load_values()
        except RuntimeError:
            pass

    def _on_show_loaded(self):
        # Safety: eine neu geladene Show startet UNSCHARF und ohne aktive
        # Figuren — Scharfschalten ist immer eine bewusste Nutzeraktion.
        lo = self._laser_output()
        if lo is not None:
            lo.set_armed(False)
            lo.clear_figures()
        try:
            self._btn_arm.setChecked(False)
            self._rebuild_figure_combo()     # neue Show → neue Figuren-Bibliothek
            self._combo_figure.setCurrentIndex(0)
            self._update_arm_button()
        except RuntimeError:
            pass
        self.refresh_from_selection()

    # ---------------------------------------------------------- Selection --
    def _on_selection_changed(self):
        # Unsichtbar: nicht bei jedem fremden Tab-Klick Widgets neu bauen —
        # showEvent holt den Sync nach (Muster aus efx_view/rgb_matrix_view).
        try:
            if not self.isVisible():
                self._stale = True
                return
        except RuntimeError:
            return
        self.refresh_from_selection()

    def showEvent(self, event):  # noqa: N802 (Qt-API)
        super().showEvent(event)
        if getattr(self, "_stale", True):
            self.refresh_from_selection()
        takt = getattr(self, "_zustand_takt", None)
        if takt is not None:
            takt.start()

    def hideEvent(self, event):  # noqa: N802 (Qt-API)
        super().hideEvent(event)
        takt = getattr(self, "_zustand_takt", None)
        if takt is not None:
            takt.stop()

    def refresh_from_selection(self):
        """Auswahl einlesen, Template bilden, Regler/Kacheln (neu) aufbauen."""
        self._stale = False
        state = get_state()
        try:
            selected = set(state.get_selected_fids())
        except Exception:
            selected = set()
        self._fixtures = [
            f for f in state.get_patched_fixtures()
            if getattr(f, "fid", None) in selected
            and fixture_has_laser_capability(f)
        ]

        if not self._fixtures:
            self._info.setText(
                "Kein Laser in der Auswahl — links ein Laser-Gerät wählen.")
            self._head_box.setVisible(False)
            self._mode_box.setVisible(False)
        else:
            names = ", ".join(
                str(getattr(f, "name", None) or getattr(f, "fixture_name", "")
                    or f"fid {getattr(f, 'fid', '?')}")
                for f in self._fixtures[:4])
            more = len(self._fixtures) - 4
            self._info.setText(
                f"{len(self._fixtures)} Laser: {names}"
                + (f" … (+{more})" if more > 0 else ""))
            self._head_box.setVisible(self._max_head_count() > 1)

        # Safety-Box nur für Netzwerk-Streaming-Laser (Klasse B) in der Auswahl
        # — über den Fähigkeits-Klassifikator (LAS-12), eine Wahrheitsquelle.
        self._network_fids = [
            int(getattr(f, "fid")) for f in self._fixtures
            if (_cap := laser_capability(f)) is not None
            and _cap.laser_class == LaserClass.NET_STREAM]
        self._safety_box.setVisible(bool(self._network_fids))
        # LAS-26: DMX-Laser in der Auswahl -> eigener NOT-AUS + Zustand
        # (LAS-34: als Sicherheitsleiste; sie trägt dann auch Modell/Anzahl).
        hat_dmx = len(self._fixtures) > len(self._network_fids)
        self._dmx_safety_box.setVisible(hat_dmx)
        # Aufgeklappte Sperrzonen-Meldung folgt der Leiste (ohne DMX-Laser zu).
        self._sperrzonen_details_zeigen(
            self._btn_sperrzonen_details.isChecked())
        self._info.setVisible(not hat_dmx)
        self._sync_arm_from_manager()   # VC-/MIDI-Änderungen widerspiegeln
        self._apply_figure_to_selection()

        template = self._template_channels()
        self._kanal_je_attr = {getattr(ch, "attribute", ""): ch
                               for ch in template}
        plan = self._plan_bilden(template)
        sig = (tuple((ch.attribute, int(getattr(ch, "channel_number", 0) or 0))
                     for ch in template), plan.kennung())
        if sig != self._template_sig:
            self._template_sig = sig
            self._plan = plan
            self._rebuild_rows(template)
            self._bausteine_aufbauen(template)
            self._rebuild_mode_tiles(template)
        self._sperrzonen_aktualisieren()
        self._update_dmx_estop_label()
        self._load_values()
        self._rebuild_palettes()
        self._rebuild_patterns(template)

    # ── Safety / Framequelle (LAS-07) ─────────────────────────────────────
    def _laser_output(self):
        try:
            return get_state().ensure_laser_output()
        except Exception as e:
            print(f"[laser_view] laser output unavailable: {e}")
            return None

    def _update_dmx_estop_label(self):
        """Zustand in der Sicherheitsleiste: NOT-AUS aktiv (LAS-26) bzw.
        Laser AN/AUS laut Betriebsart, dazu Modell und Anzahl (LAS-34)."""
        try:
            aktiv = bool(getattr(get_state(), "laser_estop_active", False))
        except Exception:
            aktiv = False
        try:
            n = len(self._fixtures)
            zahl = f"{n} Laser"
            if aktiv:
                text, farbe, punkt = "NOT-AUS aktiv", "#ff7b72", "#ff4040"
                neben = ("· alle DMX-Laser sind dunkel · wieder an: "
                         "Betriebsart oder Muster neu wählen")
            else:
                an = [self._laser_an(f) for f in self._fixtures]
                n_an = sum(1 for a in an if a)
                if not an or any(a is None for a in an):
                    text, farbe, punkt = "Laser", "#ffffff", "#555555"
                elif n_an == 0:
                    text, farbe, punkt = "Laser AUS", "#c8c8c8", "#555555"
                elif n_an == n:
                    text, farbe, punkt = "Laser AN", "#ffffff", "#30ff50"
                else:
                    text, farbe, punkt = (f"Laser AN ({n_an} von {n})",
                                          "#ffffff", "#30ff50")
                neben = "· " + " · ".join(
                    t for t in (self._modell_text(), zahl) if t)
            self._lbl_dmx_estop.setText(text)
            self._lbl_dmx_estop.setStyleSheet(
                f"color:{farbe};font-weight:bold;background:transparent;")
            self._lbl_dmx_estop.setToolTip(
                "Laut Betriebsart — im Programmer oder in der laufenden "
                "Ausgabe. Blackout, Grand Master 0 und NOT-AUS schalten den "
                "Laser über den Aus-Wert der Betriebsart dunkel.")
            self._zustand_punkt.setStyleSheet(
                f"background:{punkt};border-radius:5px;")
            self._lbl_modell.setText(neben)
        except RuntimeError:
            pass

    def _modell_text(self) -> str:
        """Modellname(n) der gewählten Laser für die Sicherheitsleiste."""
        namen: list[str] = []
        for f in self._fixtures:
            name = _modell_name(f)
            if name and name not in namen:
                namen.append(name)
        if len(namen) > 2:
            return "verschiedene Modelle"
        return ", ".join(namen)

    def _sperrzonen_aktualisieren(self):
        """Abzeichen der Sicherheitsleiste — nur, wo es die Sperrzonen-
        Anzeige gibt und sie zu den gewählten Lasern etwas sagt."""
        try:
            hinweis = sperrzonen_hinweis(
                get_state(), [getattr(f, "fid", -1) for f in self._fixtures]
            ) if self._fixtures else None
        except Exception:
            hinweis = None
        try:
            if hinweis is None:
                self._sperrzonen_abzeichen.setVisible(False)
                return
            kurz, lang = hinweis
            self._sperrzonen_abzeichen.setText(
                f"<b>{html.escape(str(kurz))}</b> &nbsp;"
                "<span style='color:#d8b84a'>"
                f"{NUR_ANZEIGE}</span>")
            self._sperrzonen_abzeichen.setToolTip(
                f"{lang}\n\n{NUR_ANZEIGE}. Kein Laserschutz.")
            self._sperrzonen_abzeichen.setVisible(True)
        except RuntimeError:
            pass

    def _sperrzonen_details_zeigen(self, an: bool):
        """Meldung je Laser unter der Sicherheitsleiste auf-/zuklappen."""
        try:
            self._btn_sperrzonen_details.setText(
                "Meldung ▴" if an else "Meldung ▾")
            zeigen = bool(an) and self._sperrzonen_hinweis is not None \
                and self._dmx_safety_box.isVisibleTo(self)
            self._sperrzonen_details.setVisible(zeigen)
            if zeigen:
                self._sperrzonen_hinweis.aktualisieren()
        except RuntimeError:
            pass

    def _sperrzonen_planer_oeffnen(self):
        """Knopf „Sperrzonen planen…“: oeffnet den Planer (LAS-35). Der Knopf
        ist nur sichtbar, wenn es den Planer auf diesem Stand gibt."""
        modul = _modul_oder_none(SPERRZONEN_PLANER_MODUL)
        if modul is None:
            return None
        try:
            return modul.planer_oeffnen(get_state(), self.window())
        except Exception as e:                           # noqa: BLE001
            print(f"[laser_view] Sperrzonen-Planer: {e}")
            return None

    def _update_arm_button(self):
        armed = self._btn_arm.isChecked()
        if armed:
            self._btn_arm.setText("🔓 SCHARF — Laser gibt Licht aus")
            self._btn_arm.setStyleSheet(
                "QPushButton{background:#8a6d00;color:#fff;font-weight:bold;"
                "border:1px solid #d4a200;border-radius:5px;padding:6px 14px;}")
        else:
            self._btn_arm.setText("🔒 UNSCHARF — Ausgabe geblockt")
            self._btn_arm.setStyleSheet(
                "QPushButton{background:#21262d;color:#8b949e;"
                "border:1px solid #30363d;border-radius:5px;padding:6px 14px;}")

    def _sync_arm_from_manager(self):
        """Arm-Button-Zustand vom Manager übernehmen — hält die Anzeige mit
        einer Scharf/Unscharf-Änderung von anderswo (VC-Button, MIDI) synchron.
        blockSignals verhindert, dass das Spiegeln ein set_armed rückauslöst."""
        lo = getattr(get_state(), "_laser_output", None)
        if lo is None:
            return
        try:
            self._btn_arm.blockSignals(True)
            self._btn_arm.setChecked(bool(lo.armed))
            self._btn_arm.blockSignals(False)
            self._update_arm_button()
        except RuntimeError:
            pass

    def _on_arm_toggled(self, checked: bool):
        lo = self._laser_output()
        if lo is not None:
            lo.set_armed(bool(checked))
        self._update_arm_button()

    def _on_estop(self):
        lo = self._laser_output()
        if lo is not None:
            # Reihenfolge ist sicherheitskritisch: (1) estop_all() setzt sofort
            # das Verriegelungs-Flag (Tick sendet nichts mehr), (2) EXPLIZIT
            # entwaffnen — NICHT nur implizit über setChecked→toggled, damit die
            # Sicherheit nicht an der Qt-Signal-Synchronität hängt, (3) erst
            # DANACH die Geräte-Verriegelung lösen. So bleibt der Laser dunkel
            # (unscharf), auch nachdem clear_estop_all die Session wieder öffnet.
            lo.estop_all()
            lo.set_armed(False)
        # Nach Not-Aus zurück auf unscharf — bewusstes Wieder-Scharfschalten nötig.
        self._btn_arm.setChecked(False)
        self._update_arm_button()
        if lo is not None:
            lo.clear_estop_all()
        self._update_dmx_estop_label()

    def _on_figure_changed(self):
        # BEWUSST ohne Index-Parameter: verbunden ueber weak_slot, das die
        # Signal-Argumente verwirft. Mit Parameter warf der Slot bei JEDEM
        # Umschalten TypeError (crash.log 2026-07-06) und die Figur wurde nie
        # gesetzt. Wer Signal-Argumente braucht, nimmt weak_slot_fwd.
        self._apply_figure_to_selection()

    def _apply_figure_to_selection(self, figure=...):
        """Setzt die Figur (Default: die in der Combo gewählte; ``None`` =
        Testmuster) als Framequelle für alle Netzwerk-Laser der Auswahl."""
        lo = self._laser_output()
        if lo is None:
            return
        if figure is ...:
            figure = self._combo_figure.currentData()
        for fid in getattr(self, "_network_fids", []):
            lo.set_figure(fid, figure)

    def _rebuild_figure_combo(self):
        """Combo neu füllen: Testmuster + eingebaute Figuren + gespeicherte
        Show-Figuren. Erhält die aktuelle Auswahl über den Namen, wenn möglich."""
        prev = self._combo_figure.currentData()
        prev_name = getattr(prev, "name", None)
        self._combo_figure.blockSignals(True)
        self._combo_figure.clear()
        self._combo_figure.addItem("Testmuster (Kreis)", None)
        try:
            from src.core.laser.figure import builtin_figures
            for fig in builtin_figures():
                self._combo_figure.addItem(f"Figur: {fig.name}", fig)
        except Exception as e:
            print(f"[laser_view] builtin figures error: {e}")
        try:
            saved = list(getattr(get_state(), "laser_figures", []) or [])
        except Exception:
            saved = []
        for fig in saved:
            self._combo_figure.addItem(f"★ {fig.name}", fig)
        # Auswahl nach Namen wiederherstellen.
        idx = 0
        if prev_name:
            for i in range(self._combo_figure.count()):
                d = self._combo_figure.itemData(i)
                if getattr(d, "name", None) == prev_name:
                    idx = i
                    break
        self._combo_figure.setCurrentIndex(idx)
        self._combo_figure.blockSignals(False)

    def _on_draw(self):
        """Zeichen-Dialog öffnen. Live-Vorschau streamt die Figur an die
        Netzwerk-Laser der Auswahl (sichtbar nur bei scharfem Laser). Beim
        Speichern landet sie in der Show-Figuren-Bibliothek + wird aktiv."""
        try:
            from src.ui.widgets.laser_draw_editor import LaserDrawDialog
        except Exception as e:
            print(f"[laser_view] draw editor unavailable: {e}")
            return
        base = self._combo_figure.currentData()   # ausgewählte Figur als Start
        # Fähigkeit → ehrliches Banner (LAS-12/13). Die Live-Vorschau streamt an
        # die NETZWERK-Laser der Auswahl → deren Fähigkeit (exakt) ist relevant,
        # nicht die eines evtl. mitgewählten DMX-Musterlasers.
        cap = None
        try:
            by_fid = {getattr(f, "fid", None): f for f in self._fixtures}
            for fid in getattr(self, "_network_fids", []):
                f = by_fid.get(fid)
                if f is not None:
                    cap = laser_capability(f)
                    break
            if cap is None and self._fixtures:
                cap = laser_capability(self._fixtures[0])
        except Exception:
            cap = None
        dlg = LaserDrawDialog(
            figure=base, parent=self, capability=cap,
            on_live_update=lambda fig: self._apply_figure_to_selection(fig))
        dlg.exec()
        # Nach dem Dialog: aktive Combo-Figur wieder streamen (Live-Preview end).
        self._apply_figure_to_selection()
        fig = getattr(dlg, "result_figure", None)
        dlg.deleteLater()      # Modal-Dialog nicht am Parent ansammeln lassen
        if fig is None or not fig.points:
            return
        # In der Show speichern (gleicher Name ersetzt) und aktiv setzen.
        try:
            state = get_state()
            figs = [f for f in getattr(state, "laser_figures", [])
                    if f.name != fig.name]
            figs.append(fig)
            state.laser_figures = figs
        except Exception as e:
            print(f"[laser_view] save figure error: {e}")
        self._rebuild_figure_combo()
        for i in range(self._combo_figure.count()):
            d = self._combo_figure.itemData(i)
            if getattr(d, "name", None) == fig.name:
                self._combo_figure.setCurrentIndex(i)
                break

    def _template_channels(self) -> list:
        """Vereinigung der Laser-Kanäle aller selektierten Laser (ein Kanal je
        Attribut; Kanäle MIT Ranges als Repräsentant bevorzugt — dasselbe
        Muster wie der Attribut-Editor des Programmers)."""
        union: dict[str, object] = {}
        order: dict[str, int] = {}
        for f in self._fixtures:
            try:
                channels = get_channels_for_patched(f)
            except Exception:
                continue
            for ch in channels:
                attr = getattr(ch, "attribute", "") or ""
                if not im_laser_reiter(attr):
                    continue
                prev = union.get(attr)
                if prev is None or (not getattr(prev, "ranges", None)
                                    and getattr(ch, "ranges", None)):
                    union[attr] = ch
                order.setdefault(
                    attr, int(getattr(ch, "channel_number", 0) or 0))
        return sorted(union.values(),
                      key=lambda c: order.get(c.attribute, 999))

    def _max_head_count(self) -> int:
        """Höchste Vorkommens-Zahl eines Laser-Attributs über die Auswahl —
        >1 bedeutet: das Gerät hat eine zweite Mustergruppe (Kopf 1)."""
        best = 1
        for f in self._fixtures:
            try:
                channels = get_channels_for_patched(f)
            except Exception:
                continue
            counts: dict[str, int] = {}
            for ch in channels:
                attr = getattr(ch, "attribute", "") or ""
                if im_laser_reiter(attr):
                    counts[attr] = counts.get(attr, 0) + 1
            if counts:
                best = max(best, max(counts.values()))
        return best

    # ── LAS-34: Bausteine ─────────────────────────────────────────────────
    def _plan_bilden(self, template: list) -> _Plan:
        """Welche Bausteine die Auswahl bekommt. Ein Baustein entsteht nur,
        wenn ALLE gewählten Laser dieselbe Angabe dazu machen — sonst bleibt
        dieser Teil bei der bisherigen Bedienung."""
        plan = _Plan()
        if not self._fixtures:
            return plan
        by_attr = {getattr(ch, "attribute", ""): ch for ch in template}
        je = []
        for f in self._fixtures:
            try:
                je.append(laser_profilangaben(
                    list(get_channels_for_patched(f) or ())))
            except Exception as e:
                print(f"[laser_view] Profilangaben nicht lesbar: {e}")
                je.append(None)
        if not any(a is not None for a in je):
            return plan

        def gemeinsam(holen):
            """``(einig, wert)`` über alle gewählten Laser."""
            werte = []
            for a in je:
                try:
                    werte.append(holen(a) if a is not None else None)
                except Exception:
                    werte.append(None)
            return all(w == werte[0] for w in werte[1:]), werte[0]

        def kanal(name: str, feld: str):
            einig, teil = gemeinsam(
                lambda a: (lambda k: None if k is None
                           else (k.attribut, getattr(k, feld)))(getattr(a, name)))
            if not einig or teil is None or teil[0] not in by_attr:
                return None
            return getattr(je[0], name)

        ba = kanal("betriebsart_kanal", "betriebsart")
        if ba is not None:
            # Jeder Wertebereich des Kanals muss ein Segment haben — sonst
            # wäre eine Betriebsart des Geräts nicht mehr wählbar.
            bereiche = _sorted_ranges(by_attr[ba.attribut])
            if all(ba.betriebsart_fuer(_range_value(r)) is not None
                   for r in bereiche):
                plan.betriebsart = ba
        plan.muster = kanal("muster_kanal", "muster")
        plan.farben = kanal("farb_kanal", "farben")
        if "laser_x" in by_attr and "laser_y" in by_attr:
            ex, rx = gemeinsam(lambda a: a.richtung("laser_x"))
            ey, ry = gemeinsam(lambda a: a.richtung("laser_y"))
            if ex and ey and rx is not None and ry is not None:
                plan.lage = (rx, ry)
        belegt = plan.abgedeckt()
        regler = []
        for attr, *_ in SPRECH_REGLER:
            if attr not in by_attr or attr in belegt:
                continue
            einig, richtung = gemeinsam(lambda a, attr=attr: a.richtung(attr))
            # Ohne Richtung nur, wenn die Zeile nichts verlöre: ein Kanal mit
            # benannten Wertebereichen behält seine Zeile samt Auswahlliste.
            if einig and (richtung is not None
                          or not _sorted_ranges(by_attr[attr])):
                regler.append((attr, richtung))
        if plan.neu or any(r is not None for _a, r in regler):
            plan.regler = tuple(regler)
        return plan

    def _bausteine_aufbauen(self, template: list):
        """Die Bausteine zum aktuellen Plan füllen bzw. ausblenden."""
        plan = self._plan
        by_attr = self._kanal_je_attr

        self._seg_box.setVisible(plan.betriebsart is not None)
        self._umschalter.set_eintraege(
            plan.betriebsart.betriebsart if plan.betriebsart else ())

        self._lage_box.setVisible(plan.lage is not None)

        self._muster_box.setVisible(plan.muster is not None)
        self._galerie.set_muster(plan.muster.muster if plan.muster else ())
        self._lbl_schema.setVisible(plan.muster is not None)
        if plan.muster is not None:
            self._lbl_muster_zahl.setText(
                f"{len(plan.muster.muster)} aus Profil ·")
        self._alle_zeile(self._muster_alle_host, self._btn_muster_alle,
                         by_attr.get(plan.muster.attribut)
                         if plan.muster else None)

        self._farbe_box.setVisible(plan.farben is not None)
        self._farbfelder.set_farben(plan.farben.farben if plan.farben else ())
        self._alle_zeile(self._farbe_alle_host, self._btn_farbe_alle,
                         by_attr.get(plan.farben.attribut)
                         if plan.farben else None)

        while self._regler_lay.count():
            w = self._regler_lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._sprech = {}
        texte = {a: (t, z, o, w) for a, t, z, o, w in SPRECH_REGLER}
        for attr, richtung in plan.regler:
            titel, zusatz, ohne, worte = texte[attr]
            if richtung is None:
                zusatz = ohne
            regler = SprechRegler(attr, titel, richtung, self._regler_bewegt,
                                  zusatz=f"· {zusatz}" if zusatz else "",
                                  worte=worte)
            ch = by_attr.get(attr)
            regler.setToolTip(
                f"{row_label(ch) if ch is not None else titel} ({attr})"
                + ("" if richtung is not None else
                   "\nDas Profil nennt keine Richtung: der Regler läuft wie "
                   "der DMX-Wert, 0 bis 255."))
            self._sprech[attr] = regler
            self._regler_lay.addWidget(regler)
        self._regler_box.setVisible(bool(self._sprech))

        self._gemerkt_box.setVisible(plan.neu)
        self._spalte_muster.setVisible(plan.muster is not None or plan.neu)
        self._spalte_farbe.setVisible(plan.farben is not None
                                      or bool(self._sprech))
        self._bausteine.setVisible(plan.neu)

    def _alle_zeile(self, host: QWidget, knopf: QToolButton, channel):
        """Die Zeile hinter „alle 0–255“ (neu) aufbauen: der bisherige Regler
        des Kanals, zugeklappt."""
        lay = host.layout()
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        knopf.blockSignals(True)
        knopf.setChecked(False)
        knopf.setText("alle 0–255 ▸")
        knopf.blockSignals(False)
        host.setVisible(False)
        if channel is None:
            return
        row = _ChannelRow(channel, self._write_value, kompakt=True)
        self._rows[channel.attribute] = row
        lay.addWidget(row)

    def _muster_alle_umschalten(self, an: bool):
        self._btn_muster_alle.setText("alle 0–255 ▾" if an else "alle 0–255 ▸")
        self._muster_alle_host.setVisible(bool(an))
        # Die Werksmuster (eigene Slots mit Foto) gehören zum Regler.
        self._rebuild_patterns()

    def _farbe_alle_umschalten(self, an: bool):
        self._btn_farbe_alle.setText("alle 0–255 ▾" if an else "alle 0–255 ▸")
        self._farbe_alle_host.setVisible(bool(an))

    def _wert(self, attr: str, fixture=None) -> int:
        """Aktueller Wert eines Attributs: Programmer des ersten (bzw. des
        genannten) Lasers, kopfgerecht; ohne Programmer-Wert der Grundwert des
        Kanals — das, was das Gerät dann bekommt."""
        fx = fixture if fixture is not None else (
            self._fixtures[0] if self._fixtures else None)
        val = None
        if fx is not None:
            state = get_state()
            fid = getattr(fx, "fid", None)
            read_head = 1 if self._head_mode == "B" else 0
            try:
                val = state.get_programmer_value(fid, attr, head=read_head)
            except TypeError:
                val = state.get_programmer_value(fid, attr)
            except Exception:
                val = None
        if val is None:
            ch = self._kanal_je_attr.get(attr)
            val = getattr(ch, "default_value", 0) if ch is not None else 0
        try:
            return max(0, min(255, int(val or 0)))
        except (TypeError, ValueError):
            return 0

    def _an_bei(self, wert: int) -> bool | None:
        """Ist der Laser bei diesem Betriebsart-Wert an? ``None`` = das Profil
        sagt es nicht (kein Betriebsart-Kanal mit Bereichen)."""
        ba = self._plan.betriebsart
        if ba is not None:
            b = ba.betriebsart_fuer(wert)
            return None if b is None else b.art != "aus"
        ch = self._kanal_je_attr.get("shutter")
        for r in (_sorted_ranges(ch) if ch is not None else ()):
            lo = int(getattr(r, "range_from", 0) or 0)
            hi = int(getattr(r, "range_to", lo) or lo)
            if lo <= wert <= hi:
                return (getattr(r, "kind", "") or "") != "closed"
        return None

    def _ausgabe_wert(self, fixture, attr: str) -> int | None:
        """Was die Ausgabe für diesen Kanal zuletzt gerechnet hat (nach
        Blackout, Grand Master, laufenden Szenen) — ``None`` = unbekannt.
        Nur gelesen."""
        try:
            om = getattr(get_state(), "output_manager", None)
            if om is None:
                return None
            frame = om.get_display_frame(int(fixture.universe))
            if frame is None:
                return None
            for ch in get_channels_for_patched(fixture):
                if (getattr(ch, "attribute", "") or "") == attr:
                    return int(frame[int(fixture.address) - 1
                                     + int(ch.channel_number) - 1])
        except Exception:
            pass
        return None

    def _laser_an(self, fixture) -> bool | None:
        """Ist dieser Laser an? Massgeblich ist die Betriebsart — im
        Programmer ODER in der laufenden Ausgabe (eine Szene kann den Laser
        einschalten, ohne dass der Programmer davon weiss). Im Zweifel „an“:
        die Anzeige darf nie dunkel melden, was leuchtet."""
        ba = self._plan.betriebsart
        attr = ba.attribut if ba is not None else "shutter"
        an = self._an_bei(self._wert(attr, fixture))
        if an is None:
            return None
        ausgabe = self._ausgabe_wert(fixture, attr)
        return bool(an or (ausgabe is not None and self._an_bei(ausgabe)))

    def _bausteine_laden(self):
        """Die Bausteine auf die aktuellen Werte stellen (ohne zu schreiben)."""
        plan = self._plan
        try:
            self._update_dmx_estop_label()
            if not plan.neu or not self._fixtures:
                return
            aktiv = None
            if plan.betriebsart is not None:
                aktiv = plan.betriebsart.betriebsart_fuer(
                    self._wert(plan.betriebsart.attribut))
                self._umschalter.set_aktiv(aktiv)
            # Musik/Auto: das Gerät läuft selbst — Muster, Lage und Farbe
            # wirken nicht. („Aus“ sperrt nicht: dort stellt man vor.)
            gesperrt = (aktiv is not None and not aktiv.steuert
                        and aktiv.art != "aus")
            self._lbl_gesperrt.setVisible(gesperrt)

            farbe = None
            bild_farbe = None
            if plan.farben is not None:
                v = self._wert(plan.farben.attribut)
                farbe = plan.farben.farbe_fuer(v)
                self._farbfelder.set_gewaehlt(farbe)
                # Der Name kommt aus dem Geräteprofil (auch aus einer
                # geladenen Datei) und steht in einem Rich-Text-Feld.
                name = html.escape(farb_name(farbe)) if farbe is not None \
                    else "kein Eintrag"
                self._lbl_farbe.setText(
                    f'<span style="color:#fff">{name}</span> '
                    f'<span style="color:#8b949e">· DMX {v}</span>')
                # Ohne Eintrag ist die Farbe unbekannt: neutral zeichnen.
                bild_farbe = (farbe_als_qt(farbe) if farbe is not None
                              else QColor("#b8b8b8"))
                self._row_zeigen(plan.farben.attribut, v)
            muster = None
            if plan.muster is not None:
                v = self._wert(plan.muster.attribut)
                muster = plan.muster.muster_fuer(v)
                self._galerie.set_gewaehlt(muster)
                self._galerie.set_farbe(bild_farbe)
                self._row_zeigen(plan.muster.attribut, v)
            for attr, regler in self._sprech.items():
                regler.set_dmx(self._wert(attr))
            tempo = self._sprech.get("effect_speed")
            if tempo is not None:
                tempo.set_aktiv(aktiv is None or aktiv.art == "dynamisch")
            if plan.lage is not None:
                rx, ry = plan.lage
                ax = rx.dmx_zu_regler(self._wert("laser_x"))
                ay = ry.dmx_zu_regler(self._wert("laser_y"))
                self._lage_feld.set_bild(muster, bild_farbe, self._groesse())
                self._lage_feld.set_lage(ax, ay)
                self._lage_x.set_text(lage_text(ax, *self._enden(
                    rx, ("links", "rechts"))))
                self._lage_y.set_text(lage_text(ay, *self._enden(
                    ry, ("unten", "oben"))))
                n = len(self._fixtures)
                self._lbl_lage_hinweis.setText(
                    "ziehen zum Verschieben" if n == 1
                    else f"zeigt den ersten von {n} Lasern")
            for w in (self._lage_feld, self._btn_mitte, self._galerie,
                      self._muster_alle_host, self._farbfelder,
                      self._farbe_alle_host):
                w.setEnabled(not gesperrt)
        except RuntimeError:
            pass

    def _row_zeigen(self, attr: str, value: int):
        row = self._rows.get(attr)
        if row is not None:
            row.set_value(value)

    @staticmethod
    def _enden(richtung, ersatz: tuple[str, str]) -> tuple[str, str]:
        from src.core.laser.profilangaben import ENDEN
        a, b = richtung.enden
        if a and b:
            return ENDEN.get(a, a), ENDEN.get(b, b)
        return ersatz

    def _groesse(self) -> float | None:
        """Bildgröße 0.0 (klein) .. 1.0 (groß) für die Vorschau."""
        if "zoom" not in self._kanal_je_attr:
            return None
        v = self._wert("zoom")
        regler = self._sprech.get("zoom")
        if regler is not None and regler.richtung is not None:
            return regler.richtung.dmx_zu_regler(v)
        return v / 255.0

    def _betriebsart_gewaehlt(self, eintrag):
        """Segment gewählt: die Bereichsmitte schreiben — derselbe Wert wie
        die bisherige Kachel dieses Bereichs."""
        ba = self._plan.betriebsart
        if ba is not None:
            self._write_value(ba.attribut, int(eintrag.mitte))

    def _muster_gewaehlt(self, muster):
        if self._plan.muster is not None:
            self._write_value(self._plan.muster.attribut, int(muster.mitte))

    def _farbe_gewaehlt(self, farbe):
        if self._plan.farben is not None:
            self._write_value(self._plan.farben.attribut, int(farbe.mitte))

    def _regler_bewegt(self, attr: str, dmx: int):
        self._write_value(attr, int(dmx))

    def _lage_gezogen(self, ax: float, ay: float):
        """Ziehen im Feld: Reglerstellung je Achse (0 = links/unten, 1 =
        rechts/oben) über die ``Richtung`` des Profils in DMX — umgekehrte
        Kanäle und der Mittelbereich sind dort berücksichtigt. Geschrieben
        wird der MODELL-Wert; hängt der Laser kopfüber (LAS-30:
        ``invert_laser_x`` …), dreht die Ausgabestufe ihn wie bei jedem
        anderen Schreiber."""
        if self._plan.lage is None:
            return
        rx, ry = self._plan.lage
        self._write_value("laser_x", rx.regler_zu_dmx(ax))
        self._write_value("laser_y", ry.regler_zu_dmx(ay))

    def _lage_mitte(self):
        if self._plan.lage is None:
            return
        for attr, r in zip(("laser_x", "laser_y"), self._plan.lage):
            mitte = r.mitte_dmx
            self._write_value(
                attr, mitte if mitte is not None else r.regler_zu_dmx(0.5))

    def bedienbare_attribute(self) -> set[str]:
        """Alle Attribute, die dieser Reiter gerade bedient: Regler-Zeilen,
        Bausteine und die Betriebsart-Kacheln. Für die Zusage „kein Kanal
        geht verloren“ (UI-89, LAS-34)."""
        out = set(self._rows) | set(self._sprech)
        plan = self._plan
        if plan.betriebsart is not None and not self._seg_box.isHidden():
            out.add(plan.betriebsart.attribut)
        if plan.muster is not None and not self._muster_box.isHidden():
            out.add(plan.muster.attribut)
        if plan.farben is not None and not self._farbe_box.isHidden():
            out.add(plan.farben.attribut)
        if plan.lage is not None and not self._lage_box.isHidden():
            out |= {"laser_x", "laser_y"}
        if not self._mode_box.isHidden():
            out.add("shutter")
        return out

    # ------------------------------------------------------------- Aufbau --
    def _rebuild_rows(self, template: list):
        while self._rows_lay.count() > 1:
            item = self._rows_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows = {}
        self._collapsible_groups = {}
        # LAS-34: was ein Baustein bedient, bekommt hier keine Zeile.
        ohne = self._plan.abgedeckt()
        template = [ch for ch in template
                    if getattr(ch, "attribute", "") not in ohne]
        by_attr = {getattr(ch, "attribute", ""): ch for ch in template}

        # Kern-Achsen als benannte Gruppen (Muster / Farbe / Bewegung … /
        # Zeichnen) — in Reihenfolge, nur wenn das Gerät die Attribute hat.
        for title, attrs in _ROW_GROUPS:
            present = [by_attr[a] for a in attrs if a in by_attr]
            if present:
                box = self._make_row_group(title, present, collapsed=False)
                self._rows_lay.insertWidget(self._rows_lay.count() - 1, box)

        # Alles Übrige = technische Kanäle → eingeklappte „Weitere"-Gruppe.
        # `shutter` steckt in den Betriebsart-Kacheln — aber nur, wenn der
        # Kanal Wertebereiche hat. Ohne Bereiche gibt es keine Kacheln; dann
        # bekommt er hier seinen Regler (UI-89: der Programmer zeigt ihn fuer
        # einen Laser sonst nirgends mehr).
        rest = [ch for ch in template
                if getattr(ch, "attribute", "") not in _GROUPED_ATTRS
                and not (getattr(ch, "attribute", "") == "shutter"
                         and _sorted_ranges(ch))]
        if rest:
            box = self._make_row_group(_ADVANCED_GROUP, rest, collapsed=True)
            self._rows_lay.insertWidget(self._rows_lay.count() - 1, box)
        self._rows_host.setVisible(bool(self._rows))

    def _make_row_group(self, title: str, channels: list,
                        collapsed: bool) -> QGroupBox:
        """Eine benannte Regler-Gruppe. ``collapsed`` macht sie einklappbar
        (checkable QGroupBox; die Regler-Zeilen werden bei „zu" versteckt).

        WICHTIG (STAB-09): der Toggle-Slot darf die Regler-Zeilen NICHT in die
        Signal-Closure binden — jede Zeile hält ``self._write_value`` und damit
        die View; über die C++-``toggled``-Connection wäre das ein GC-blinder
        Selbst-Pin. Wir merken uns die Attribut-Namen PRO Gruppe (Titel als
        Schlüssel) und binden nur diesen String in die Closure; die Zeilen
        werden zur Laufzeit in ``self._rows`` nachgeschlagen."""
        # LAS-26: „&“ im Titel ist fuer Qt ein Tastenkuerzel — „Bewegung &
        # Geschwindigkeit“ stand als „Bewegung _Geschwindigkeit“ da.
        box = QGroupBox(title.replace("&", "&&"))
        lay = QVBoxLayout(box)
        lay.setSpacing(3)
        lay.setContentsMargins(8, 4, 8, 6)
        attrs: list[str] = []
        for ch in channels:
            row = _ChannelRow(ch, self._write_value)
            self._rows[ch.attribute] = row
            lay.addWidget(row)
            attrs.append(ch.attribute)
        if collapsed:
            box.setCheckable(True)
            box.setChecked(False)
            box.setToolTip("Technische Kanäle — zum Aufklappen anhaken.")
            for a in attrs:
                self._rows[a].setVisible(False)
            self._collapsible_groups[title] = list(attrs)
            box.toggled.connect(weak_slot_fwd(self._toggle_group_named, title))
        return box

    def _toggle_group_named(self, title: str, checked: bool):
        for a in getattr(self, "_collapsible_groups", {}).get(title, ()):
            row = self._rows.get(a)
            if row is None:
                continue
            try:
                row.setVisible(bool(checked))
            except RuntimeError:
                pass

    def _rebuild_mode_tiles(self, template: list):
        while self._mode_lay.count():
            item = self._mode_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        shutter = next((ch for ch in template if ch.attribute == "shutter"),
                       None)
        ranges = _sorted_ranges(shutter) if shutter is not None else []
        # LAS-34: bedient der Umschalter die Betriebsart, entfallen die Kacheln.
        ba = self._plan.betriebsart
        if ba is not None and ba.attribut == "shutter":
            ranges = []
        self._mode_box.setVisible(bool(ranges))
        if not ranges:
            return
        try:
            from src.ui.widgets.preset_tile import PresetTile
        except Exception as e:
            print(f"[laser_view] preset_tile import error: {e}")
            return
        kind_colors = {"closed": "#21262d", "open": "#1a4a2a",
                       "sound": "#1a3a5c"}
        for r in ranges:
            name = getattr(r, "name", "") or "?"
            tile = PresetTile(
                name, _range_value(r),
                color=kind_colors.get(getattr(r, "kind", "") or ""),
                tooltip=f"{getattr(shutter, 'name', '') or 'Betriebsart'}"
                        f" → {_range_value(r)}")
            tile.clicked.connect(weak_slot_fwd(self._on_mode_tile_clicked))
            self._mode_lay.addWidget(tile)
        self._mode_lay.addStretch(1)

    def _rebuild_palettes(self):
        while self._pal_grid.count():
            item = self._pal_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        try:
            from src.core.engine.palette import (PaletteType,
                                                 get_palette_manager)
            from src.ui.widgets.preset_tile import PresetTile
        except Exception as e:
            print(f"[laser_view] palette import error: {e}")
            return
        palettes = get_palette_manager().get_by_type(PaletteType.LASER)
        for i, p in enumerate(palettes):
            tile = PresetTile(p.name, p.name, color="#2a0a3a",
                              tooltip="Muster auf die ausgewählten Laser "
                                      "anwenden")
            tile.clicked.connect(weak_slot(self._apply_palette, p))
            self._pal_grid.addWidget(tile, i // 4, i % 4)
        # LAS-34: mit Bausteinen stehen dieselben Paletten als „Gemerkte
        # Muster“ in der mittleren Spalte — der Kasten ist der Rückfall.
        self._pal_box.setVisible(not self._plan.neu)
        self._gemerkte_aufbauen(palettes)

    #: So viele gemerkte Muster stehen als Knopf da; weitere im Menü „▾“.
    GEMERKT_SICHTBAR = 2

    def _gemerkte_aufbauen(self, palettes: list):
        """„Gemerkte Muster“: kleine Knöpfe für die Laser-Paletten der Show
        (``PaletteType.LASER`` — dieselbe Ablage wie der Paletten-Reiter,
        keine zweite) und „+ merken…“."""
        lay = self._gemerkt_lay
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._gemerkt_knoepfe = []
        for p in palettes[:self.GEMERKT_SICHTBAR]:
            btn = QPushButton(self._gemerkt_text(p, 11))
            btn.setFixedHeight(TOUCH)
            btn.setToolTip(f"„{p.name}“ auf die gewählten Laser anwenden "
                           "(umbenennen und löschen im Reiter Paletten).")
            btn.clicked.connect(weak_slot(self._apply_palette, p))
            self._gemerkt_knoepfe.append(btn)
            lay.addWidget(btn, stretch=1)
        rest = palettes[self.GEMERKT_SICHTBAR:]
        if rest:
            mehr = QToolButton()
            mehr.setText(f"+{len(rest)} ▾")
            mehr.setFixedHeight(TOUCH)
            mehr.setToolTip("Weitere gemerkte Muster")
            mehr.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(mehr)
            for p in rest:
                menu.addAction(p.name).triggered.connect(
                    weak_slot(self._apply_palette, p))
            mehr.setMenu(menu)
            lay.addWidget(mehr)
        merken = QPushButton("+ merken…")
        merken.setFixedHeight(TOUCH)
        merken.setToolTip(
            "Muster, Farbe, Größe und Lage der gewählten Laser unter einem "
            "Namen merken (als Laser-Palette der Show).")
        merken.clicked.connect(weak_slot(self._save_palette))
        self._btn_merken = merken
        lay.addWidget(merken)
        if not palettes:
            lay.addStretch(1)

    @staticmethod
    def _gemerkt_text(palette, laenge: int) -> str:
        name = str(getattr(palette, "name", "") or "")
        return name if len(name) <= laenge else name[:laenge - 1] + "…"

    # ── Werksmuster-Picker (LAS-18b) ──────────────────────────────────────
    def _pattern_picker_applicable(self, template=None) -> bool:
        """Picker nur für Klasse-A-Laser (BUILTIN_DMX) mit Musterauswahl-Kanal
        (``gobo_wheel``) in der Auswahl — Netz-Laser haben die Figuren."""
        if template is None:
            template = self._template_channels()
        has_pattern = any(getattr(ch, "attribute", "") == "gobo_wheel"
                          for ch in template)
        if not has_pattern:
            return False
        for f in self._fixtures:
            try:
                cap = laser_capability(f)
            except Exception:
                cap = None
            if cap is not None and cap.laser_class == LaserClass.BUILTIN_DMX:
                return True
        return False

    def _rebuild_patterns(self, template=None):
        while self._pattern_grid.count():
            item = self._pattern_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        applicable = self._pattern_picker_applicable(template)
        # LAS-34: steht die Muster-Galerie des Profils da, gehören die selbst
        # gemerkten Werksmuster zum Regler hinter „alle 0–255“.
        if (applicable and self._plan.muster is not None
                and not self._btn_muster_alle.isChecked()):
            applicable = False
        self._pattern_box.setVisible(applicable)
        if not applicable:
            return
        slots = list(getattr(get_state(), "laser_patterns", []) or [])
        for i, slot in enumerate(slots):
            tile = _PatternTile(slot, self._apply_pattern_slot,
                                self._delete_pattern_slot)
            self._pattern_grid.addWidget(tile, i // 6, i % 6)

    def _apply_pattern_slot(self, slot):
        """Werksmuster abrufen: Bank + Muster kopf-korrekt in den Programmer
        (über ``_write_value`` → ENG-03-Guard greift; Bank existiert am L2600
        nur in Gruppe A und wird dort geschrieben)."""
        template = self._template_channels()
        attrs = {getattr(ch, "attribute", "") for ch in template}
        if "laser_bank" in attrs:
            self._write_value("laser_bank", int(slot.bank))
        self._write_value("gobo_wheel", int(slot.pattern))
        self._load_values()

    def _add_pattern_slot(self):
        """Aktuelle Bank-/Muster-Werte als Slot merken (Name + optionales
        Foto). Liest die Werte des ERSTEN Lasers der Auswahl — kopfgerecht zum
        aktiven A/B-Modus (wie ``_load_values``)."""
        if not self._fixtures:
            return
        state = get_state()
        fid = getattr(self._fixtures[0], "fid", None)
        if fid is None:
            return
        read_head = 1 if self._head_mode == "B" else 0
        try:
            pattern = state.get_programmer_value(fid, "gobo_wheel",
                                                 head=read_head)
        except Exception:
            pattern = None
        try:
            bank = state.get_programmer_value(fid, "laser_bank")
        except Exception:
            bank = None
        from src.core.laser.pattern_slots import PatternSlot
        slots = list(getattr(state, "laser_patterns", []) or [])
        name, ok = QInputDialog.getText(
            self, "Werksmuster merken",
            "Name für dieses Werksmuster (z. B. Kreis groß):",
            text=f"Muster {len(slots) + 1}")
        if not ok:
            return
        image_path = ""
        try:
            from PySide6.QtWidgets import QFileDialog
            image_path, _ = QFileDialog.getOpenFileName(
                self, "Foto vom Laser-Output (optional — Abbrechen = ohne)",
                "", "Bilder (*.png *.jpg *.jpeg *.bmp *.webp)")
        except Exception:
            image_path = ""
        slot = PatternSlot(name=(name or "").strip(),
                           bank=int(bank or 0), pattern=int(pattern or 0),
                           image_path=image_path or "")
        slots.append(slot)
        state.laser_patterns = slots
        self._rebuild_patterns()

    def _delete_pattern_slot(self, slot):
        state = get_state()
        slots = [s for s in getattr(state, "laser_patterns", []) or []
                 if s is not slot]
        state.laser_patterns = slots
        self._rebuild_patterns()

    # ------------------------------------------------------------- Werte ---
    def _heads_for(self, fx, attr: str) -> list[int]:
        """Zu beschreibende Köpfe je Modus — Kopf 1 nur, wenn das Gerät ein
        2. Vorkommen des Attributs wirklich hat (ENG-03-Muster)."""
        try:
            count = sum(
                1 for ch in get_channels_for_patched(fx)
                if (getattr(ch, "attribute", "") or "") == attr)
        except Exception:
            count = 0
        if count <= 0:
            return []
        heads = {"A": [0], "B": [1], "AB": [0, 1]}[self._head_mode]
        return [h for h in heads if h == 0 or count > h]

    def _write_value(self, attr: str, value: int):
        state = get_state()
        for f in self._fixtures:
            fid = getattr(f, "fid", None)
            if fid is None:
                continue
            for head in self._heads_for(f, attr):
                state.set_programmer_value(fid, attr, int(value), head=head)
        # Betriebsart/Muster loesen den DMX-NOT-AUS (A3D-02) — Anzeige folgen
        # (LAS-34: samt Bausteinen: Zustand, Vorschau, Sperre in Musik/Auto).
        self._bausteine_laden()

    def _load_values(self):
        if not self._fixtures:
            return
        state = get_state()
        first = self._fixtures[0]
        fid = getattr(first, "fid", None)
        read_head = 1 if self._head_mode == "B" else 0
        for attr, row in self._rows.items():
            try:
                val = state.get_programmer_value(fid, attr, head=read_head)
            except TypeError:
                val = state.get_programmer_value(fid, attr)
            except Exception:
                val = None
            row.set_value(int(val) if val is not None else 0)
        self._bausteine_laden()

    def _on_head_mode_toggled(self, key: str, on: bool):
        """Bound-Slot statt Lambda (STAB-10): nur der AKTIV werdende
        Radio-Button schaltet die Mustergruppe."""
        if on:
            self._set_head_mode(key)

    def _on_mode_tile_clicked(self, value):
        """Bound-Slot statt Lambda (STAB-10): Shutter-Kachel schreibt den Wert."""
        self._write_value("shutter", int(value))

    def _set_head_mode(self, mode: str):
        self._head_mode = mode
        self._load_values()

    # ----------------------------------------------------------- Paletten --
    def _save_palette(self):
        if not self._fixtures:
            return
        name, ok = QInputDialog.getText(
            self, "Muster speichern",
            "Name für das Laser-Muster (aktuelle Werte der Auswahl):")
        name = (name or "").strip()
        if not ok or not name:
            return
        try:
            from src.core.engine.palette import (Palette, PaletteType,
                                                 get_palette_manager)
            manager = get_palette_manager()
            fids = [getattr(f, "fid") for f in self._fixtures]
            existing = manager.find(name)
            if existing is not None and existing.type == PaletteType.LASER:
                existing.record_from_programmer(fids)
                manager._notify_palettes_changed()
            else:
                p = Palette(name=name, type=PaletteType.LASER)
                p.record_from_programmer(fids)
                manager.add(p)
        except Exception as e:
            print(f"[laser_view] save palette error: {e}")
        self._rebuild_palettes()

    def _apply_palette(self, palette):
        fids = [getattr(f, "fid") for f in self._fixtures]
        if not fids:
            return
        try:
            palette.apply_to_programmer(fids)
        except Exception as e:
            print(f"[laser_view] apply palette error: {e}")
        self._load_values()
