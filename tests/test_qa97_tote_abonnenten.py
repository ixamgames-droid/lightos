"""QA-97: tote Abonnenten duerfen den Event-Bus nicht stoeren.

Zwei Laser-Tests waren nur im Sammellauf rot. Ursache war ein Hauptfenster aus
einem frueheren Test, das seine Abos im globalen ``StateSync`` behielt:

* lebte es noch, verbrauchte es den Sperrzonen-Wechselhinweis
  (``_sperrzonen_wechsel_melden``) — ein spaeterer Test sah ihn nie;
* war es schon zerstoert, warf sein NOT-AUS-Abonnent ``RuntimeError("Signal
  source has been deleted")``, und die Fehlermeldung in ``emit()`` warf beim
  ``repr`` der toten gebundenen Methode gleich noch einmal — diesmal AUS dem
  ``except``-Zweig heraus. Alle nachfolgenden Abonnenten gingen leer aus.

Geprueft wird hier beides am Produktcode: ``emit()`` bleibt bei einem Abonnenten
mit kaputtem ``repr`` zustellfaehig, und das echte ``MainWindow`` meldet beim
Abbau alle Bus- und State-Abos ab.
"""
import os
import unittest
import weakref

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from _qt_lifecycle import flush_deferred_deletes                    # noqa: E402
from src.core.sync import StateSync, SyncEvent                      # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class _ReprWirft:
    """Wie eine gebundene Methode eines zerstoerten Qt-Objekts: Aufruf und
    ``repr`` werfen ``RuntimeError``, einen ``__name__`` gibt es nicht."""

    def __init__(self, text):
        self.text = text
        self.aufrufe = 0

    def __call__(self, *_):
        self.aufrufe += 1
        raise RuntimeError(self.text)

    def __repr__(self):
        raise RuntimeError("Internal C++ object (MainWindow) already deleted.")


class EmitBleibtZustellfaehigTest(unittest.TestCase):
    def test_kaputtes_repr_nimmt_den_folgenden_nichts_weg(self):
        sync = StateSync()
        tot = _ReprWirft("etwas anderes ging schief")
        danach = []
        sync.subscribe(SyncEvent.LASER_ESTOP, tot)
        sync.subscribe(SyncEvent.LASER_ESTOP, lambda *a: danach.append(a))
        sync.emit(SyncEvent.LASER_ESTOP, None)          # darf nicht werfen
        self.assertEqual(tot.aufrufe, 1)
        self.assertEqual(len(danach), 1, "Folge-Abonnent ging leer aus")

    def test_geloeschte_signalquelle_gilt_als_toter_abonnent(self):
        sync = StateSync()
        tot = _ReprWirft("Signal source has been deleted")
        sync.subscribe(SyncEvent.LASER_ESTOP, tot)
        sync.emit(SyncEvent.LASER_ESTOP, None)
        sync.emit(SyncEvent.LASER_ESTOP, None)
        self.assertEqual(tot.aufrufe, 1, "toter Abonnent nicht abgemeldet")


def _gehoert_zu(cb, fenster, _tiefe=0) -> bool:
    """Haengt dieser Abonnent am Fenster? Gebundene Methode, Lambda mit
    ``self`` in der Closure oder ``subscribe_widget``-Huelle (schwache Ref als
    Default-Argument)."""
    def _ist(obj):
        if obj is fenster:
            return True
        if isinstance(obj, weakref.ref):
            return obj() is fenster
        return False

    if _ist(getattr(cb, "__self__", None)):
        return True
    for wert in (getattr(cb, "__defaults__", None) or ()):
        if _ist(wert):
            return True
        if callable(wert) and _ist(getattr(wert, "__self__", None)):
            return True
    for zelle in (getattr(cb, "__closure__", None) or ()):
        try:
            inhalt = zelle.cell_contents
        except ValueError:
            continue
        if _ist(inhalt):
            return True
        # Huellen schachteln hoechstens einmal (guarded -> callback); die
        # Huelle faengt sich selbst fuer ``unsubscribe`` — daher begrenzt.
        if (_tiefe < 2 and inhalt is not cb and callable(inhalt)
                and _gehoert_zu(inhalt, fenster, _tiefe + 1)):
            return True
    return False


