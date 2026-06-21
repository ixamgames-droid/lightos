"""VCEffectEditor — beweglicher Effekt-Editor-Container (Welle 4, L/N).

Subklasse von ``VCFrame``: haelt die Bedien-Widgets EINES Effekts zusammen in
einer verschiebbaren Box mit Live-Vorschau oben. Erbt von VCFrame: Kinder als
Qt-Child-Widgets, Snap-out/Snap-in (``vc_canvas.handle_drag_drop`` FRM-01),
Seiten, Serialisierung der Kinder. Zusatz:
  - ``effect_id``  -> Header-Beschriftung + eingebettete Live-Vorschau,
  - ``EffectMiniPreview`` in einem reservierten Band (``_preview_h``),
  - ``add_effect_child()`` schliesst die Delete-Verdrahtungs-Luecke
    (``add_child_to_page`` allein verdrahtet ``delete_requested`` NICHT).

Die Beschriftung der Kind-Widgets ist bereits korrekt (``aspect_caption`` im
Smart-Drop) — die Box erbt sie kostenlos.
"""
from __future__ import annotations
from PySide6.QtCore import QRect
from .vc_frame import VCFrame


class VCEffectEditor(VCFrame):
    """Beweglicher Container fuer die Bedien-Widgets eines Effekts + Live-Vorschau."""

    def __init__(self, caption: str = "Effekt-Editor", parent=None):
        super().__init__(caption, parent)
        self.effect_id: int | None = None
        self._preview = None          # EffectMiniPreview (plain QWidget, KEIN VCWidget)
        self._preview_h: int = 72     # reserviertes Vorschau-Band oben
        self.resize(360, 220)

    # ── Effekt + Vorschau ─────────────────────────────────────────────────────

    def set_effect(self, fid):
        """Bindet die Box an einen Effekt: Header = Effektname, Vorschau in der
        ECHTEN Geraetegroesse des Effekts, plus einstellbare Live-Regler
        (Speed/Intensitaet/Size). Fuer Typen ohne Live-Parameter (Szene/Chaser)
        wird KEIN Editor gezeigt (preview_h=0) — Editor nur, wo er Sinn macht."""
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
            self.update()
            return
        self._ensure_preview()
        if self._preview is not None:
            try:
                cols = int(getattr(fn, "cols", 8) or 8)
                rows = int(getattr(fn, "rows", 1) or 1)
                grid = list(getattr(fn, "fixture_grid", []) or [])
                self._preview.set_grid(cols, rows, grid or None)
            except Exception:
                pass
            try:
                self._preview.play(
                    algorithm=getattr(fn, "algorithm", None),
                    color1=getattr(fn, "color1", None),
                    color2=getattr(fn, "color2", None),
                    speed=getattr(fn, "matrix_speed", None),
                    label=self.caption)
            except Exception:
                pass
        self._build_param_controls()
        self._reposition_preview()
        self.update()

    def _build_param_controls(self):
        """Pro sinnvollem Numerik-Parameter (Speed/Intensitaet/Size) einen
        EFFECT_PARAM-Fader unter die Vorschau haengen -> die Box ist EINSTELLBAR,
        nicht nur Anzeige. Lade-sicher: nur bauen, wenn die Box noch keine
        (aus der Serialisierung wiederhergestellten) Kind-Widgets hat."""
        from PySide6.QtCore import Qt
        from .vc_widget import VCWidget
        if self.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            return
        try:
            from src.core.engine import effect_live
            from .vc_slider import VCSlider, SliderMode
        except Exception:
            return
        want = ("matrix_speed", "speed", "intensity", "size")
        picked, seen = [], set()
        try:
            for s in effect_live.list_params(self.effect_id):
                key = getattr(s, "key", "")
                if key not in want or getattr(s, "kind", "") not in ("int", "float"):
                    continue
                norm = "speed" if key in ("speed", "matrix_speed") else key
                if norm in seen:
                    continue
                seen.add(norm)
                picked.append(s)
        except Exception:
            return
        picked = picked[:3]
        if not picked:
            return
        top = (self._tab_height if self._show_header else 0) + self._preview_h + 4
        fw, gap = 52, 6
        for i, s in enumerate(picked):
            sl = VCSlider(getattr(s, "label", None) or s.key)
            sl.mode = SliderMode.EFFECT_PARAM
            sl.function_ids = [self.effect_id]
            sl.param_key = s.key
            sl._value = 160
            sl.setGeometry(4 + i * (fw + gap), top, fw, max(60, self.height() - top - 6))
            self.add_effect_child(sl, 0)

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

    # ── Layout: Vorschau-Band aus dem Content-Bereich reservieren ──────────────

    def _content_rect(self) -> QRect:
        r = super()._content_rect()
        if self._preview is not None and self._preview_h:
            r.setTop(r.top() + self._preview_h)
        return r

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_preview()

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
        if self._preview is not None:
            try:
                self._preview._timer.start(50)
            except Exception:
                pass

    # ── Kind hinzufuegen MIT Delete-Verdrahtung ────────────────────────────────

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
        widget.delete_requested.connect(lambda w=widget: self._remove_child(w))

    # ── Serialisierung ─────────────────────────────────────────────────────────

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
            self.set_effect(int(eid))  # Header + Vorschau wiederherstellen
