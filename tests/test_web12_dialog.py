"""WEB-12: Verbindungs-Dialog — „Handy verbinden“ in einem Schritt, Laser-
Freigabe mit Bestaetigung, feste Fernbedienung und Roh-DMX unter „Erweitert“,
Befund QA96-36 (LAN-Adresse im Modus „nur dieser PC“, Schluessel dreimal offen,
LAN ab Werk an).

Der Dialog wird wirklich gebaut und bedient; der Server wird nie gestartet
(``steuerung`` ist ein Stub), die Einstellungen liegen in einem Wegwerf-Ordner.
"""
import os
import tempfile
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web12d_")

from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog,  # noqa: E402
                               QLabel, QLineEdit, QWidget)

from src.web import handy_verbindung as hv  # noqa: E402
from src.web import remote_settings  # noqa: E402
import src.web.app as web_app  # noqa: E402
from src.ui.widgets import web_remote_dialog as wrd  # noqa: E402

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WLAN = hv.Schnittstelle("WLAN", ("192.168.1.77",))


class _Steuerung:
    def __init__(self, laeuft=False, bind="0.0.0.0"):
        self.laeuft_ = laeuft
        self.bind = bind
        self.aufrufe = []
        self.meldungen = []

    def laeuft(self):
        return self.laeuft_

    def starten(self):
        self.aufrufe.append("starten")
        self.laeuft_ = True
        self.bind = "0.0.0.0" if remote_settings.is_lan_remote_enabled() else "127.0.0.1"

    def neu_starten(self):
        self.aufrufe.append("neu_starten")
        self.bind = "0.0.0.0" if remote_settings.is_lan_remote_enabled() else "127.0.0.1"

    def melde(self, text):
        self.meldungen.append(text)


class _Basis(unittest.TestCase):
    def setUp(self):
        for name in ("lan_remote_enabled", "vc_remote_enabled", "laser_vom_handy",
                     "feste_seite_enabled", "roh_dmx_enabled"):
            remote_settings.save_settings({name: False})
        self.st = _Steuerung()
        for ziel, name, wert in (
                (web_app, "is_running", lambda: self.st.laeuft_),
                (web_app, "bind_host", lambda: self.st.bind if self.st.laeuft_ else ""),
                (web_app, "erlaubte_hosts", lambda: None),
                (web_app, "get_lan_ip", lambda: "192.168.1.77"),
                (hv, "lese_schnittstellen", lambda: [WLAN]),
                (hv, "standard_adresse", lambda: "192.168.1.77")):
            fleck = mock.patch.object(ziel, name, wert)
            fleck.start()
            self.addCleanup(fleck.stop)
        self.addCleanup(lambda: [remote_settings.save_settings({n: False}) for n in (
            "lan_remote_enabled", "vc_remote_enabled", "laser_vom_handy",
            "feste_seite_enabled", "roh_dmx_enabled")])

    def _dialog(self, bestaetigen=None):
        dlg = wrd.WebRemoteDialog(None, steuerung=self.st,
                                  laser_bestaetigen=bestaetigen or (lambda _p: False))
        self.addCleanup(dlg.deleteLater)
        return dlg

    @staticmethod
    def _alle_texte(dlg):
        texte = [dlg.windowTitle()]
        for w in dlg.findChildren(QWidget):
            if not w.isVisibleTo(dlg):
                continue
            texte.append(w.toolTip())
            if isinstance(w, (QLabel, QAbstractButton)):
                texte.append(w.text())
            if isinstance(w, QLineEdit):
                texte.append(w.text())
        return "\n".join(t for t in texte if t)


class HandyVerbindenTest(_Basis):

    def test_ein_schritt_schaltet_alles_ein_und_startet(self):
        dlg = self._dialog()
        self.assertFalse(dlg.qr_feld.hat_code())
        dlg.btn_verbinden.click()
        self.assertTrue(remote_settings.is_lan_remote_enabled())
        self.assertTrue(remote_settings.is_vc_remote_enabled())
        self.assertEqual(self.st.aufrufe, ["starten"])
        self.assertTrue(dlg.qr_feld.hat_code())
        self.assertIn("/konsole?k=", dlg.edit_konsole.text())
        self.assertIn("192.168.1.77", dlg.edit_konsole.text())
        self.assertIn("bereit", dlg.lbl_status.text())
        # Laser, feste Seite und Roh-DMX bleiben aus
        self.assertFalse(remote_settings.is_laser_vom_handy_erlaubt())
        self.assertFalse(remote_settings.is_feste_seite_enabled())
        self.assertFalse(remote_settings.is_roh_dmx_enabled())

    def test_nur_lokal_laufender_server_wird_neu_gestartet(self):
        self.st.laeuft_, self.st.bind = True, "127.0.0.1"
        dlg = self._dialog()
        dlg.handy_verbinden()
        self.assertEqual(self.st.aufrufe, ["neu_starten"])
        self.assertEqual(self.st.bind, "0.0.0.0")

    def test_schon_bereit_startet_nichts_neu(self):
        remote_settings.set_lan_remote_enabled(True)
        remote_settings.set_vc_remote_enabled(True)
        self.st.laeuft_ = True
        dlg = self._dialog()
        dlg.handy_verbinden()
        self.assertEqual(self.st.aufrufe, [])


