"""Stellt den ZWEITEN QA-58-Rueckfall her: die globale Engine auf der Bibliothek.

Dieses Modul ist KEIN Test. Es wird von
``tests/test_qa58_bibliothek_schema_unberuehrt.py`` als pytest-Plugin in einen
KINDPROZESS geladen (``-p _qa58_engine_rueckfall``) — nie in den Gate-Lauf
selbst.

**Warum es diesen zweiten Rueckfall gibt.** ``DB_PATH`` ist nur der eine Weg zur
Bibliothek. ``fixture_db.get_engine(pfad)`` nimmt einen expliziten Pfad daran
vorbei, und ``fixture_db._engine`` ist ein gewoehnliches Modul-Global, das sich
umsetzen laesst. Beides ist im Bestand real vorhanden:

* ``tests/_fixture_quelle.frische_library`` baut genau so eine Engine und setzt
  ``FDB._engine`` darauf um (dort auf eine Wegwerf-Datei — richtig).
* ``tools/verify_stage_reload.py`` richtet sich ausdruecklich auf die echte
  Bibliothek aus und nennt das „nur lesend", geht dabei aber durch
  ``get_engine()`` und migriert damit.

Nachgestellt wird deshalb der Fall „jemand haengt die globale Engine an
``app_data_dir()/fixtures.db``", waehrend ``DB_PATH`` voellig in Ordnung ist —
der Fall, den die Pruefung bei der Kollektion per Konstruktion nicht sehen kann.

**Zeitpunkt — nachgemessen, weil der erste Versuch daneben lag.** In
``pytest_collection_modifyitems`` gesetzt, faengt es der Kollektions-Waechter in
``conftest.pytest_collection_finish`` ab (``modifyitems`` laeuft VOR
``collection_finish``), und dieses Modul belegte dann etwas anderes als es soll.
Gesetzt wird deshalb beim Aufbau des ERSTEN Tests: das ist der Fall „waehrend
des Laufs setzt jemand die globale Engine um", und rot werden muss dabei die
Fixture nach dem Test.
"""
import os

_GESETZT = False


def pytest_runtest_setup(item):
    global _GESETZT
    if _GESETZT:
        return
    _GESETZT = True
    from src.core.paths import app_data_dir
    from src.core.database import fixture_db

    echte = os.path.join(app_data_dir(), "fixtures.db")
    assert os.path.realpath(fixture_db.DB_PATH) != os.path.realpath(echte), (
        "DB_PATH zeigt schon auf die Bibliothek — dann belegt dieser Rueckfall "
        "nicht, was er soll (das waere der Fall des Kollektions-Waechters)")
    fixture_db._engine = fixture_db.get_engine(echte)
