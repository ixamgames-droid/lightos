"""Effekt-Assistent — Schritt-fuer-Schritt Effekte bauen (QLC+ v5 inspiriert).

Ablauf:
  1. Effekt-Typ waehlen (Farb-Chase, Lauflicht, Police, Rainbow, Fire, ...)
  2. Lampen auswaehlen
  3. Farben auswaehlen (bei farbbasierten Effekten)
  4. Tempo / Beat / Name
  -> erzeugt automatisch die noetigen Szenen + einen Chaser im Function-Manager.

Aufruf:  EffectWizard(parent).exec()  -> self.created_function (Chaser | None)
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QCheckBox, QGridLayout, QPushButton, QLineEdit,
    QDoubleSpinBox, QSpinBox, QWidget, QScrollArea, QFrame,
)

# (key, Label, Beschreibung, braucht_farben, default_farben, default_beat)
PRESETS = [
    ("color_chase", "Farb-Chase", "Farben nacheinander auf allen Lampen", True,
     ["red", "green", "blue"], True),
    ("color_run", "Farb-Lauflicht", "Farben wandern über die Lampen", True,
     ["red", "green", "blue"], True),
    ("run", "Lauflicht", "Ein Licht wandert über die Lampen", False, ["white"], True),
    ("rainbow", "Rainbow", "Sanfter Regenbogen-Verlauf", True,
     ["red", "amber", "green", "cyan", "blue", "magenta"], False),
    ("police", "Police", "Blaulicht: zwei Farben im Wechsel + Aus", True,
     ["red", "blue"], True),
    ("strobe", "Strobe", "Schnelles weisses Blitzen", False, ["white"], False),
    ("pulse", "Pulse", "Sanftes Auf- und Abblenden", True, ["white"], False),
    ("twinkle", "Twinkle", "Zufälliges Funkeln einzelner Lampen", True, ["white"], False),
    ("fire", "Fire", "Warmes Feuer-Flackern", False, [], False),
    ("theater", "Theater", "Abwechselnd Gruppen (aussen/mitte)", True, ["white"], True),
    ("wipe", "Wipe", "Farbe wischt über die Lampen (füllt auf)", True, ["blue"], True),
    ("comet", "Komet", "Heller Kopf mit nachziehendem Schweif", True, ["white"], True),
    ("random_strobe", "Random-Strobe", "Zufällige Lampen blitzen weiß", False, ["white"], False),
    ("vu", "VU-Meter", "Pegel-Balken grün→rot, auf und ab", False, [], True),
]

SWATCHES = [
    ("Rot", (255, 0, 0)), ("Amber", (255, 140, 0)), ("Gelb", (255, 255, 0)),
    ("Grün", (0, 255, 0)), ("Cyan", (0, 255, 255)), ("Blau", (0, 0, 255)),
    ("Magenta", (255, 0, 255)), ("Pink", (255, 60, 120)), ("Weiß", (255, 255, 255)),
    ("Warm", (255, 140, 40)),
]
_NAMED = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
          "white": (255, 255, 255), "amber": (255, 140, 0), "cyan": (0, 255, 255),
          "magenta": (255, 0, 255)}


class _TypePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("1. Effekt-Typ wählen")
        self.setSubTitle("Welche Art von Effekt möchtest du erstellen?")
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setSpacing(2)
        for key, label, desc, *_ in PRESETS:
            it = QListWidgetItem(f"{label}   —   {desc}")
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda *_: self.wizard().next())
        lay.addWidget(self.list)

    def selected_key(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else "color_chase"


class _FixturePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("2. Lampen wählen")
        self.setSubTitle("Welche Lampen soll der Effekt nutzen?")
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        b_all = QPushButton("Alle"); b_none = QPushButton("Keine")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none.clicked.connect(lambda: self._set_all(False))
        row.addWidget(b_all); row.addWidget(b_none); row.addStretch(1)
        lay.addLayout(row)
        self.checks = []
        try:
            from src.core.app_state import get_state
            state = get_state()
            # Vorauswahl aus dem Programmer (R2): liegen gewählte Geräte vor, nur
            # diese vorab ankreuzen; sonst (leer) wie bisher alle.
            sel = set(state.get_selected_fids())
            # EA-01: Gruppen-Schnellauswahl — ein Klick kreuzt die Mitglieder der
            # Gruppe zusaetzlich an (Union; hebt andere Haken nicht auf).
            try:
                from sqlalchemy import select
                from src.core.database.models import FixtureGroup
                with state._session() as s:
                    group_names = [g.name for g in s.execute(
                        select(FixtureGroup).order_by(
                            FixtureGroup.folder, FixtureGroup.name)).scalars()]
                # Doppelte Namen entfernen (group_fids_by_name matcht per Name; bei
                # Duplikaten liefert es [] -> die Gruppe verschwaende sonst ganz).
                group_names = list(dict.fromkeys(group_names))
                # Hinweis: selected_fids() folgt der Checkbox-/Patch-Reihenfolge, nicht
                # der Gruppen-Raster-Reihenfolge — richtungsabhaengige Sweeps nutzen
                # also Patch-Order. Fuer den Grundfall (Gruppe waehlen) unkritisch.
                grp = [(n, state.group_fids_by_name(n)) for n in group_names]
                grp = [(n, f) for (n, f) in grp if f]
            except Exception:
                grp = []
            if grp:
                grow = QHBoxLayout()
                grow.addWidget(QLabel("Gruppen:"))
                for gname, gfids in grp:
                    gb = QPushButton(f"{gname} ({len(gfids)})")
                    gb.setToolTip("Mitglieder dieser Gruppe zusätzlich auswählen")
                    gb.clicked.connect(
                        lambda _=False, fl=list(gfids): self._select_group(fl))
                    grow.addWidget(gb)
                grow.addStretch(1)
                lay.addLayout(grow)
            for f in state.get_patched_fixtures():
                cb = QCheckBox(f"{getattr(f,'label','Fixture')}  (ID {f.fid}, U{f.universe} @{f.address})")
                cb.setChecked(f.fid in sel if sel else True)
                cb.fid = f.fid
                self.checks.append(cb)
                lay.addWidget(cb)
        except Exception as e:
            lay.addWidget(QLabel(f"Fehler beim Laden der Lampen: {e}"))
        lay.addStretch(1)

    def _set_all(self, on):
        for cb in self.checks:
            cb.setChecked(on)

    def _select_group(self, fids):
        """EA-01: Mitglieder einer Gruppe zusätzlich ankreuzen (Union — bestehende
        Haken bleiben). Nicht gepatchte fids haben keine Checkbox und entfallen."""
        want = set(fids)
        for cb in self.checks:
            if cb.fid in want:
                cb.setChecked(True)

    def selected_fids(self):
        return [cb.fid for cb in self.checks if cb.isChecked()]


class _ColorPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("3. Farben wählen")
        self.setSubTitle("Klick die Farben an, die der Effekt verwenden soll.")
        lay = QVBoxLayout(self)
        self._info = QLabel("")
        self._info.setStyleSheet("color:#888;")
        lay.addWidget(self._info)
        grid = QGridLayout()
        self.swatch_btns = []
        for i, (name, rgb) in enumerate(SWATCHES):
            b = QPushButton(name)
            b.setCheckable(True)
            b.rgb = rgb
            b.setFixedHeight(40)
            tc = "#000" if sum(rgb) > 380 else "#fff"
            b.setStyleSheet(
                f"QPushButton {{ background: rgb{rgb}; color:{tc}; border:2px solid #333; border-radius:4px; }}"
                f"QPushButton:checked {{ border:3px solid #fff; }}")
            self.swatch_btns.append(b)
            grid.addWidget(b, i // 5, i % 5)
        lay.addLayout(grid)
        # EA-02: optionale Farb-Zwischenstufen (sanfte Verläufe).
        ir = QHBoxLayout()
        self._interp_chk = QCheckBox("Zwischenstufen einfügen")
        self._interp_chk.setToolTip(
            "Interpoliert zwischen den gewählten Farben N Zwischenfarben — sanfter "
            "Verlauf für Farb-Chase / Rainbow / Farb-Lauflicht.")
        self._interp_spin = QSpinBox()
        self._interp_spin.setRange(1, 16)
        self._interp_spin.setValue(4)
        self._interp_spin.setPrefix("× ")
        self._interp_spin.setEnabled(False)
        self._interp_chk.toggled.connect(self._interp_spin.setEnabled)
        ir.addWidget(self._interp_chk)
        ir.addWidget(self._interp_spin)
        ir.addStretch(1)
        lay.addLayout(ir)
        lay.addStretch(1)

    def initializePage(self):
        # Defaults aus dem gewaehlten Preset setzen
        wiz = self.wizard()
        key = wiz.page(0).selected_key()
        preset = next((p for p in PRESETS if p[0] == key), None)
        needs = preset[3] if preset else True
        defaults = preset[4] if preset else []
        self.setEnabled(needs)
        self._info.setText("" if needs else
                           "Dieser Effekt braucht keine Farbauswahl (überspringen mit Weiter).")
        default_rgbs = [_NAMED.get(c) for c in defaults if _NAMED.get(c)]
        for b in self.swatch_btns:
            b.setChecked(b.rgb in default_rgbs)

    def selected_colors(self):
        cols = [b.rgb for b in self.swatch_btns if b.isChecked()]
        return cols or [(255, 255, 255)]

    def expanded_colors(self):
        """EA-02: optional N Zwischenfarben zwischen aufeinanderfolgenden Farben
        (mit Wrap last→first für nahtlose Loops). Ohne Aktivierung = selected_colors."""
        cols = self.selected_colors()
        if not (self._interp_chk.isChecked() and len(cols) >= 2):
            return cols
        n = int(self._interp_spin.value())
        if n <= 0:
            return cols
        from src.core.engine.rgb_matrix import lerp_color
        out = []
        for i in range(len(cols)):
            a = cols[i]
            b = cols[(i + 1) % len(cols)]
            out.append(a)
            for k in range(1, n + 1):
                out.append(lerp_color(a, b, k / (n + 1)))
        return out


class _OptionsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("4. Tempo & Name")
        self.setSubTitle("Geschwindigkeit, Beat-Sync und Name festlegen.")
        form = QVBoxLayout(self)
        self.name = QLineEdit("Mein Effekt")
        form.addWidget(QLabel("Name:")); form.addWidget(self.name)
        r1 = QHBoxLayout()
        self.hold = QDoubleSpinBox(); self.hold.setRange(0.02, 10.0); self.hold.setValue(0.5)
        self.hold.setSingleStep(0.05); self.hold.setSuffix(" s Halten")
        self.fade = QDoubleSpinBox(); self.fade.setRange(0.0, 10.0); self.fade.setValue(0.2)
        self.fade.setSingleStep(0.05); self.fade.setSuffix(" s Fade")
        r1.addWidget(self.hold); r1.addWidget(self.fade)
        form.addLayout(r1)
        self.beat = QCheckBox("Im Beat laufen (folgt dem globalen Tempo / TAP)")
        form.addWidget(self.beat)
        form.addStretch(1)
        self._hint = QLabel(""); self._hint.setStyleSheet("color:#888;")
        form.addWidget(self._hint)

    def initializePage(self):
        wiz = self.wizard()
        key = wiz.page(0).selected_key()
        preset = next((p for p in PRESETS if p[0] == key), None)
        if preset:
            label = preset[1]
            self.name.setText(label)
            self.beat.setChecked(bool(preset[5]))
            # sinnvolle Defaults pro Typ
            defaults = {"strobe": (0.05, 0.0), "police": (0.13, 0.0), "rainbow": (0.3, 0.7),
                        "pulse": (0.5, 0.6), "fire": (0.1, 0.06), "twinkle": (0.12, 0.04),
                        "wipe": (0.15, 0.1), "comet": (0.1, 0.05),
                        "random_strobe": (0.05, 0.0), "vu": (0.1, 0.05)}
            h, f = defaults.get(key, (0.4, 0.2))
            self.hold.setValue(h); self.fade.setValue(f)
            self._hint.setText("Tipp: Bei 'Im Beat' bestimmt das TAP-Tempo das Schalt-Tempo.")


class EffectWizard(QWizard):
    """Erzeugt einen fertigen Chaser (inkl. Hilfs-Szenen) im Function-Manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Effekt-Assistent")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(560, 460)
        self.created_function = None
        self.addPage(_TypePage())
        self.addPage(_FixturePage())
        self.addPage(_ColorPage())
        self.addPage(_OptionsPage())
        self.setButtonText(QWizard.WizardButton.FinishButton, "Effekt erstellen")

    def accept(self):
        try:
            self._generate()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Effekt-Assistent", f"Konnte Effekt nicht erstellen:\n{e}")
            return
        super().accept()

    # ── Effekt-Generierung ─────────────────────────────────────────────────────

    def _generate(self):
        from src.core.app_state import get_state, get_channels_for_patched
        from src.core.engine.function_manager import get_function_manager
        from src.core.engine.function import RunOrder
        from src.core.engine.chaser import ChaserStep

        key = self.page(0).selected_key()
        fids = self.page(1).selected_fids()
        colors = self.page(2).selected_colors()
        colors_seq = self.page(2).expanded_colors()   # EA-02: optional interpoliert
        name = self.page(3).name.text().strip() or "Effekt"
        hold = float(self.page(3).hold.value())
        fade = float(self.page(3).fade.value())
        beat = bool(self.page(3).beat.isChecked())

        st = get_state()
        fm = get_function_manager()
        if not fids:
            raise ValueError("Keine Lampe ausgewählt.")
        # Bugfix: Kanal-Zuordnung MUSS pro Fixture berechnet werden. Frueher kam
        # die Map aus dem ersten Geraet und galt fuer alle — bei gemischten Typen
        # (PAR + Moving Head) landete color_r=Ch1 dann auf dem Pan-Kanal des MH
        # (er bewegte sich statt die Farbe zu wechseln). Jetzt: pro fid die echte
        # {attr: channel_number}-Map des jeweiligen Geraets.
        fx_by_fid = {f.fid: f for f in st.get_patched_fixtures()}
        chan_cache: dict[int, dict[str, int]] = {}

        def _chan_for(fid):
            m = chan_cache.get(fid)
            if m is None:
                fx = fx_by_fid.get(fid)
                m = ({c.attribute: c.channel_number
                      for c in get_channels_for_patched(fx)} if fx is not None else {})
                chan_cache[fid] = m
            return m

        def scene(sname, rgb=(0, 0, 0), intensity=255, only=None, white=0):
            s = fm.new_scene(sname)
            r, g, b = rgb
            for fid in (only if only is not None else fids):
                chan = _chan_for(fid)
                if "intensity" in chan:
                    s.set_value(fid, chan["intensity"], intensity)
                for a, v in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", white)):
                    if a in chan:
                        s.set_value(fid, chan[a], v)
            return s

        off = scene(f"{name} · Aus", intensity=0)
        steps, order = [], RunOrder.Loop

        if key in ("color_chase", "rainbow"):
            steps = [scene(f"{name} · {i+1}", rgb=c).id for i, c in enumerate(colors_seq)]
        elif key == "color_run":
            steps = [scene(f"{name} · P{i+1}", rgb=colors_seq[i % len(colors_seq)], only=[fid]).id
                     for i, fid in enumerate(fids)]
        elif key == "run":
            steps = [scene(f"{name} · P{i+1}", rgb=(0, 0, 0), white=255, only=[fid]).id
                     for i, fid in enumerate(fids)]
        elif key == "twinkle":
            steps = [scene(f"{name} · P{i+1}", rgb=colors[0], only=[fid]).id
                     for i, fid in enumerate(fids)]
            order = RunOrder.Random
        elif key == "police":
            c1 = colors[0]
            c2 = colors[1] if len(colors) > 1 else (0, 0, 255)
            steps = [scene(f"{name} · A", rgb=c1).id, off.id,
                     scene(f"{name} · B", rgb=c2).id, off.id]
        elif key == "strobe":
            steps = [scene(f"{name} · On", rgb=(0, 0, 0), white=255).id, off.id]
        elif key == "pulse":
            steps = [scene(f"{name} · Hell", rgb=colors[0]).id, off.id]
        elif key == "fire":
            steps = [scene(f"{name} · F1", rgb=(255, 80, 0)).id,
                     scene(f"{name} · F2", rgb=(255, 140, 0), intensity=180).id,
                     scene(f"{name} · F3", rgb=(200, 40, 0), intensity=110).id]
            order = RunOrder.Random
        elif key == "theater":
            if len(fids) >= 2:
                half = len(fids) // 2 or 1
                a = scene(f"{name} · A", rgb=colors[0], only=fids[:half] + fids[half+1:] if len(fids) >= 3 else fids[:half])
                b = scene(f"{name} · B", rgb=colors[0], only=fids[half:half+1] if len(fids) >= 3 else fids[half:])
                steps = [a.id, b.id]
            else:
                steps = [scene(f"{name} · A", rgb=colors[0]).id, off.id]
        elif key == "wipe":
            col = colors[0]
            steps = [scene(f"{name} · W{i+1}", rgb=col, only=fids[:i+1]).id
                     for i in range(len(fids))]
        elif key == "comet":
            col = colors[0]
            tail = 3
            for i in range(len(fids)):
                s = fm.new_scene(f"{name} · K{i+1}")
                for t in range(tail + 1):
                    j = i - t
                    if not (0 <= j < len(fids)):
                        continue
                    frac = 1.0 - t / (tail + 1)
                    chan = _chan_for(fids[j])
                    r, g, b = (int(c * frac) for c in col)
                    if "intensity" in chan:
                        s.set_value(fids[j], chan["intensity"], int(255 * frac))
                    for a, v in (("color_r", r), ("color_g", g), ("color_b", b)):
                        if a in chan:
                            s.set_value(fids[j], chan[a], v)
                    if "color_w" in chan and col == (255, 255, 255):
                        s.set_value(fids[j], chan["color_w"], int(255 * frac))
                steps.append(s.id)
        elif key == "random_strobe":
            steps = [scene(f"{name} · R{i+1}", rgb=(0, 0, 0), white=255, only=[fid]).id
                     for i, fid in enumerate(fids)]
            order = RunOrder.Random
        elif key == "vu":
            from src.core.engine.rgb_matrix import lerp_color
            n = len(fids)

            def _vu_color(frac):
                if frac < 0.5:
                    return lerp_color((0, 255, 0), (255, 255, 0), frac * 2)
                return lerp_color((255, 255, 0), (255, 0, 0), (frac - 0.5) * 2)

            levels = list(range(1, n + 1)) + list(range(n - 1, 0, -1))
            for k in levels:
                s = fm.new_scene(f"{name} · VU{k}")
                for idx in range(k):
                    fid = fids[idx]
                    chan = _chan_for(fid)
                    frac = idx / (n - 1) if n > 1 else 0.0
                    r, g, b = _vu_color(frac)
                    if "intensity" in chan:
                        s.set_value(fid, chan["intensity"], 255)
                    for a, v in (("color_r", r), ("color_g", g), ("color_b", b)):
                        if a in chan:
                            s.set_value(fid, chan[a], v)
                steps.append(s.id)
        else:
            steps = [scene(f"{name} · {i+1}", rgb=c).id for i, c in enumerate(colors_seq)]

        ch = fm.new_chaser(name)
        ch.run_order = order
        ch.audio_triggered = beat
        ch.beats_per_step = 1
        for sid in steps:
            ch.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
        self.created_function = ch

        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.emit(SyncEvent.FUNCTION_CHANGED, {"id": ch.id})
            sync.emit(SyncEvent.REFRESH_ALL, None)
        except Exception:
            pass
