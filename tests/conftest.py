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
# Tests auf SEPARATE, PRO-PROZESS-EINDEUTIGE Datenbanken umlenken. So fasst kein
# Test je die echten DBs der laufenden App an UND zwei gleichzeitige pytest-Laeufe
# (oder ein abgebrochener Vorlauf) teilen sich NICHTS mehr.
#
# WARUM eindeutig statt fest: Frueher lag hier ein FESTER Pfad
# (lightos_test_show.db), der ueber Laeufe hinweg bestehen blieb und von allen
# parallelen Prozessen geteilt wurde. Lief der Suite-Lauf gleichzeitig ein
# zweites Mal (oder gegen eine offene App), leerte/fuellte ein Prozess den
# SQLite-Patch, waehrend ein anderer mitten in load_show() steckte -> dieser sah
# eine FALSCHE Fixture-Zahl (z. B. test_musik_show_2026::test_patch_8_par_2_mh:
# 7/9/12 != 10) oder leere Fixture-Lookups (StopIteration). Die PID im Dateinamen
# entkoppelt die Laeufe vollstaendig. MUSS vor dem ersten app_state-Import stehen
# (app_state.SHOW_DB_PATH liest LIGHTOS_SHOW_DB beim Import EINMAL).
_TEST_TMP = tempfile.gettempdir()
_TEST_PID = os.getpid()
os.environ.setdefault(
    "LIGHTOS_SHOW_DB",
    os.path.join(_TEST_TMP, f"lightos_test_show_{_TEST_PID}.db"))
# Hinweis: Die Fixture-DEFINITIONS-DB (fixture_db.DB_PATH) wird BEWUSST NICHT
# umgelenkt. Die committeten shows/*.lshow referenzieren feste
# fixture_profile_id-Werte aus der real geseedeten fixtures.db; eine frisch
# geseedete Eigen-DB vergibt andere Auto-IDs -> Kanal-Lookups (Dimmer/Farbe)
# liefen ins Leere (test_color_fx_show_render/test_strict_dimmer_render). Sie ist
# zudem reine LESE-/idempotente Seed-Last und damit nicht die Flaky-Quelle.


def _purge_test_dbs():
    """Die prozess-eigene Show-Test-DB (inkl. SQLite -wal/-shm-Seitendateien)
    loeschen. Garantiert einen WIRKLICH leeren Start, falls ein frueherer Lauf
    mit derselben (recycelten) PID Altzeilen hinterlassen hat."""
    _base = os.environ.get("LIGHTOS_SHOW_DB")
    if not _base:
        return
    for _suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_base + _suffix)
        except OSError:
            pass


# Beim conftest-Import (Sammelphase, VOR dem ersten get_state()/engine())
# etwaige Altdateien derselben PID wegraeumen -> jeder Lauf startet garantiert leer.
_purge_test_dbs()
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
    # Prozess-eigene Show-Test-DB am Suite-Ende abraeumen. Vorher die SQLAlchemy-
    # Engine schliessen (dispose), damit die Datei auf Windows ueberhaupt loeschbar
    # ist (sonst „WinError 32: in use"). Schlaegt das fehl, bleibt nur eine
    # (harmlose) Temp-Leiche zurueck — die Isolation (PID im Namen) haengt nicht
    # davon ab.
    try:
        from src.core import app_state as _A2
        st = getattr(_A2, "_state", None)
        eng = getattr(st, "_show_engine", None) if st is not None else None
        if eng is not None:
            eng.dispose()
    except Exception:
        pass
    _purge_test_dbs()


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
