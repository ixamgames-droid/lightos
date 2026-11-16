"""STAB-41: Dialoge mit dem Hauptfenster als Eltern nach ``exec()`` freigeben.

Befund (Klick-Test 16.11.2026): beim 5./6. nacheinander modal geoeffneten und
per ``reject()`` geschlossenen Dialog stuerzte die App nativ ab (SIGSEGV).
``Dialog(self).exec()`` ohne Freigabe laesst einen Dialog, an dem noch ein
Verweis haengt (Signalverbindung mit ``self``), bis Sitzungsende als Kind des
Hauptfensters liegen.

Die Tests hier:

1. Nachstellung in einem EIGENEN Prozess (``tests/_stab41_dialog_kind.py``):
   echtes Hauptfenster in der Sandbox, alle betroffenen Dialoge ueber die
   echten ``MainWindow._open_…``-Methoden mehrfach nacheinander, Schliessen
   per Timer. Der Prozess darf nicht abstuerzen, die Zahl der QDialog-Kinder
   des Hauptfensters darf nicht wachsen, kein Slot darf werfen (Nebenbefund
   ``_refresh_undo_labels``).
2. ``src/ui/dialog_hilfe.py`` selbst (Ergebnis, Freigabe, Ausnahmen).
3. Stichproben umgestellter Stellen mit echtem Dialog: bestaetigen ->
   Wirkung wie vorher, danach kein Dialog mehr am Elternfenster.
4. Waechter (AST): neue ``….exec()``-Stellen in ``src/ui/main_window.py`` und
   ``src/ui/views`` ohne ``dialog_hilfe``.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget  # noqa: E402

from src.ui import dialog_hilfe  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIND = os.path.join(REPO, "tests", "_stab41_dialog_kind.py")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _loeschungen_zustellen():
    """Wie die Rueckkehr in die Hauptschleife: deleteLater ausfuehren."""
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


def _wenn_modal(tu, versuche=200):
    """``tu(dialog)`` ausfuehren, sobald ein modaler Dialog offen ist (wartet
    auf die Bedingung statt auf eine feste Zeit)."""
    zaehler = {"n": 0}

    def pruefen():
        w = QApplication.activeModalWidget()
        if w is not None and w.isVisible():
            tu(w)
            return
        zaehler["n"] += 1
        if zaehler["n"] < versuche:
            QTimer.singleShot(10, pruefen)
    QTimer.singleShot(0, pruefen)


# ── 1. Nachstellung im eigenen Prozess ───────────────────────────────────────

def _kind(tmp_path, runden: int, oeffner: str | None = None):
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"
    for k in ("LIGHTOS_ECHTE_DATEN", "LIGHTOS_ECHTE_AUSGABE", "LIGHTOS_ECHTE_APP"):
        env.pop(k, None)
    befehl = [sys.executable, KIND, str(tmp_path / "sandbox"), str(runden)]
    if oeffner:
        befehl.append(oeffner)
    r = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=420, cwd=REPO, env=env)
    return r


@pytest.mark.timeout(450)   # eigener Prozess baut das ganze Hauptfenster
def test_viele_dialoge_nacheinander_ohne_absturz_und_ohne_reste(tmp_path):
    """Alle Dialoge des Klick-Tests dreimal hintereinander ueber die echten
    App-Methoden: kein nativer Absturz, kein liegengebliebener Dialog, keine
    Ausnahme in einem Slot (auch nicht in ``_refresh_undo_labels``)."""
    r = _kind(tmp_path, runden=3)
    zeilen = r.stdout.splitlines()
    ergebnis = [z for z in zeilen if z.startswith("ERGEBNIS ")]
    letzte = [z for z in zeilen if z.startswith("OEFFNE ")][-1:]
    assert r.returncode == 0 and ergebnis, (
        f"Kindprozess endete mit {r.returncode} (negativ = Signal, -11 = SIGSEGV), "
        f"zuletzt {letzte}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    _ok, dialoge, zuwachs, ausnahmen = ergebnis[0].split()[1:]
    assert int(dialoge) == 33
    reste = [z for z in zeilen if z.startswith("NACH ") and not z.endswith(" 0")]
    assert int(zuwachs) == 0, "Dialoge bleiben am Hauptfenster liegen:\n" + "\n".join(reste)
    assert int(ausnahmen) == 0, "\n".join(z for z in zeilen if z.startswith("AUSNAHME"))


# ── 2. Die Hilfe selbst ──────────────────────────────────────────────────────

def test_ausfuehren_gibt_ergebnis_und_gibt_frei(app):
    eltern = QWidget()
    dlg = QDialog(eltern)
    _wenn_modal(lambda w: w.accept())
    assert dialog_hilfe.ausfuehren(dlg) == QDialog.DialogCode.Accepted
    # bis zur Rueckkehr in die Schleife lebt er noch (Werte lesbar) …
    assert eltern.findChildren(QDialog) == [dlg]
    _loeschungen_zustellen()
    assert eltern.findChildren(QDialog) == []

    dlg2 = QDialog(eltern)
    _wenn_modal(lambda w: w.reject())
    assert dialog_hilfe.ausfuehren(dlg2) == QDialog.DialogCode.Rejected
    _loeschungen_zustellen()
    assert eltern.findChildren(QDialog) == []
    eltern.deleteLater()
    _loeschungen_zustellen()


def test_offen_gibt_frei_auch_bei_return_und_ausnahme(app):
    eltern = QWidget()

    def mit_return():
        dlg = QDialog(eltern)
        dlg.setObjectName("wert")
        _wenn_modal(lambda w: w.accept())
        with dialog_hilfe.offen(dlg):
            if dlg.exec() == QDialog.DialogCode.Accepted:
                return dlg.objectName()      # im Block noch lesbar
        return None

    assert mit_return() == "wert"
    _loeschungen_zustellen()
    assert eltern.findChildren(QDialog) == []

    dlg = QDialog(eltern)
    with pytest.raises(ValueError):
        with dialog_hilfe.offen(dlg):
            raise ValueError("x")
    _loeschungen_zustellen()
    assert eltern.findChildren(QDialog) == []
    eltern.deleteLater()
    _loeschungen_zustellen()


def test_freigeben_vertraegt_none_ersatz_und_geloeschtes(app):
    import shiboken6
    from types import SimpleNamespace
    dialog_hilfe.freigeben(None)
    dialog_hilfe.freigeben(SimpleNamespace())          # Ersatzobjekt aus Tests
    dlg = QDialog()
    shiboken6.delete(dlg)
    dialog_hilfe.freigeben(dlg)                        # schon weg: still


# ── 3. Stichproben umgestellter Stellen ──────────────────────────────────────

@pytest.mark.parametrize("knopf, erwartet", [("loeschen", True), ("abbrechen", False)])
def test_vk_alle_loeschen_rueckfrage_ergebnis_bleibt(app, knopf, erwartet):
    from src.ui.views import virtual_console_view as vcv
    eltern = QWidget()

    def klick(box):
        ziel = box._ui137_loeschen if knopf == "loeschen" else box.escapeButton()
        ziel.click()
    _wenn_modal(klick)
    assert vcv._frage_alle_loeschen(eltern, 3) is erwartet
    _loeschungen_zustellen()
    assert eltern.findChildren(QMessageBox) == []
    eltern.deleteLater()
    _loeschungen_zustellen()


def test_hauptfenster_rueckfrage_liefert_gewaehlten_knopf(app):
    from src.ui import main_window as mw
    eltern = QWidget()
    _wenn_modal(lambda box: box.button(QMessageBox.StandardButton.Yes).click())
    antwort = mw.QMessageBox.question(eltern, "Frage", "Wirklich?")
    assert antwort == QMessageBox.StandardButton.Yes
    _loeschungen_zustellen()
    assert eltern.findChildren(QMessageBox) == []
    eltern.deleteLater()
    _loeschungen_zustellen()


def test_kurvenbibliothek_neu_uebernimmt_kurve(app, monkeypatch):
    """Lesen nach exec(): die Kurve aus dem bestaetigten Dialog kommt an —
    auch wenn danach noch eine (hier ersetzte) Namensabfrage folgt."""
    from src.ui.views import curve_library_view as clv
    view = clv.CurveLibraryView()
    angekommen = []
    monkeypatch.setattr(view, "_do_add", lambda c: angekommen.append(c) or True)
    monkeypatch.setattr(clv.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Meine Kurve", True)))
    _wenn_modal(lambda dlg: dlg._accept())
    view._on_new()
    assert len(angekommen) == 1 and angekommen[0].name == "Meine Kurve"
    _loeschungen_zustellen()
    assert view.findChildren(QDialog) == []
    view.deleteLater()
    _loeschungen_zustellen()


def test_kurvenbibliothek_abbrechen_uebernimmt_nichts(app, monkeypatch):
    from src.ui.views import curve_library_view as clv
    view = clv.CurveLibraryView()
    angekommen = []
    monkeypatch.setattr(view, "_do_add", lambda c: angekommen.append(c) or True)
    _wenn_modal(lambda dlg: dlg.reject())
    view._on_new()
    assert angekommen == []
    _loeschungen_zustellen()
    assert view.findChildren(QDialog) == []
    view.deleteLater()
    _loeschungen_zustellen()


def test_undo_beschriftung_nach_abgebauter_aktion_wirft_nicht(app):
    """Nebenbefund: ``_refresh_undo_labels`` auf eine schon geloeschte
    QAction (Klick-Test: ``RuntimeError: Internal C++ object (QAction)
    already deleted``) — jetzt still, mit lebenden Aktionen wie bisher."""
    import shiboken6
    from types import SimpleNamespace
    from PySide6.QtGui import QAction
    from src.ui.main_window import MainWindow
    undo, redo = QAction("Rückgängig"), QAction("Wiederholen")
    fenster = SimpleNamespace(
        _act_undo=undo, _act_redo=redo,
        _naechster_verlauf=lambda wiederholen: (("app", "Farbe") if not wiederholen
                                                 else (None, None)))
    MainWindow._refresh_undo_labels(fenster)
    assert undo.text() == "Rückgängig: Farbe" and undo.isEnabled()
    assert redo.text() == "Wiederholen" and not redo.isEnabled()
    shiboken6.delete(undo)
    MainWindow._refresh_undo_labels(fenster)          # wirft nicht mehr


# ── 4. Waechter ──────────────────────────────────────────────────────────────

# (Datei relativ zum Repo, Funktionsname) -> Begruendung. Nur fuer Stellen, an
# denen ``exec()`` ohne Freigabe Absicht ist. Derzeit keine.
AUSNAHMEN: dict[tuple[str, str], str] = {}


def _dateien():
    yield "src/ui/main_window.py"
    views = os.path.join(REPO, "src", "ui", "views")
    for name in sorted(os.listdir(views)):
        if name.endswith(".py"):
            yield f"src/ui/views/{name}"


def stellen_ohne_hilfe(quelle: str) -> list[tuple[int, str]]:
    """``(zeile, funktion)`` jeder argumentlosen ``….exec()``/``exec_()``-Stelle,
    die nicht in ``with dialog_hilfe.offen(<dasselbe Objekt>)`` steht."""
    baum = ast.parse(quelle.lstrip("﻿"))
    eltern = {k: p for p in ast.walk(baum) for k in ast.iter_child_nodes(p)}
    funde = []
    for n in ast.walk(baum):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("exec", "exec_") and not n.args and not n.keywords):
            continue
        ziel = ast.unparse(n.func.value)
        p, gedeckt, funktion = eltern.get(n), False, "<modul>"
        while p is not None:
            if isinstance(p, ast.With) and not gedeckt:
                for it in p.items:
                    c = it.context_expr
                    if (isinstance(c, ast.Call) and ast.unparse(c.func).endswith("dialog_hilfe.offen")
                            and c.args and ast.unparse(c.args[0]) == ziel):
                        gedeckt = True
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)) and funktion == "<modul>":
                funktion = p.name
            p = eltern.get(p)
        if not gedeckt:
            funde.append((n.lineno, funktion))
    return funde


def test_waechter_erkennt_die_muster():
    beispiel = (
        "def a(self):\n    Foo(self).exec()\n"
        "def b(self):\n    dlg = Foo(self)\n    if dlg.exec():\n        pass\n"
        "def c(self):\n    dialog_hilfe.ausfuehren(Foo(self))\n"
        "def d(self):\n    dlg = Foo(self)\n    with dialog_hilfe.offen(dlg):\n"
        "        dlg.exec()\n"
        "def e(self):\n    dlg = Foo(self)\n    with dialog_hilfe.offen(anderer):\n"
        "        dlg.exec()\n"
        "def f(self):\n    menue.exec(pos)\n")
    assert [f for _z, f in stellen_ohne_hilfe(beispiel)] == ["a", "b", "e"]


def test_keine_exec_stelle_ohne_dialog_hilfe():
    funde = []
    gesehen = set()
    for rel in _dateien():
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            for zeile, funktion in stellen_ohne_hilfe(f.read()):
                gesehen.add((rel, funktion))
                if (rel, funktion) not in AUSNAHMEN:
                    funde.append(f"{rel}:{zeile} ({funktion})")
    assert not funde, (
        "Dialog nach exec() nicht freigegeben (STAB-41) — "
        "dialog_hilfe.ausfuehren(dlg) bzw. `with dialog_hilfe.offen(dlg):` "
        "benutzen:\n" + "\n".join(funde))
    veraltet = set(AUSNAHMEN) - gesehen
    assert not veraltet, f"Ausnahmeliste veraltet: {sorted(veraltet)}"
