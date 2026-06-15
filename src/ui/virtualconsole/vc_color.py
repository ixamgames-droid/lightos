"""VCColor — Virtual-Console-Widget, das eine feste Farbe haelt.

Klick (oder gebundene MIDI-Taste/Fader) wendet die Farbe auf die Ziel-Fixtures
an. Die Kachel zeigt die Farbe direkt an. MIDI-Bindung funktioniert identisch
zum VCButton, daher greifen MIDI-Teach (Rechtsklick) und der Canvas-Dispatch
ohne Zusatzcode. Das APC-mk2-LED-Feedback faerbt das gebundene Pad in genau
dieser Farbe (siehe apc_mk2_feedback.py).
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QDialogButtonBox, QSpinBox, QLabel, QPushButton,
                                QCheckBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class ColorTarget(str):
    PROGRAMMER = "Programmer/Selektion"
    ALL = "Alle Fixtures"
    # Phase 6: setzt live die aktuell ausgewaehlte Farbe der Color-Sequence eines
    # Effekts (gebundene function_id oder aktiver Effekt) — Live-Farbsteuerung.
    EFFECT = "Effekt (aktive Farbe)"
    # Live-Color-Chase: HAENGT diese Farbe an die Color-Sequence des Ziel-Effekts
    # an (statt die aktive zu ersetzen) — so baut man per Pad-Druck eine Farbliste
    # zusammen, durch die ein COLORFADE/CHASE-Effekt dann durchlaeuft.
    EFFECT_ADD = "Effekt (Farbe hinzufuegen)"
    # APC-Probier To-Do #5: setzt gezielt color1/2/3 des Ziel-Effekts. Algorithmen
    # wie Feuer/Plasma/Windrad lesen feste color1/2/3 (NICHT die Color-Sequence) —
    # damit lassen sie sich live umfaerben, was ColorTarget.EFFECT dort nicht kann.
    EFFECT_C1 = "Effekt Farbe 1"
    EFFECT_C2 = "Effekt Farbe 2"
    EFFECT_C3 = "Effekt Farbe 3"


# Ziel → Effekt-Parameter-Key fuer die festen Farbslots (To-Do #5).
_EFFECT_COLOR_SLOTS = {
    ColorTarget.EFFECT_C1: "color1",
    ColorTarget.EFFECT_C2: "color2",
    ColorTarget.EFFECT_C3: "color3",
}


class VCColor(VCWidget):
    """Farb-Kachel — wendet eine RGB(+W/A/UV)-Farbe auf Fixtures an."""

    def __init__(self, caption: str = "Farbe", parent=None):
        super().__init__(caption, parent)
        self.color_r = 255
        self.color_g = 255
        self.color_b = 255
        self.color_w = 0       # nur gesendet wenn > 0
        self.color_a = 0
        self.color_uv = 0
        # Intensitaet mitsetzen, damit die Farbe IMMER sichtbar ist (sonst haengt
        # sie von der Intensitaet eines laufenden Effekts ab -> "Farbe geht nicht").
        self.with_intensity = True
        self.intensity = 255
        self.target = ColorTarget.PROGRAMMER
        # Phase 6: Ziel-Effekt fuer ColorTarget.EFFECT (None = aktiver Effekt).
        self.function_id: int | None = None
        # Live-Bearbeitung: Effekt-Ziel aus einem benannten Edit-Slot (von einem
        # Effekt-Pad gesetzt). Greift nur bei EFFECT*-Zielen ohne feste function_id.
        self.edit_slot: str = ""

        # MIDI-Bindung (-1 = keine) — identisch zu VCButton
        self.midi_ch: int = 0
        self.midi_data1: int = -1
        self.midi_type: str = "note_on"

        self._pressed = False
        self._color_picker = None      # schwebender, nicht-modaler Farbwähler
        self.resize(80, 80)

    # ── Farbe als QColor ───────────────────────────────────────────────────────

    def color(self) -> QColor:
        return QColor(self.color_r, self.color_g, self.color_b)

    def set_color(self, c: QColor):
        self.color_r, self.color_g, self.color_b = c.red(), c.green(), c.blue()
        self.update()

    # ── Anwenden ───────────────────────────────────────────────────────────────

    def _target_fids(self, state) -> list[int]:
        if self.target == ColorTarget.PROGRAMMER:
            fids = list(state.programmer.keys())
            if fids:
                return fids
        # Fallback / "Alle": alle gepatchten Fixtures
        out = []
        for f in state.get_patched_fixtures():
            fid = getattr(f, "fid", None)
            if fid is None and isinstance(f, dict):
                fid = f.get("fid") or f.get("id")
            if fid is not None:
                out.append(fid)
        return out

    def _effect_fid(self):
        """Ziel-Effekt für EFFECT*-Kacheln: feste function_id, sonst Live-Edit-Slot,
        sonst None (= aktiver Effekt)."""
        if self.function_id is not None:
            return self.function_id
        if self.edit_slot:
            try:
                from src.core.engine import effect_live
                fid = effect_live.get_edit_target(self.edit_slot)
                if fid is not None:
                    return fid
            except Exception:
                pass
        return None

    def _apply(self):
        if self.target == ColorTarget.EFFECT_ADD:
            # Live-Color-Chase: Farbe an die Color-Sequence des Ziel-Effekts anhaengen.
            try:
                from src.core.engine import effect_live
                effect_live.do_action("add_color", self._effect_fid(),
                                      rgb=(self.color_r, self.color_g, self.color_b))
            except Exception as e:
                print(f"[VCColor] effect add color error: {e}")
            return
        if self.target == ColorTarget.EFFECT:
            # Phase 6: Live in die aktive Sequence-Farbe des Effekts faerben.
            try:
                from src.core.engine import effect_live
                effect_live.set_selected_color(
                    (self.color_r, self.color_g, self.color_b), self._effect_fid())
            except Exception as e:
                print(f"[VCColor] effect color error: {e}")
            return
        if self.target in _EFFECT_COLOR_SLOTS:
            # To-Do #5: gezielt color1/2/3 des Effekts setzen (Feuer/Plasma/Windrad).
            try:
                from src.core.engine import effect_live
                effect_live.set_param(_EFFECT_COLOR_SLOTS[self.target],
                                      (self.color_r, self.color_g, self.color_b),
                                      self._effect_fid())
            except Exception as e:
                print(f"[VCColor] effect color-slot error: {e}")
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            for fid in self._target_fids(state):
                if self.with_intensity:
                    state.set_programmer_value(fid, "intensity", self.intensity)
                state.set_programmer_value(fid, "color_r", self.color_r)
                state.set_programmer_value(fid, "color_g", self.color_g)
                state.set_programmer_value(fid, "color_b", self.color_b)
                # color_w IMMER setzen -> klärt Restweiss eines vorigen Looks/Effekts
                state.set_programmer_value(fid, "color_w", self.color_w)
                if self.color_a:
                    state.set_programmer_value(fid, "color_a", self.color_a)
                if self.color_uv:
                    state.set_programmer_value(fid, "color_uv", self.color_uv)
        except Exception as e:
            print(f"[VCColor] apply error: {e}")

    # ── MIDI (analog VCButton) ─────────────────────────────────────────────────

    def supports_midi_teach(self) -> bool:
        return True

    def current_midi_binding(self):
        if self.midi_data1 is None or self.midi_data1 < 0:
            return None
        return (self.midi_type, self.midi_ch, self.midi_data1)

    def apply_midi_binding(self, msg_type, channel, data1):
        if data1 is None or data1 < 0:
            self.midi_data1 = -1
            return
        self.midi_type = "cc" if msg_type == "cc" else "note_on"
        self.midi_ch = channel or 0
        self.midi_data1 = data1

    def matches_midi(self, msg) -> bool:
        from .vc_widget import midi_binding_matches   # T-6: zentrale Prüfung
        return midi_binding_matches(msg, self.midi_type, self.midi_ch, self.midi_data1)

    def handle_midi(self, msg) -> bool:
        if not self.matches_midi(msg):
            return False
        if msg.msg_type == "note_on" and msg.data2 > 0:
            self._pressed = True
            self._apply()
            self.update()
        elif msg.msg_type in ("note_off",) or (msg.msg_type == "note_on" and msg.data2 == 0):
            self._pressed = False
            self.update()
        elif msg.msg_type == "cc":
            press = msg.data2 > 63
            if press != self._pressed:
                self._pressed = press
                if press:
                    self._apply()
                self.update()
        return True

    # ── Maus ───────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._apply()
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        # Doppelklick öffnet den schwebenden Farbwähler — in BEIDEN Modi: im
        # Edit-Modus zum Einstellen der Kachelfarbe, im Run-Modus zum LIVE-Umfärben.
        # (Die vollen Einstellungen bleiben über Rechtsklick → Einstellungen.)
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_color_picker()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ── Schwebender Farb-Picker (nicht-modal) ────────────────────────────────────

    def _open_color_picker(self):
        """Nicht-modaler, schwebender Farbwähler direkt an der Kachel. Änderungen
        wirken sofort (live); im Run-Modus werden sie auch auf die Fixtures
        angewandt. Anders als der modale Dialog in den Einstellungen blockiert er
        die Bedienung nicht — man kann weiterklicken/-mischen."""
        existing = getattr(self, "_color_picker", None)
        if existing is not None:
            try:
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                self._color_picker = None
        from PySide6.QtWidgets import QColorDialog
        dlg = QColorDialog(self.color(), self)
        dlg.setOption(QColorDialog.ColorDialogOption.NoButtons, True)
        dlg.setModal(False)
        dlg.setWindowTitle(f"Farbe — {self.caption}")
        dlg.currentColorChanged.connect(self._on_live_color)
        dlg.finished.connect(lambda *_: setattr(self, "_color_picker", None))
        self._color_picker = dlg
        dlg.show()

    def _on_live_color(self, c: QColor):
        if c is None or not c.isValid():
            return
        self.color_r, self.color_g, self.color_b = c.red(), c.green(), c.blue()
        self.update()
        # Im Run-Modus die neue Farbe sofort auf die Ziel-Fixtures/-Effekte legen.
        if not self._edit_mode:
            self._apply()

    def _color_overridden(self) -> bool:
        """True, wenn diese Kachel die Programmer-/Alle-Farbe setzt, ein laufender
        Effekt aber gerade die Farbkanaele besitzt (To-Do #9). Effekt-Ziele
        (EFFECT/EFFECT_ADD/EFFECT_C*) sind ausgenommen — die füttern den Effekt."""
        if self.target not in (ColorTarget.PROGRAMMER, ColorTarget.ALL):
            return False
        try:
            from src.core.engine import effect_live
            return effect_live.color_is_effect_driven()
        except Exception:
            return False

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        col = self.color()
        if self._pressed:
            col = col.lighter(130)
        p.fillRect(self.rect(), col)

        # Kontrast-Textfarbe
        lum = self.color_r + self.color_g + self.color_b
        text_col = QColor("#000") if lum > 380 else QColor("#fff")
        p.setPen(text_col)
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                   self.caption)

        if self._pressed:
            p.setPen(QPen(QColor("#ffffff"), 3))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))

        # To-Do #9: Kontext-Hinweis — wenn ein laufender Effekt die Farbe „besitzt"
        # (RGB/RGBW-Matrix), bringt eine Programmer/Alle-Kachel nichts Sichtbares.
        # Kachel abdunkeln + Schloss-Symbol; nur im Run-Modus.
        if not self._edit_mode and self._color_overridden():
            p.fillRect(self.rect(), QColor(0, 0, 0, 150))   # ausgrauen
            p.setPen(QColor("#ffd700"))
            f = QFont("Segoe UI", 14)
            p.setFont(f)
            p.drawText(6, 20, "🔒")

        # MIDI-Bindung-Indikator oben rechts
        if self.midi_data1 >= 0:
            p.fillRect(self.width() - 8, 0, 8, 8, QColor("#00aaff"))

        # Edit-Mode: Resize-Handle + Auswahlrahmen wieder einzeichnen
        if self._edit_mode:
            hs = self.HANDLE_SIZE
            r = self.rect()
            p.fillRect(r.right() - hs, r.bottom() - hs, hs, hs, QColor("#0088ff"))
            if self._selected:
                p.setPen(QPen(QColor("#58d68d"), 2))
            else:
                p.setPen(QPen(QColor("#0088ff"), 1, Qt.PenStyle.DashLine))
            p.drawRect(r.adjusted(0, 0, -1, -1))
        p.end()

    # ── Properties ─────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Farb-Kachel Einstellungen")
        form = QFormLayout(dlg)

        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)

        # Farbauswahl
        btn_color = QPushButton()
        btn_color.setFixedHeight(28)

        def _refresh_swatch():
            c = self.color()
            tc = "#000" if (self.color_r + self.color_g + self.color_b) > 380 else "#fff"
            btn_color.setStyleSheet(
                f"background: rgb({c.red()},{c.green()},{c.blue()}); color:{tc};"
                "border:1px solid #555; border-radius:3px;")
            btn_color.setText(f"RGB {c.red()},{c.green()},{c.blue()}")

        def _pick():
            from PySide6.QtWidgets import QColorDialog
            c = QColorDialog.getColor(self.color(), dlg, "Farbe waehlen")
            if c.isValid():
                self.color_r, self.color_g, self.color_b = c.red(), c.green(), c.blue()
                _refresh_swatch()
        btn_color.clicked.connect(_pick)
        _refresh_swatch()
        form.addRow("Farbe:", btn_color)

        # WP-9: gespeicherte Farb-Paletten (im Programmer aufgezeichnet) direkt
        # waehlbar. Liste wird bei JEDEM Oeffnen frisch geladen -> neu gespeicherte
        # Farben erscheinen sofort (kein Neuladen/Neustart noetig).
        pal_cb = QComboBox()
        pal_cb.addItem("— gespeicherte Farbe wählen —", None)
        try:
            from src.core.engine.palette import get_palette_manager, PaletteType
            for p in get_palette_manager().get_by_type(PaletteType.COLOR):
                pal_cb.addItem(p.name, p)
        except Exception as e:
            print(f"[VCColor] palette list error: {e}")

        def _pick_palette(idx):
            p = pal_cb.itemData(idx)
            if p is None:
                return
            vals = getattr(p, "values", {}) or {}
            self.color_r = int(vals.get("color_r", self.color_r))
            self.color_g = int(vals.get("color_g", self.color_g))
            self.color_b = int(vals.get("color_b", self.color_b))
            _refresh_swatch()
            if cap.text().strip() in ("", "Farbe"):
                cap.setText(p.name)
        pal_cb.currentIndexChanged.connect(_pick_palette)
        form.addRow("Aus Palette:", pal_cb)

        # Helligkeit mitsenden: AN = Kachel setzt auch Intensitaet (sofort hell,
        # aber kollidiert mit Dimmer-Effekten). AUS = reine Farb-Ebene (empfohlen,
        # wenn die Fixtures eine Basis-Helligkeit haben) -> Dimmer-Effekte dunkeln.
        intens_chk = QCheckBox("Helligkeit mitsenden (aus = nur Farbe)")
        intens_chk.setChecked(self.with_intensity)
        form.addRow("Modus:", intens_chk)
        i_spin = QSpinBox(); i_spin.setRange(0, 255); i_spin.setValue(self.intensity)
        form.addRow("Helligkeit (falls aktiv):", i_spin)

        w_spin = QSpinBox(); w_spin.setRange(0, 255); w_spin.setValue(self.color_w)
        form.addRow("White (0=aus):", w_spin)
        a_spin = QSpinBox(); a_spin.setRange(0, 255); a_spin.setValue(self.color_a)
        form.addRow("Amber (0=aus):", a_spin)
        uv_spin = QSpinBox(); uv_spin.setRange(0, 255); uv_spin.setValue(self.color_uv)
        form.addRow("UV (0=aus):", uv_spin)

        target_cb = QComboBox()
        target_cb.addItems([ColorTarget.PROGRAMMER, ColorTarget.ALL, ColorTarget.EFFECT,
                            ColorTarget.EFFECT_ADD, ColorTarget.EFFECT_C1,
                            ColorTarget.EFFECT_C2, ColorTarget.EFFECT_C3])
        target_cb.setCurrentText(self.target)
        form.addRow("Ziel:", target_cb)

        # Phase 6: Ziel-Effekt-ID (nur Ziel = Effekt; leer = aktiver Effekt)
        fid_edit = QLineEdit("" if self.function_id is None else str(self.function_id))
        fid_edit.setToolTip("Funktions-ID des Ziel-Effekts (Ziel = Effekt). Leer = aktiver Effekt.")
        form.addRow("Effekt-ID (Ziel=Effekt):", fid_edit)
        # Live-Edit-Slot: greift bei EFFECT*-Zielen ohne feste ID.
        edit_slot_edit = QLineEdit(self.edit_slot)
        edit_slot_edit.setToolTip("Live-Edit-Slot (Freitext, z. B. MX). Färbt den Effekt aus "
                                  "diesem Slot, falls keine feste Effekt-ID gesetzt ist.")
        form.addRow("Live-Edit-Slot:", edit_slot_edit)

        form.addRow(QLabel("── MIDI-Bindung (oder Rechtsklick → Teach) ──"))
        midi_type_combo = QComboBox()
        midi_type_combo.addItems(["note_on", "cc"])
        midi_type_combo.setCurrentText(self.midi_type)
        form.addRow("MIDI-Typ:", midi_type_combo)
        midi_ch_spin = QSpinBox(); midi_ch_spin.setRange(0, 16)
        midi_ch_spin.setValue(self.midi_ch); midi_ch_spin.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", midi_ch_spin)
        midi_note_spin = QSpinBox(); midi_note_spin.setRange(-1, 127)
        midi_note_spin.setValue(self.midi_data1); midi_note_spin.setSpecialValueText("keine")
        form.addRow("Note / CC (-1=keine):", midi_note_spin)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.with_intensity = intens_chk.isChecked()
            self.intensity = i_spin.value()
            self.color_w = w_spin.value()
            self.color_a = a_spin.value()
            self.color_uv = uv_spin.value()
            self.target = target_cb.currentText()
            _ftxt = fid_edit.text().strip()
            self.function_id = int(_ftxt) if _ftxt.lstrip("-").isdigit() else None
            self.edit_slot = edit_slot_edit.text().strip()
            self.midi_type = midi_type_combo.currentText()
            self.midi_ch = midi_ch_spin.value()
            self.midi_data1 = midi_note_spin.value()
            self.update()

    # ── Serialisierung ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["color_r"] = self.color_r
        d["color_g"] = self.color_g
        d["color_b"] = self.color_b
        d["color_w"] = self.color_w
        d["color_a"] = self.color_a
        d["color_uv"] = self.color_uv
        d["with_intensity"] = self.with_intensity
        d["intensity"] = self.intensity
        d["target"] = self.target
        d["function_id"] = self.function_id
        d["edit_slot"] = self.edit_slot
        d["midi_ch"] = self.midi_ch
        d["midi_data1"] = self.midi_data1
        d["midi_type"] = self.midi_type
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.color_r = d.get("color_r", 255)
        self.color_g = d.get("color_g", 255)
        self.color_b = d.get("color_b", 255)
        self.color_w = d.get("color_w", 0)
        self.color_a = d.get("color_a", 0)
        self.color_uv = d.get("color_uv", 0)
        self.with_intensity = bool(d.get("with_intensity", True))
        self.intensity = d.get("intensity", 255)
        self.target = d.get("target", ColorTarget.PROGRAMMER)
        self.function_id = d.get("function_id")
        self.edit_slot = d.get("edit_slot", "")
        self.midi_ch = d.get("midi_ch", 0)
        self.midi_data1 = d.get("midi_data1", -1)
        self.midi_type = d.get("midi_type", "note_on")
