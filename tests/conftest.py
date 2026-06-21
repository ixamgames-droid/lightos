"""Gemeinsame Test-Fixtures.

Stabilisiert die Gesamt-Suite: VCCanvas abonniert beim Erzeugen den globalen
MIDI-Manager und meldet sich erst bei seiner Zerstoerung (destroyed/closeEvent)
wieder ab. Viele Tests erzeugen Canvases, ohne sie zu schliessen — die toten
Callbacks haeuften sich ueber die Suite an und konnten in einem spaeteren Test zu
einem harten Crash fuehren. Diese Autouse-Fixture meldet nach JEDEM Test alle noch
lebenden Canvases ab.
"""
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Tests auf eine SEPARATE Show-DB umlenken (app_state.SHOW_DB_PATH liest
# LIGHTOS_SHOW_DB). So fasst kein Test je die echte data/current_show.db der
# laufenden App an — man kann parallel eine Show bauen, ohne Konflikt/„database
# locked"/Datenverlust. MUSS vor dem ersten app_state-Import gesetzt sein.
os.environ.setdefault(
    "LIGHTOS_SHOW_DB",
    os.path.join(tempfile.gettempdir(), "lightos_test_show.db"))
# Den 44-Hz-DMX-Output-Thread in Tests gar nicht erst autostarten (siehe
# app_state.get_state): er rendert in _render_frame und emittiert Sync-Events,
# die cross-thread in Qt marshallt werden -> race mit dem pytest-Teardown
# (processEvents/GC abgemeldeter Widgets) = sporadische native Access Violation.
# MUSS vor dem ersten get_state() gesetzt sein -> hier am conftest-Kopf.
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
# AUTO-Start der Audio-BPM-Erkennung (AUTO ist standardmaessig an) in Tests
# unterdruecken: kein Test soll je den WASAPI-Loopback-Capture hochfahren.
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")

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
    # NS-TEARDOWN: auch die MIDI-Threads sauber joinen, falls ein Test die
    # Singletons erzeugt hat. Über die Modul-Globals pruefen (NICHT get_*),
    # damit hier kein Singleton lazy erzeugt wird. Reihenfolge: erst der
    # Feedback-Thread (ruft intern den Manager), dann der Dispatch-Thread.
    try:
        from src.core.midi import midi_mapper as _MM
        mapper = getattr(_MM, "_mapper_instance", None)
        if mapper is not None:
            mapper.close()
    except Exception:
        pass
    try:
        from src.core.midi import midi_manager as _MGR
        mgr = getattr(_MGR, "_manager", None)
        if mgr is not None:
            mgr.close_all()
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
def _clear_qt_focus():
    """Schuetzt die Gesamt-Suite vor einem undichten globalen Tastatur-Fokus.

    Manche Tests erzeugen Widgets/Dialoge und zeigen sie (z. B.
    EfxView._open_popout -> dialog.show()), ohne sie wieder zu zerstoeren. Beim
    Anzeigen bekommt das erste fokussierbare Kind (oft eine QSpinBox/
    QDoubleSpinBox) den Tastatur-Fokus. Da das Widget am Leben bleibt, liefert
    ``QApplication.focusWidget()`` ueber den Rest der Suite weiterhin dieses
    Eingabefeld.

    Das brachte test_keyboard_mapping nur im Gesamt-Lauf zum Kippen:
    ``KeyboardHotkeyFilter.eventFilter`` unterdrueckt Hotkeys, solange der Fokus
    in einem Texteingabefeld liegt (``_is_text_input(app.focusWidget())``) —
    ein QAbstractSpinBox zaehlt dazu. Der geleakte Fokus liess jeden KeyPress
    fruehzeitig mit ``False`` zurueckkehren.

    Nach JEDEM Test nehmen wir einem ggf. noch fokussierten Widget den Fokus,
    sodass der naechste Test mit ``focusWidget() is None`` startet. Bewusst OHNE
    app-weites sendPostedEvents/processEvents (clearFocus() nullt den globalen
    Fokus-Zeiger sofort).
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        fw = app.focusWidget()
        if fw is not None:
            fw.clearFocus()
    except Exception:
        pass
    # Auch geleakte MODALE Dialoge schliessen: ein Test, der einen Dialog modal
    # zeigt (setModal/open) ohne ihn zu schliessen, laesst ``activeModalWidget()``
    # ueber den Rest der Suite gesetzt. Das brachte test_keyboard_mapping nur im
    # Gesamt-Lauf zum Kippen — ``KeyboardHotkeyFilter.eventFilter`` pausiert
    # Hotkeys, solange ein modaler Dialog offen ist. close() in einer kleinen
    # Schleife (das Schliessen eines Modals kann das naechste sichtbar machen);
    # bewusst OHNE app-weites processEvents.
    try:
        for _ in range(20):
            mw = app.activeModalWidget()
            if mw is None:
                break
            mw.close()
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


@pytest.fixture(autouse=True)
def _reset_bpm_manager():
    """Stoppt nach JEDEM Test einen ggf. laufenden globalen BPM-Beat-Timer und
    setzt den Leader zurueck.

    Ein Test, der via tap/nudge/set_bpm eine BPM>0 am Singleton setzt (z. B.
    test_vc_bpm ueber den Nudge-Button), laesst sonst den 'BPM-Beat'-Daemon
    weiterlaufen; dessen _emit_beat() greift quer durch die restliche Suite auf
    app_state/function_manager zu -> Mit-Ursache der sporadischen nativen
    Teardown-Crashes. Ueber das Modul-Global pruefen (NICHT get_bpm_manager()),
    damit hier kein Singleton lazy erzeugt wird."""
    yield
    try:
        from src.core.engine import bpm_manager as _BM
        mgr = getattr(_BM, "_mgr", None)
        if mgr is not None:
            mgr._audio_active = False
            mgr._locked = False
            mgr.reset()                 # stoppt den Timer-Thread + nullt den Zustand
            mgr._mode = _BM.BpmMode.AUTO
    except Exception:
        pass
