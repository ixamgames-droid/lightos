"""QA-112: Kind-Probe fuer test_qa112_interpreter_ende.py — nie im Gate-Lauf
(Name ohne ``test_``; nur ausdruecklich als Datei an pytest gegeben).

Nachgestellt wird, was in ``test_group_edit_dialog`` & Co. beim normalen
Interpreter-Ende uebrig blieb: Dialoge, deren Klasse in Python abgeleitet ist
und die sich ueber ein Lambda am eigenen Knopf selbst festhalten
(``clicked.connect(lambda: self._...)``). Die Verbindung haelt Qt in C++ — fuer
Pythons Speicherbereinigung unsichtbar, ``gc.collect()`` gibt sie nicht frei.

Am Interpreter-Ende zaehlt ein ``atexit``-Haken die noch lebenden
Top-Level-Fenster und schreibt die Zahl nach ``QA112_ZAEHLUNG``. Er ist nach
PySides eigenem Aufraeumen angemeldet und laeuft deshalb davor (LIFO), aber
nach ``conftest.pytest_unconfigure``.
"""
import atexit
import gc
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QPushButton  # noqa: E402


class _Dialog(QDialog):
    def __init__(self):
        super().__init__()
        knopf = QPushButton("OK", self)
        knopf.clicked.connect(lambda: self._geklickt())

    def _geklickt(self):
        pass


def _zaehlen():
    ziel = os.environ.get("QA112_ZAEHLUNG")
    if not ziel:
        return
    app = QApplication.instance()
    n = len(QApplication.topLevelWidgets()) if app is not None else -1
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump({"fenster": n}, f)


atexit.register(_zaehlen)


def test_dialoge_haengen_ueber_ihr_lambda_fest():
    QApplication.instance() or QApplication([])
    for _ in range(int(os.environ.get("QA112_DIALOGE", "8"))):
        _Dialog()
    gc.collect()
    # Vorbedingung: das Leck gibt es wirklich (sonst prueft der Test nichts)
    assert len(QApplication.topLevelWidgets()) >= 8
    assert os.environ.get("QA112_ROT") != "1", "gewollt rot (Gegenprobe)"
