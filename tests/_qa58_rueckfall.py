"""Stellt den realistischen QA-58-Rueckfall her: die Bibliothek OHNE Override.

Dieses Modul ist KEIN Test. Es wird von
``tests/test_qa58_bibliothek_schema_unberuehrt.py`` als pytest-Plugin in einen
KINDPROZESS geladen (``-p _qa58_rueckfall``) — nie in den Gate-Lauf selbst.

**Was nachgestellt wird.** Die eine Zeile, um die es in QA-58 geht::

    src/core/database/fixture_db.py
        DB_PATH = os.environ.get("LIGHTOS_FIXTURE_DB") or os.path.join(
            app_data_dir(), "fixtures.db")

Faellt der Override-Teil weg — oder setzt ``tests/conftest.py`` ihn nicht mehr —,
steht in ``DB_PATH`` wieder ``app_data_dir()/fixtures.db``, also die echte
Bibliothek des Nutzers. Genau dieses Ergebnis wird hier ueber die Umgebung
erzeugt.

**Warum ueber die Umgebung und nicht per Zuweisung an ``fixture_db.DB_PATH``.**
Eine nachtraegliche Zuweisung waere nur die halbe Regression: ``get_engine(path:
str = DB_PATH)`` bindet seinen Default zur ``def``-Zeit, also beim Import. Ein
spaeter umgesetztes ``DB_PATH`` erreicht ihn nicht mehr — der Rueckfall liefe
zur Haelfte ins Leere, und ein Waechter koennte gruen bleiben, obwohl er die
echte Regression nicht ueberlebt haette. So dagegen laeuft der Rueckfall durch
die ECHTE Zeile: das Modul wird erst NACH diesem Hook importiert und rechnet
sich seinen Pfad selbst aus.

**Der Zeitpunkt ist nachgemessen, nicht geraten.** Bei ``pytest_configure`` ist
``tests/conftest.py`` bereits importiert (hat seine Umlenkung also gesetzt, die
hier weggenommen wird), ``src.core.database.fixture_db`` dagegen noch nicht.
Die Zusicherung unten haelt beides fest — ohne sie koennte der Rueckfall ins
Leere laufen und der Test waere gruen, ohne je etwas gefahren zu haben.
"""
import os
import sys


def pytest_configure(config):
    assert "src.core.database.fixture_db" not in sys.modules, (
        "fixture_db war beim Herstellen des Rueckfalls schon importiert — "
        "DB_PATH und der Default von get_engine stehen dann bereits auf der "
        "Kopie, der Rueckfall waere nicht nachgestellt")
    assert "LIGHTOS_FIXTURE_DB" in os.environ, (
        "conftest hat die Umlenkung gar nicht gesetzt — dann nimmt dieses "
        "Plugin nichts weg und der Test belegt nicht, was er behauptet")
    os.environ.pop("LIGHTOS_FIXTURE_DB", None)
