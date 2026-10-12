"""LIZ-1: Abfrage der Testlizenz beim Start — Dialog (offscreen) und die
Verdrahtung in ``main.py``.

Eigenes Test-Schluesselpaar (Monkeypatch des oeffentlichen Schluessels); der
echte Signierschluessel und echte Lizenzdateien kommen hier nicht vor.
"""
from __future__ import annotations

import datetime as dt
import os
import re

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from src.core import ed25519, lizenz
from src.ui import lizenz_dialog
from src.ui.lizenz_dialog import LizenzDialog

GEHEIM = bytes(range(1, 33))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch, tmp_path):
    monkeypatch.setattr(lizenz, "OEFFENTLICHER_SCHLUESSEL",
                        ed25519.oeffentlicher_schluessel(GEHEIM))
    monkeypatch.delenv(lizenz.ENV_PFAD, raising=False)
    monkeypatch.setattr(lizenz, "app_data_dir",
                        lambda: str(tmp_path / "daten" / "LightOS"))


def _datei(tmp_path, name="x.lic", bis=dt.date(2099, 1, 1), inhalt=None) -> str:
    p = tmp_path / name
    p.write_text(inhalt if inhalt is not None else lizenz.als_text(
        lizenz.stelle_aus(GEHEIM, "Testerin", bis)), encoding="utf-8")
    return str(p)


OHNE = lizenz.Lizenzstatus(lizenz.FEHLT)


# ── Dialog ───────────────────────────────────────────────────────────────────

def test_dialog_titel_text_und_knoepfe(app):
    dlg = LizenzDialog(OHNE)
    try:
        assert dlg.windowTitle() == "LightOS — Testlizenz erforderlich"
        text = dlg.erklaerung.text()
        assert "Testphase" in text and "ixamgames-droid" in text
        assert "https://github.com/ixamgames-droid/lightos" in text
        assert "keine Lizenzdatei" in dlg.grund.text()
        knoepfe = [b.text() for b in dlg.findChildren(QPushButton)]
        assert knoepfe == ["Lizenzdatei auswählen…", "Lizenztext anzeigen", "Beenden"]
        assert lizenz.DATEINAME in dlg.ort.text()
    finally:
        dlg.deleteLater()


def test_kein_weiter_ohne_lizenz(app):
    """Es gibt keinen Knopf, der ohne gueltige Datei annimmt; Schliessen und
    Esc beenden."""
    dlg = LizenzDialog(OHNE)
    try:
        for b in dlg.findChildren(QPushButton):
            assert not re.search(r"weiter|später|ohne|überspringen|testen|ok",
                                 b.text(), re.I), b.text()
        dlg.btn_beenden.click()
        assert dlg.result() == QDialog.DialogCode.Rejected
        dlg2 = LizenzDialog(OHNE)
        dlg2.close()
        assert dlg2.result() == QDialog.DialogCode.Rejected
        dlg2.deleteLater()
    finally:
        dlg.deleteLater()


@pytest.mark.parametrize("status,erwartet", [
    (lizenz.Lizenzstatus(lizenz.ABGELAUFEN, name="T", kennung="K",
                         gueltig_bis=dt.date(2026, 3, 5)), "abgelaufen"),
    (lizenz.Lizenzstatus(lizenz.UNGUELTIG, grund="Signatur passt nicht"),
     "Signatur passt nicht"),
])
def test_dialog_zeigt_den_grund(app, status, erwartet):
    dlg = LizenzDialog(status)
    try:
        assert erwartet in dlg.grund.text()
        if status.zustand == lizenz.ABGELAUFEN:
            assert "05.03.2026" in dlg.grund.text()
    finally:
        dlg.deleteLater()


def test_gueltige_datei_wird_uebernommen_und_dialog_angenommen(app, tmp_path, monkeypatch):
    dlg = LizenzDialog(OHNE)
    try:
        monkeypatch.setattr(dlg, "_frage_datei", lambda: _datei(tmp_path))
        dlg.btn_auswaehlen.click()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.status.ist_gueltig and dlg.status.name == "Testerin"
        assert os.path.isfile(lizenz.standard_pfad())
        assert lizenz.pruefe(env={}).ist_gueltig
    finally:
        dlg.deleteLater()