class AnzeigeTest(_Basis):

    def test_nur_dieser_pc_zeigt_keine_lan_adresse(self):
        self.st.laeuft_, self.st.bind = True, "127.0.0.1"
        remote_settings.set_vc_remote_enabled(True)
        dlg = self._dialog()
        texte = self._alle_texte(dlg)
        self.assertIn("127.0.0.1:5000", dlg.lbl_status.text())
        self.assertIn("nur dieser PC", dlg.lbl_status.text())
        self.assertNotIn("192.168.1.77", texte)

    def test_schluessel_steht_hoechstens_einmal(self):
        remote_settings.set_lan_remote_enabled(True)
        remote_settings.set_vc_remote_enabled(True)
        remote_settings.set_feste_seite_enabled(True)
        self.st.laeuft_ = True
        dlg = self._dialog()
        dlg.btn_erweitert.setChecked(True)
        texte = self._alle_texte(dlg)
        k, f = remote_settings.get_token(), remote_settings.get_feste_token()
        self.assertEqual(texte.count(k), 1, texte)
        self.assertEqual(texte.count(f), 1, texte)
        self.assertIn(k, dlg.edit_konsole.text())
        self.assertIn(f, dlg.edit_fest.text())
        self.assertNotIn(k, dlg.edit_fest.text())

    def test_ohne_konsole_kein_schluessel(self):
        self.st.laeuft_ = True
        remote_settings.set_lan_remote_enabled(True)
        dlg = self._dialog()
        self.assertNotIn(remote_settings.get_token(), self._alle_texte(dlg))
        self.assertFalse(dlg.edit_konsole.isVisibleTo(dlg))


class LaserSchalterTest(_Basis):

    def test_einschalten_nur_nach_bestaetigung(self):
        gefragt = []
        dlg = self._dialog(lambda _p: gefragt.append(1) or False)
        dlg.cb_laser.setChecked(True)
        self.assertEqual(gefragt, [1])
        self.assertFalse(dlg.cb_laser.isChecked())
        self.assertFalse(remote_settings.is_laser_vom_handy_erlaubt())
        dlg2 = self._dialog(lambda _p: True)
        dlg2.cb_laser.setChecked(True)
        self.assertTrue(remote_settings.is_laser_vom_handy_erlaubt())

    def test_ausschalten_ohne_rueckfrage(self):
        remote_settings.set_laser_vom_handy(True)
        gefragt = []
        dlg = self._dialog(lambda _p: gefragt.append(1) or True)
        self.assertTrue(dlg.cb_laser.isChecked())
        dlg.cb_laser.setChecked(False)
        self.assertEqual(gefragt, [])
        self.assertFalse(remote_settings.is_laser_vom_handy_erlaubt())

    def test_bestaetigungsfenster(self):
        gebaut = {}

        def _exec(fenster):
            gebaut["dlg"] = fenster
            return QDialog.DialogCode.Rejected

        with mock.patch.object(QDialog, "exec", _exec):
            self.assertFalse(wrd.laser_freigabe_bestaetigen(None))
        fenster = gebaut["dlg"]
        nein = fenster.findChild(QAbstractButton, "laser_freigabe_nein")
        ja = fenster.findChild(QAbstractButton, "laser_freigabe_ja")
        self.assertTrue(nein.isDefault())          # Enter gibt nichts frei
        self.assertFalse(ja.isDefault())
        text = fenster.findChild(QLabel, "laser_freigabe_text").text()
        self.assertIn(f'href="{wrd.LASER_BEDINGUNGEN}"', text)
        self.assertIn("NOT-AUS", text)
        self.assertTrue(os.path.isfile(os.path.join(_REPO, "docs", *wrd.LASER_BEDINGUNGEN.split("/"))))
        with mock.patch("src.ui.hilfe.oeffne_doku") as oeffne:
            fenster.findChild(QLabel, "laser_freigabe_text").linkActivated.emit(
                wrd.LASER_BEDINGUNGEN)
            oeffne.assert_called_once_with(wrd.LASER_BEDINGUNGEN)
        fenster.deleteLater()


