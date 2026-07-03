"""VCEffectEditor — beweglicher Effekt-Editor-Container (Welle 4, L/N).

Subklasse von ``VCFrame``: haelt die Bedien-Widgets EINES Effekts zusammen in
einer verschiebbaren Box mit Live-Vorschau oben. Erbt von VCFrame: Kinder als
Qt-Child-Widgets, Snap-out/Snap-in (``vc_canvas.handle_drag_drop`` FRM-01),
Seiten, Serialisierung der Kinder. Zusatz:
  - ``effect_id``  -> Header-Beschriftung + eingebettete Live-Vorschau,
  - ``EffectMiniPreview`` in einem reservierten Band (``_preview_h``),
  - ``add_effect_child()`` schliesst die Delete-Verdrahtungs-Luecke
    (``add_child_to_page`` allein verdrahtet ``delete_requested`` NICHT).

Bedienelement-Auswahl (wie ein Matrix-Programmer): Statt stur feste Slider zu
bauen, hat die Box ein **Auswahlmenue** (⚙-Knopf im Kopf, ODER automatisch beim
frischen Draufziehen eines Effekts). Es zeigt — gefiltert auf die Faehigkeiten
des Effekts (``vc_effect_meta.control_options``) — alle live steuerbaren Aspekte
(Tempo/Helligkeit/Farben/Bewegung/einzelne Parameter/Aktionen) als Checkboxen;
Angekreuztes wird als passendes Widget (Slider/Knopf/Auswahl/XY) IN die Box
gebaut (ueber ``VCCanvas.build_results_into_box``). So waehlt der Nutzer selbst,
was er live regeln will. Dieselbe Karte (``VCDropPanel``) wie beim Smart-Drop.

Die Beschriftung der Kind-Widgets ist bereits korrekt (``aspect_caption`` im
Smart-Drop) — die Box erbt sie kostenlos.
"""
from __future__ import annotations
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QToolButton
from .vc_frame import VCFrame