class HauptfensterMeldetSichAbTest(unittest.TestCase):
    """Das Hauptfenster selbst meldet beim Abbau alle eigenen Abos ab.

    Bewusst nur die des Fensters: eingebettete Views mit eigenen ``subscribe``-
    Lambdas raeumt die Selbstheilung in ``emit()`` ab ("already deleted")."""

    def test_abgebautes_fenster_hinterlaesst_keine_abos(self):
        import src.ui.main_window as MW
        from src.core.app_state import get_state
        from src.core.sync import get_sync

        _app()
        st = get_state()
        sync = get_sync()

        def eigene():
            bus = [cb for cbs in sync._subscribers.values() for cb in cbs
                   if _gehoert_zu(cb, w)]
            state = [cb for cb in st._callbacks if _gehoert_zu(cb, w)]
            return bus, state

        w = MW.MainWindow()
        bus, state = eigene()
        # 10 Abos im Konstruktor + 8 Autosave-Abos; das State-Abo genau einmal.
        self.assertGreaterEqual(len(bus), 10)
        self.assertEqual(len(state), 1)
        _app().processEvents()          # Anlauf-Zeitgeber (singleShot 0) abarbeiten

        w.deleteLater()
        flush_deferred_deletes()
        _app().processEvents()
        flush_deferred_deletes()

        bus, state = eigene()
        self.assertEqual(bus, [], "Bus-Abos des Fensters ueberleben es")
        self.assertEqual(state, [], "State-Abo des Fensters ueberlebt es")

        # Und das, worum es ging: der Hinweis bleibt fuer den naechsten Leser.
        st.sperrzonen_wechsel_hinweis = True
        try:
            sync.emit(SyncEvent.SHOW_LOADED, {})
            self.assertTrue(st.sperrzonen_wechsel_hinweis,
                            "totes Fenster hat den Wechselhinweis verbraucht")
        finally:
            st.sperrzonen_wechsel_hinweis = False


class StateRuftKeineTotenAnsichtenTest(unittest.TestCase):
    """``AppState`` ruft keine gebundene Methode eines zerstoerten Qt-Objekts
    mehr auf — deren Python-Teil liefe sonst bis zur ersten Qt-Beruehrung."""

    def test_toter_abonnent_wird_abgemeldet_statt_gerufen(self):
        from PySide6.QtCore import QObject
        from shiboken6 import delete as qt_delete
        from src.core.app_state import get_state

        _app()
        st = get_state()
        gerufen = []

        class _Ansicht(QObject):
            def bei_ereignis(self, ev, _daten):
                gerufen.append(ev)          # reiner Python-Teil: liefe weiter

        lebend, tot = _Ansicht(), _Ansicht()
        st.subscribe(lebend.bei_ereignis)
        st.subscribe(tot.bei_ereignis)
        self.addCleanup(st.unsubscribe, lebend.bei_ereignis)
        self.addCleanup(st.unsubscribe, tot.bei_ereignis)
        qt_delete(tot)

        st._emit_impl("qa97_probe", None)
        self.assertEqual(gerufen, ["qa97_probe"], "nur die lebende Ansicht")
        self.assertNotIn(tot.bei_ereignis, st._callbacks)
        self.assertIn(lebend.bei_ereignis, st._callbacks)


class LiveViewMeldetSichAbTest(unittest.TestCase):
    """Die 2D-Buehne (``StageCanvas``) haengt nach dem Abbau nicht mehr an
    ``SHOW_LOADED`` — vorher lud sie beim naechsten Show-Laden weiter
    Positionen nach und gab sie an den State weiter."""

    def test_abgebaute_buehne_hat_keine_bus_abos(self):
        import src.ui.views.live_view as LV
        from src.core.sync import get_sync

        _app()
        sync = get_sync()
        c = LV.StageCanvas()
        eigene = lambda: [cb for ev in (SyncEvent.SHOW_LOADED, SyncEvent.REFRESH_ALL)  # noqa: E731
                          for cb in sync._subscribers[ev] if _gehoert_zu(cb, c)]
        self.assertEqual(len(eigene()), 2)
        _app().processEvents()
        c.deleteLater()
        flush_deferred_deletes()
        _app().processEvents()
        flush_deferred_deletes()
        self.assertEqual(eigene(), [])


if __name__ == "__main__":
    unittest.main()