@pytest.mark.parametrize("art", ["kaputt", "abgelaufen", "fremd"])
def test_ungueltige_datei_bleibt_im_dialog(app, tmp_path, monkeypatch, art):
    if art == "kaputt":
        pfad = _datei(tmp_path, inhalt="das ist keine Lizenz")
    elif art == "abgelaufen":
        pfad = _datei(tmp_path, bis=dt.date(2020, 1, 1))
    else:
        pfad = _datei(tmp_path, inhalt=lizenz.als_text(
            lizenz.stelle_aus(bytes([9]) * 32, "Fremd", None)))
    dlg = LizenzDialog(OHNE)
    try:
        monkeypatch.setattr(dlg, "_frage_datei", lambda: pfad)
        dlg.btn_auswaehlen.click()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert not dlg.status.ist_gueltig
        assert "nicht übernommen" in dlg.grund.text()
        assert not os.path.exists(lizenz.standard_pfad())
    finally:
        dlg.deleteLater()


def test_abgebrochene_dateiauswahl_aendert_nichts(app, monkeypatch):
    dlg = LizenzDialog(OHNE)
    try:
        vorher = dlg.grund.text()
        monkeypatch.setattr(dlg, "_frage_datei", lambda: "")
        dlg.btn_auswaehlen.click()
        assert dlg.grund.text() == vorher
        assert dlg.result() != QDialog.DialogCode.Accepted

        def kaputt():
            raise RuntimeError("Dateidialog kaputt")
        monkeypatch.setattr(dlg, "_frage_datei", kaputt)
        dlg.btn_auswaehlen.click()                 # darf nicht werfen
        assert dlg.result() != QDialog.DialogCode.Accepted
    finally:
        dlg.deleteLater()


def test_lizenztext_anzeigen(app, monkeypatch):
    gezeigt = []
    monkeypatch.setattr(lizenz_dialog.LizenztextDialog, "exec",
                        lambda self: gezeigt.append(self.text.toPlainText()) or 0)
    dlg = LizenzDialog(OHNE)
    try:
        dlg.btn_lizenztext.click()
        dlg.btn_lizenztext.click()                 # zweimal: derselbe Unterdialog
        assert len(gezeigt) == 2
        assert "Alle Rechte vorbehalten" in gezeigt[0]
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert len(dlg.findChildren(lizenz_dialog.LizenztextDialog)) == 1
    finally:
        dlg.deleteLater()


def test_frage_nach_lizenz_liefert_none_beim_beenden(app, monkeypatch):
    monkeypatch.setattr(LizenzDialog, "exec",
                        lambda self: (self.reject(), self.result())[1])
    assert lizenz_dialog.frage_nach_lizenz(OHNE) is None


def test_frage_nach_lizenz_liefert_status_nach_uebernahme(app, monkeypatch, tmp_path):
    pfad = _datei(tmp_path)

    def exec_(self):
        self.uebernimm(pfad)
        return self.result()
    monkeypatch.setattr(LizenzDialog, "exec", exec_)
    status = lizenz_dialog.frage_nach_lizenz(OHNE)
    assert status is not None and status.ist_gueltig


# ── Verdrahtung in main.py ───────────────────────────────────────────────────

@pytest.fixture
def main_modul():
    import main
    return main


def test_main_startet_mit_gueltiger_lizenz_ohne_dialog(app, main_modul, tmp_path,
                                                       monkeypatch, capsys):
    lizenz.installiere(_datei(tmp_path))
    monkeypatch.delenv(lizenz.ENV_TESTLAUF)        # wie beim Nutzer
    monkeypatch.setattr(lizenz_dialog, "frage_nach_lizenz",
                        lambda *a, **k: pytest.fail("Dialog trotz gueltiger Lizenz"))
    status = main_modul._lizenz_beim_start()
    assert status is not None and status.ist_gueltig
    aus = capsys.readouterr().out
    assert "ixamgames-droid" in aus and "Lizenz: gueltig" in aus
    assert "Testerin" not in aus                   # Name nie im Log


def test_main_fragt_ohne_lizenz_und_beendet_bei_absage(app, main_modul, monkeypatch,
                                                       capsys):
    monkeypatch.delenv(lizenz.ENV_TESTLAUF)
    gefragt = []
    monkeypatch.setattr(lizenz_dialog, "frage_nach_lizenz",
                        lambda status, *a, **k: gefragt.append(status.zustand))
    assert main_modul._lizenz_beim_start() is None
    assert gefragt == [lizenz.FEHLT]
    assert "Lizenz: fehlt" in capsys.readouterr().out


def test_main_uebernimmt_den_status_aus_dem_dialog(app, main_modul, monkeypatch):
    monkeypatch.delenv(lizenz.ENV_TESTLAUF)
    gut = lizenz.Lizenzstatus(lizenz.GUELTIG, name="T", kennung="ABCDEFGHJKLM")
    monkeypatch.setattr(lizenz_dialog, "frage_nach_lizenz", lambda *a, **k: gut)
    assert main_modul._lizenz_beim_start() is gut