class ErweitertTest(_Basis):

    def test_feste_seite_und_roh_dmx_unter_erweitert(self):
        dlg = self._dialog()
        self.assertFalse(dlg.erweitert.isVisibleTo(dlg))
        self.assertIs(dlg.cb_fest.parent(), dlg.erweitert)
        self.assertIs(dlg.cb_roh.parent(), dlg.erweitert)
        dlg.btn_erweitert.setChecked(True)
        self.assertTrue(dlg.erweitert.isVisibleTo(dlg))
        self.assertFalse(dlg.cb_roh.isEnabled())       # nur mit fester Seite
        dlg.cb_fest.setChecked(True)
        self.assertTrue(remote_settings.is_feste_seite_enabled())
        self.assertTrue(dlg.cb_roh.isEnabled())
        dlg.cb_roh.setChecked(True)
        self.assertTrue(remote_settings.is_roh_dmx_enabled())
        dlg.cb_fest.setChecked(False)                  # nimmt Roh-DMX mit
        self.assertFalse(remote_settings.is_roh_dmx_enabled())
        self.assertFalse(dlg.cb_roh.isChecked())


class ErneuernTest(_Basis):

    def test_erneuern_mit_rueckfrage_und_laufendem_server(self):
        from PySide6.QtWidgets import QMessageBox
        dlg = self._dialog()
        with mock.patch.object(remote_settings, "regenerate_token") as regen, \
                mock.patch.object(web_app, "refresh_running_token",
                                  return_value=True) as frisch, \
                mock.patch.object(QMessageBox, "question",
                                  return_value=QMessageBox.StandardButton.No):
            dlg.btn_erneuern.click()
            regen.assert_not_called()
        with mock.patch.object(remote_settings, "regenerate_token") as regen, \
                mock.patch.object(web_app, "refresh_running_token",
                                  return_value=True) as frisch, \
                mock.patch.object(QMessageBox, "question",
                                  return_value=QMessageBox.StandardButton.Yes):
            dlg.btn_erneuern.click()
            regen.assert_called_once()
            frisch.assert_called_once()


class HauptfensterTest(_Basis):
    """Das Hauptfenster baut DIESEN Dialog, und die Seitenleiste ruft ihn mit
    „verbinden“ auf."""

    def _fenster(self):
        from src.ui import main_window as mw

        class _Fenster(QWidget):
            def statusBar(self):
                return types.SimpleNamespace(showMessage=lambda *a, **k: None)

        f = _Fenster()
        self.addCleanup(f.deleteLater)
        f._act_web = types.SimpleNamespace(setChecked=lambda _b: None)
        f._lbl_web = types.SimpleNamespace(setText=lambda _t: None,
                                           setStyleSheet=lambda _s: None)
        return mw, f

    def test_open_mit_verbinden_schaltet_ein(self):
        mw, f = self._fenster()
        gebaut = {}

        def _exec(dlg):
            gebaut["dlg"] = dlg
            return 0

        with mock.patch.object(QDialog, "exec", _exec), \
                mock.patch.object(web_app, "start_server",
                                  lambda *_a: setattr(self.st, "laeuft_", True)):
            mw.MainWindow._open_web_remote_dialog(f, verbinden=True)
        self.assertIsInstance(gebaut["dlg"], wrd.WebRemoteDialog)
        self.assertTrue(remote_settings.is_lan_remote_enabled())
        self.assertTrue(remote_settings.is_vc_remote_enabled())
        self.assertTrue(self.st.laeuft_)

    def test_seitenleiste_fragt_verbinden_an(self):
        from src.ui.views.virtual_console_view import VirtualConsoleView
        aufrufe = []
        fenster = types.SimpleNamespace(
            _open_web_remote_dialog=lambda **k: aufrufe.append(k))
        view = types.SimpleNamespace(window=lambda: fenster, _handy_leiste=None)
        VirtualConsoleView._handy_verbinden(view)
        self.assertEqual(aufrufe, [{"verbinden": True}])

    def test_knopf_in_der_seitenleiste_heisst_handy_verbinden(self):
        from src.ui.virtualconsole.vc_handy_leiste import HandyKonsolenLeiste
        quelle = open(os.path.join(_REPO, "src", "ui", "virtualconsole",
                                   "vc_handy_leiste.py"), encoding="utf-8").read()
        self.assertIn('QPushButton("📱 Handy verbinden")', quelle)
        self.assertTrue(HandyKonsolenLeiste)


if __name__ == "__main__":
    unittest.main()
