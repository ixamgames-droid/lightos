"""Render a single editor widget at a constrained size and save it to PNG.

Used to reproduce / document the "fields too small / squished" display bug
deterministically (a widget.grab() IS the real rendering), so we get clean
before/after evidence without fighting live-app navigation.

Usage (run with the venv python from the inner project root):
    python docs/_walkthrough/render_editor.py <target> <out.png> [W] [H]

targets:
    efx        -> EfxView (Bewegungen)
    color      -> ColorPicker on the "Full" tab (RGB/HSB/CMY/White...)
    effectlayer-> EffectLayerEditor
    carousel   -> CarouselEditor
    chaser     -> ChaserEditor
    sequence   -> SequenceEditor
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QTabWidget
from PySide6.QtCore import Qt


def build(target):
    if target == "efx":
        from src.ui.views.efx_view import EfxView
        w = EfxView()
        # make sure at least one EFX exists so the editor shows populated fields
        try:
            if w._list.count() == 0:
                w._add_efx()
        except Exception as e:
            print("efx seed:", e)
        return w
    if target == "color":
        from src.ui.widgets.color_picker import ColorPicker
        w = ColorPicker()
        # switch to the dense "Full" tab
        tabs = w.findChild(QTabWidget)
        if tabs is not None and tabs.count() > 1:
            tabs.setCurrentIndex(1)
        return w
    if target == "effectlayer":
        from src.ui.views.effect_layer_editor import EffectLayerEditor
        from src.core.engine.effect_func import LayeredEffect
        return EffectLayerEditor(LayeredEffect())
    if target == "carousel":
        from src.ui.views.carousel_editor import CarouselEditor
        from src.core.engine.carousel import Carousel
        return CarouselEditor(Carousel())
    if target == "chaser":
        from src.ui.views.chaser_editor import ChaserEditor
        from src.core.engine.chaser import Chaser
        return ChaserEditor(Chaser())
    if target == "sequence":
        from src.ui.views.sequence_editor import SequenceEditor
        from src.core.engine.sequence import Sequence
        return SequenceEditor(Sequence())
    if target == "scene":
        from src.ui.views.scene_editor import SceneEditor
        from src.core.engine.scene import Scene
        return SceneEditor(Scene())
    if target == "audio":
        from src.ui.views.audio_editor import AudioEditor
        from src.core.engine.audio_func import AudioFunction
        return AudioEditor(AudioFunction())
    raise SystemExit(f"unknown target {target}")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "efx"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.environ.get("TEMP", "."), f"render_{target}.png")
    w_px = int(sys.argv[3]) if len(sys.argv) > 3 else 560
    h_px = int(sys.argv[4]) if len(sys.argv) > 4 else 620

    app = QApplication.instance() or QApplication(sys.argv)
    w = build(target)
    w.resize(w_px, h_px)
    w.show()
    app.processEvents()
    app.processEvents()
    pm = w.grab()
    pm.save(out, "PNG")
    print(f"saved {out} ({pm.width()}x{pm.height()}) target={target} req={w_px}x{h_px}")


if __name__ == "__main__":
    main()