def test_main_kaputter_dialog_startet_nicht_ohne_lizenz(app, main_modul, monkeypatch):
    monkeypatch.delenv(lizenz.ENV_TESTLAUF)

    def kaputt(*a, **k):
        raise RuntimeError("Dialog kaputt")
    monkeypatch.setattr(lizenz_dialog, "frage_nach_lizenz", kaputt)
    from PySide6.QtWidgets import QMessageBox
    gemeldet = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: gemeldet.append(a[2])))
    assert main_modul._lizenz_beim_start() is None
    assert gemeldet and "Lizenzdatei" in gemeldet[0]


def test_main_im_testlauf_ohne_lizenz_keine_abfrage(app, main_modul, monkeypatch):
    """Der Zustand der Suite: Schalter gesetzt, keine Lizenz -> Start ohne Dialog."""
    monkeypatch.setattr(lizenz_dialog, "frage_nach_lizenz",
                        lambda *a, **k: pytest.fail("Dialog im Testlauf"))
    status = main_modul._lizenz_beim_start()
    assert status is not None and not status.ist_gueltig


def test_die_abfrage_haengt_nur_am_gui_start_in_main():
    """Die Abfrage steht in main() nach QApplication und vor MainWindow; sonst
    ruft sie niemand (kein Timer, kein Import-Nebeneffekt, nichts im Kern)."""
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as fh:
        quelle = fh.read()
    rumpf = quelle[quelle.index("\ndef main():"):]
    i_app = rumpf.index("app = QApplication(sys.argv)")
    i_liz = rumpf.index("_lizenz_beim_start()")
    i_win = rumpf.index("window = MainWindow(")
    assert i_app < i_liz < i_win
    assert rumpf.count("_lizenz_beim_start()") == 1
    # --selbsttest / --diagnose verlassen main() vor der QApplication
    assert rumpf.index("if args.selbsttest:") < i_app
    assert rumpf.index("if args.diagnose is not None:") < i_app
    treffer = []
    for wurzel, _dirs, dateien in os.walk(os.path.join(ROOT, "src")):
        for name in dateien:
            if not name.endswith(".py"):
                continue
            pfad = os.path.join(wurzel, name)
            with open(pfad, encoding="utf-8") as fh:
                text = fh.read()
            if "frage_nach_lizenz(" in text or "LizenzDialog(" in text:
                treffer.append(os.path.relpath(pfad, ROOT).replace(os.sep, "/"))
    assert treffer == ["src/ui/lizenz_dialog.py"]


def test_ablaufhinweis_haelt_den_start_nicht_auf(app, main_modul, capsys):
    class Leiste:
        def __init__(self):
            self.texte = []

        def isVisibleTo(self, _w):
            return True

        def showMessage(self, text, ms):
            self.texte.append((text, ms))

    class Fenster:
        def __init__(self):
            self.leiste = Leiste()

        def statusBar(self):
            return self.leiste

    bald = lizenz.Lizenzstatus(lizenz.GUELTIG, name="T", kennung="K",
                               gueltig_bis=dt.date.today() + dt.timedelta(days=3))
    f = Fenster()
    main_modul._lizenz_ablauf_hinweis(f, bald)
    assert f.leiste.texte and "läuft am" in f.leiste.texte[0][0]
    assert "Testlizenz läuft am" in capsys.readouterr().out
    lang = lizenz.Lizenzstatus(lizenz.GUELTIG, name="T", kennung="K",
                               gueltig_bis=dt.date.today() + dt.timedelta(days=90))
    f2 = Fenster()
    main_modul._lizenz_ablauf_hinweis(f2, lang)
    assert f2.leiste.texte == []
    main_modul._lizenz_ablauf_hinweis(object(), bald)      # kaputtes Fenster: kein Wurf


def test_ueber_dialog_nennt_urheber_link_und_status(app, tmp_path):
    from src.ui import hilfe
    text = hilfe.ueber_text()
    assert "Copyright (c) 2026 ixamgames-droid — alle Rechte vorbehalten" in text
    assert "href='https://github.com/ixamgames-droid/lightos'" in text
    assert "nicht lizenziert" in text
    lizenz.installiere(_datei(tmp_path, bis=dt.date(2099, 1, 1)))
    text = hilfe.ueber_text()
    assert "lizenziert für Testerin, gültig bis 01.01.2099" in text