class VCEffectEditor(VCFrame):
    """Beweglicher Container fuer die Bedien-Widgets eines Effekts + Live-Vorschau."""

    def __init__(self, caption: str = "Effekt-Editor", parent=None):
        super().__init__(caption, parent)
        self.effect_id: int | None = None
        self._preview = None          # EffectMiniPreview (plain QWidget, KEIN VCWidget)
        self._preview_h: int = 72     # reserviertes Vorschau-Band oben
        # ⚙-Knopf im Kopf: oeffnet das Bedienelement-Auswahlmenue (nur Edit-Modus).
        # Plain QToolButton (KEIN VCWidget) -> wird nicht serialisiert, taucht nicht
        # in findChildren(VCWidget) auf (wie die Vorschau).
        self._gear_btn = QToolButton(self)
        self._gear_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._gear_btn.setText("⚙")
        self._gear_btn.setToolTip("Bedienelemente wählen — welche Effekt-Parameter "
                                  "live steuerbar sind (Slider/Knöpfe/Auswahl). "
                                  "Ohne gebundenen Effekt: erst Effekt per Name wählen.")
        self._gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Groesse/Beschriftung setzt _reposition_chrome adaptiv (Touch vs. Maus,
        # leer vs. befuellt) — daher hier KEIN festes setFixedSize.
        self._gear_btn.setStyleSheet(
            "QToolButton { border:1px solid #2d333b; border-radius:4px;"
            " background:#21262d; color:#c9d1d9; font-size:13px; padding:2px 6px; }"
            "QToolButton:hover { background:#30363d; color:#58a6ff; }")
        self._gear_btn.clicked.connect(self._on_gear_clicked)
        self._gear_btn.hide()
        self.resize(360, 220)

    # ── Effekt + Vorschau ──────────────────────────────────

    def set_effect(self, fid, open_chooser: bool = False):
        """Bindet die Box an einen Effekt: Header = Effektname, Vorschau in der
        ECHTEN Geraetegroesse des Effekts. Es werden KEINE festen Regler mehr
        automatisch gebaut — welche Bedienelemente die Box bekommt, waehlt der
        Nutzer im Auswahlmenue (⚙ / ``open_control_chooser``).

        ``open_chooser=True`` (frischer interaktiver Drop auf eine noch leere Box)
        oeffnet das Auswahlmenue sofort. Fuer Typen ohne Live-Parameter
        (Szene/Chaser) wird KEIN Editor gezeigt (preview_h=0)."""
        if fid is None:
            return
        self.effect_id = int(fid)
        try:
            from .vc_effect_meta import effect_name
            self.caption = effect_name(self.effect_id)
        except Exception:
            pass
        fn = None
        try:
            from src.core.engine import effect_live
            fn = effect_live.resolve_target(self.effect_id)
        except Exception:
            fn = None
        # Sinn-Guard: nur Matrix/EFX (Algorithmus + Live-Parameter) bekommen einen Editor.
        if fn is None or not hasattr(fn, "algorithm") or not hasattr(fn, "list_params"):
            self._preview_h = 0
            if self._preview is not None:
                self._preview.hide()
            self._reposition_chrome()
            self.update()
            return
        self._ensure_preview()
        if self._preview is not None:
            try:
                from src.core.engine.rgb_matrix import RgbMatrixInstance
                if isinstance(fn, RgbMatrixInstance):
                    self._preview.play_effect(fn, label=self.caption)
                else:
                    cols = int(getattr(fn, "cols", 8) or 8)
                    rows = int(getattr(fn, "rows", 1) or 1)
                    grid = list(getattr(fn, "fixture_grid", []) or [])
                    self._preview.set_grid(cols, rows, grid or None)
                    self._preview.play(
                        algorithm=getattr(fn, "algorithm", None),
                        color1=getattr(fn, "color1", None),
                        color2=getattr(fn, "color2", None),
                        speed=getattr(fn, "matrix_speed", None),
                        label=self.caption)
            except Exception:
                pass
        self._reposition_chrome()
        self.update()
        # Frischer Drop auf eine noch leere Box -> direkt das Auswahlmenue oeffnen,
        # damit der Nutzer gleich seine Bedienelemente waehlt (statt fester Regler).
        if open_chooser and not self._control_children():
            self.open_control_chooser()

    # ── Bedienelement-Auswahlmenue (Matrix-Programmer-artig) ────────────

    def open_control_chooser(self):
        """Oeffnet die Checkbox-Auswahlkarte (``VCDropPanel`` fuer diesen Effekt)
        und baut die angekreuzten Aspekte als Bedien-Widgets IN die Box. Schon
        vorhandene, gleichartige Regler werden nicht doppelt gebaut (Entfernen per
        Rechtsklick → Löschen, undobar)."""
        if self.effect_id is None:
            return
        try:
            from .vc_drop_panel import VCDropPanel
        except Exception:
            return
        canvas = self._find_canvas()
        if canvas is None or not hasattr(canvas, "build_results_into_box"):
            return
        panel = VCDropPanel(self.effect_id, parent=self, for_box=True)
        results = panel.run()
        if not results:
            return
        present = self._present_signatures()
        fresh = [r for r in results if self._result_signature(r) not in present]
        if not fresh:
            return
        canvas.build_results_into_box(self, fresh)

    def _on_gear_clicked(self):
        """⚙: ohne gebundenen Effekt erst Effekt per Name waehlen (touch, kein
        Drag noetig), sonst direkt die Bedienelement-Auswahl oeffnen."""
        if self.effect_id is None:
            self.choose_effect()
        else:
            self.open_control_chooser()

    def choose_effect(self):
        """Effekt per NAME auswaehlen (touch-tauglich, ohne Drag) -> binden +
        Bedienelement-Auswahl oeffnen. Greift auf die nach Namen sortierte
        Funktionsliste zu (gleiche Quelle wie die „Steuert"-Listen)."""
        try:
            from PySide6.QtWidgets import QInputDialog
            from .target_list_editor import _all_functions
        except Exception:
            return
        funcs = _all_functions()
        if not funcs:
            return
        labels = [lbl for _id, lbl in funcs]
        cur = 0
        if self.effect_id is not None:
            cur = next((i for i, (fid, _l) in enumerate(funcs)
                        if fid == self.effect_id), 0)
        label, ok = QInputDialog.getItem(
            self, "Effekt wählen", "Welchen Effekt soll diese Box steuern?",
            labels, cur, False)
        if not ok:
            return
        fid = next((fid for fid, lbl in funcs if lbl == label), None)
        if fid is not None:
            self.set_effect(int(fid), open_chooser=True)

    @staticmethod
    def _is_touch() -> bool:
        try:
            from src.ui.touch_keyboard import is_touch_mode
            return bool(is_touch_mode())
        except Exception:
            return False

    def _control_children(self) -> list:
        """Direkte Bedien-Kinder (VCWidgets) der Box — ohne Vorschau/⚙ (keine VCWidgets)."""
        from .vc_widget import VCWidget
        return self.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)

    def _present_signatures(self) -> set:
        return {self._widget_signature(w) for w in self._control_children()}

    @staticmethod
    def _widget_signature(w) -> tuple:
        """Grobe Signatur eines vorhandenen Bedien-Widgets (fuer Dedup gegen die
        Auswahl). param_key/effect_action_key zaehlen NUR, wenn sie den Aspekt
        wirklich unterscheiden (EFFECT_PARAM bzw. EFFECT_ACTION) — sonst wuerde der
        Default eines frisch gebauten Widgets nie zur (leeren) Auswahl passen.
        Best-effort — bei Nicht-Treffer wird hoechstens ein Duplikat zugelassen
        (per Rechtsklick loeschbar)."""
        cn = type(w).__name__
        if cn == "VCButton":
            from .vc_button import ButtonAction
            act = getattr(w, "action", None)
            if act == ButtonAction.EFFECT_ACTION:
                return ("VCButton", str(act), str(getattr(w, "effect_action_key", "") or ""))
            return ("VCButton", str(act))
        if cn == "VCSlider":
            from .vc_slider import SliderMode
            mode = getattr(w, "mode", None)
            if mode == SliderMode.EFFECT_PARAM:
                return ("VCSlider", str(mode), str(getattr(w, "param_key", "") or ""))
            return ("VCSlider", str(mode))
        if cn in ("VCEncoder", "VCStepper"):
            return (cn, str(getattr(w, "param_key", "") or ""))
        if cn == "VCSpeedDial":
            return ("VCSpeedDial", str(getattr(w, "target_mode", "")))
        return (cn,)

    @staticmethod
    def _result_signature(res) -> tuple:
        """Signatur eines SmartDropResult, gespiegelt zu ``_widget_signature``."""
        wt = getattr(res, "widget_type", "")
        if wt == "VCButton":
            from .vc_button import ButtonAction
            act = getattr(res, "action", None)
            if act == ButtonAction.EFFECT_ACTION:
                return ("VCButton", str(act), str(getattr(res, "effect_action_key", "") or ""))
            return ("VCButton", str(act))
        if wt == "VCSlider":
            from .vc_slider import SliderMode
            mode = getattr(res, "slider_mode", None)
            if mode == SliderMode.EFFECT_PARAM:
                return ("VCSlider", str(mode), str(getattr(res, "param_key", "") or ""))
            return ("VCSlider", str(mode))
        if wt in ("VCEncoder", "VCStepper"):
            return (wt, str(getattr(res, "param_key", "") or ""))
        if wt == "VCSpeedDial":
            return ("VCSpeedDial", str(getattr(res, "speed_target", "") or ""))
        return (wt,)

    def _relayout_controls(self):
        """Legt alle Bedien-Kinder in einer Reihe unter dem Vorschau-Band ab und
        vergroessert die Box bei Bedarf (Wachstum, nie Schrumpfen)."""
        kids = self._control_children()
        if not kids:
            return
        pad = getattr(self, "GRID", 8) or 8
        band = (self._tab_height if self._show_header else 0) + 2 + self._preview_h
        max_h = max((c.height() for c in kids), default=40)
        total_w = sum(c.width() + pad for c in kids) + pad
        self.resize(max(self.width(), total_w),
                    max(self.height(), band + max_h + 2 * pad))
        cx, cy = pad, band + pad
        for w in kids:
            w.move(cx, cy)
            cx += w.width() + pad
        self._reposition_chrome()    # ⚙ von „grosser Knopf" auf Eck-Zahnrad umstellen

    def build_default_controls(self) -> list:
        """Baut einen sinnvollen Standard-Satz Bedien-Regler (Tempo/Helligkeit je
        nach Faehigkeiten des Effekts) als Kinder — fuer HEADLESS/programmatische
        Nutzung (Show-Generatoren), wo kein interaktives Auswahlmenue laeuft.
        Im Live-App-Pfad waehlt der Nutzer stattdessen ueber ``open_control_chooser``.
        No-op, wenn kein Effekt gebunden ist oder die Box schon Regler hat."""
        if self.effect_id is None or self._control_children():
            return []
        try:
            from .vc_effect_meta import function_capabilities
            from .vc_slider import VCSlider, SliderMode
        except Exception:
            return []
        try:
            caps = function_capabilities(self.effect_id)
        except Exception:
            return []
        built: list = []
        if getattr(caps, "has_speed", False):
            s = VCSlider("FX Speed")
            s.mode = SliderMode.EFFECT_SPEED
            s.function_id = self.effect_id
            built.append(s)
        if getattr(caps, "has_intensity", False):
            s = VCSlider("Helligkeit")
            s.mode = SliderMode.EFFECT_INTENSITY
            s.function_id = self.effect_id
            built.append(s)
        for s in built:
            self.add_effect_child(s, self._current_page)
        self._relayout_controls()
        return built

    def _ensure_preview(self):
        if self._preview is not None:
            return
        try:
            from src.ui.widgets.effect_mini_preview import EffectMiniPreview
            self._preview = EffectMiniPreview(8, 4, parent=self)
            self._preview.show()
        except Exception:
            self._preview = None

    def _reposition_preview(self):
        if self._preview is None:
            return
        top = self._tab_height if self._show_header else 0
        self._preview.setGeometry(2, top + 2, max(10, self.width() - 4), self._preview_h)

    def _reposition_chrome(self):
        """Vorschau + ⚙-Knopf neu platzieren. Der ⚙ ist touch-tauglich:
          - leere Box  -> grosser, beschrifteter Tap-Knopf im Inhaltsbereich
            („⚙ Effekt wählen" ohne gebundenen Effekt, sonst „⚙ Bedienelemente wählen"),
          - befuellte Box -> kompaktes Zahnrad oben rechts (im Touch-Modus groesser).
        Nur im Edit-Modus sichtbar (kein versehentliches Antippen im Betrieb)."""
        self._reposition_preview()
        g = getattr(self, "_gear_btn", None)
        if g is None:
            return
        if not self._edit_mode:
            g.setVisible(False)
            return
        g.setVisible(True)
        touch = self._is_touch()
        if self._control_children():
            # Befuellte Box: kompaktes Eck-Zahnrad (Touch -> groesser).
            gw, gh = (40, 30) if touch else (24, 22)
            g.setText("⚙")
            g.setFixedSize(gw, gh)
            g.move(max(2, self.width() - gw - 3), 2)
        else:
            # Leere Box: grosser, beschrifteter Tap-Knopf im Inhaltsbereich.
            g.setText("⚙  Effekt wählen" if self.effect_id is None
                      else "⚙  Bedienelemente wählen")
            bh = 52 if touch else 36
            bw = max(180, self.width() - 24)
            band = (self._tab_height if self._show_header else 0) + 2 + max(0, self._preview_h)
            g.setFixedSize(bw, bh)
            g.move(max(2, (self.width() - bw) // 2), band + 8)
        g.raise_()

    def _remove_child(self, widget):
        # Nach dem Entfernen den ⚙-Zustand (Eck vs. grosser Knopf) auffrischen.
        super()._remove_child(widget)
        self._reposition_chrome()

    def set_edit_mode(self, enabled: bool):
        super().set_edit_mode(enabled)
        self._reposition_chrome()

    # ── Layout: Vorschau-Band aus dem Content-Bereich reservieren ──────────

    def _content_rect(self) -> QRect:
        r = super()._content_rect()
        if self._preview is not None and self._preview_h:
            r.setTop(r.top() + self._preview_h)
        return r

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_chrome()

    # ── CPU: Vorschau-Timer an Sichtbarkeit koppeln (off-bank -> Timer aus) ─────

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._preview is not None:
            try:
                self._preview._timer.stop()
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        self._reposition_chrome()
        if self._preview is not None:
            try:
                self._preview._timer.start(50)
            except Exception:
                pass

    # ── Kind hinzufuegen MIT Delete-Verdrahtung ────────────────────

    def add_effect_child(self, widget, page: int = 0):
        """Wie add_child_to_page, aber verdrahtet ``delete_requested`` an
        ``_remove_child`` (die Basis-Methode tut das NICHT) — sonst liesse sich ein
        in die Box gebautes Widget nicht per Rechtsklick „Loeschen" entfernen.
        Vorher bestehende (Canvas-)Verdrahtung wird geloest (kein Doppel-Delete)."""
        self.add_child_to_page(widget, page)
        try:
            widget.delete_requested.disconnect()
        except (TypeError, RuntimeError):
            pass
        # STAB-09: sender()-Adapter (geerbt von VCFrame) statt self-fangendem Lambda.
        widget.delete_requested.connect(self._on_child_delete_requested)

    # ── Serialisierung ────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()          # type=VCEffectEditor, Kinder, caption, geometry …
        d["effect_id"] = self.effect_id
        d["preview_h"] = self._preview_h
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)          # baut Kinder + verdrahtet deren delete neu
        self._preview_h = int(d.get("preview_h", 72))
        eid = d.get("effect_id")
        if eid is not None:
            self.set_effect(int(eid))  # Header + Vorschau wiederherstellen (KEIN Chooser)
