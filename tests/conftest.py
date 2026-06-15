"""Gemeinsame Test-Fixtures.

Stabilisiert die Gesamt-Suite: VCCanvas abonniert beim Erzeugen den globalen
MIDI-Manager und meldet sich erst bei seiner Zerstoerung (destroyed/closeEvent)
wieder ab. Viele Tests erzeugen Canvases, ohne sie zu schliessen — die toten
Callbacks haeuften sich ueber die Suite an und konnten in einem spaeteren Test zu
einem harten Crash fuehren. Diese Autouse-Fixture meldet nach JEDEM Test alle noch
lebenden Canvases ab.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Den 44-Hz-DMX-Output-Thread in Tests gar nicht erst autostarten (siehe
# app_state.get_state): er rendert in _render_frame und emittiert Sync-Events,
# die cross-thread in Qt marshallt werden -> race mit dem pytest-Teardown
# (processEvents/GC abgemeldeter Widgets) = sporadische native Access Violation.
# MUSS vor dem ersten get_state() gesetzt sein -> hier am conftest-Kopf.
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _stop_background_threads_at_end():
    """Sicherheitsnetz: am Suite-Ende einen ggf. doch laufenden Output-Thread
    stoppen (z. B. wenn ein Test ihn explizit gestartet hat), damit der
    Interpreter-Shutdown nicht mit einem laufenden Thread auf freigegebene
    Objekte trifft."""
    yield
    try:
        from src.core import app_state as _A
        st = getattr(_A, "_state", None)
        om = getattr(st, "output_manager", None) if st is not None else None
        if om is not None and getattr(om, "_running", False):
            om.stop()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _cleanup_vc_canvases():
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        for w in list(app.allWidgets()):
            if isinstance(w, VCCanvas):
                try:
                    w._teardown_midi()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        app.processEvents()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _restore_app_state_singleton():
    """Schuetzt die Gesamt-Suite vor undichten Instanz-Monkeypatches am globalen
    AppState-Singleton.

    Einige Tests ersetzen Methoden direkt auf der Instanz (z. B.
    ``state.get_patched_fixtures = lambda: [...]``), um Fake-Fixtures einzuspielen.
    Wird das nach dem Test nicht zurueckgenommen, verdeckt das Instanz-Attribut
    dauerhaft die Klassenmethode: nachfolgende Tests bekommen die alten Fakes
    geliefert, und sogar ein ``patch.object(type(state), ...)`` bleibt wirkungslos
    (die Instanz-Bindung gewinnt). Genau das liess test_simple_desk_tint und
    test_vc_slider_group_scope nur in der Gesamt-Suite kippen.

    Nach JEDEM Test entfernen wir daher alle Instanz-Attribute des Singletons, die
    eine *aufrufbare* Klassenmethode ueberdecken. Echte Zustands-Attribute
    (programmer, _patch_cache, selected_fids, …) sind keine Klassenmethoden und
    bleiben unangetastet.
    """
    yield
    try:
        from src.core import app_state as _A
    except Exception:
        return
    st = getattr(_A, "_state", None)   # nicht get_state() -> Singleton nicht erzeugen
    if st is None:
        return
    cls = type(st)
    for name in list(vars(st)):
        if callable(getattr(cls, name, None)):
            try:
                delattr(st, name)
            except Exception:
                pass
