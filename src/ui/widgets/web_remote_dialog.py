"""WEB-12: Dialog „Web-Remote: Verbindung & Token“ — Handy verbinden in einem
Schritt, Laser-Freigabe, feste Fernbedienung und Roh-DMX unter „Erweitert“.

Frueher stand der Dialog als lange Methode in ``main_window.py``. Der Bedientest
QA-96 (Befund QA96-36) fand dort: im Modus „nur dieser PC“ zeigte er die
LAN-Adresse, der Schluessel stand dreimal offen da, und LAN-Zugriff war ab Werk
an. Jetzt:

* **„📱 Handy verbinden“** schaltet in EINEM Schritt alles Noetige ein —
  LAN-/Handy-Remote, Handy-Konsole, das Web-Interface (bzw. startet es neu,
  wenn es nur an diesem PC lauscht) — und zeigt den QR-Code.
* Der Schluessel der Handy-Konsole steht genau EINMAL im Dialog: im Link unter
  dem QR-Code. „Nur dieser PC“ zeigt ``127.0.0.1`` — die Adresse, die dann
  wirklich gilt.
* **„Laser vom Handy erlauben“** (Vorgabe aus; Entscheidung des
  Projektinhabers vom 12.10.2026): beim Einschalten ein Bestaetigungsfenster
  mit Link auf die Seite mit den Bedingungen
  (``docs/anleitung_web_remote/LASER_VOM_HANDY.md``). Ausschalten wirkt sofort.
* **„Erweitert“**: die feste Fernbedienung (GO, Executor-Fader, Blackout) mit
  eigenem Schluessel und darunter Roh-DMX — beide ab Werk aus.

Den Server startet der Dialog nicht selbst, sondern ueber ``steuerung`` (vom
Hauptfenster: haelt Menue-Haken und Statuszeile mit dem Server in Takt; in
Tests ein Stub). Die Einstellungen schreibt er direkt (``remote_settings``).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame,
                               QHBoxLayout, QLabel, QLayout, QLineEdit,
                               QMessageBox, QPushButton, QToolButton,
                               QVBoxLayout)

#: Die Seite mit den Bedingungen (relativ zu ``docs/``).
LASER_BEDINGUNGEN = "anleitung_web_remote/LASER_VOM_HANDY.md"

LASER_TEXT = (
    "<b>Laser vom Handy erlauben?</b><br><br>"
    "Dann lassen sich Tasten, Fader und Cuelisten mit Laser-Inhalt auch vom "
    "Handy aus bedienen. Bedingungen:"
    "<ul>"
    "<li>Wer am Handy bedient, sieht den ganzen Laser-Bereich und das Publikum.</li>"
    "<li>Am Pult ist jederzeit jemand, der den <b>Laser-NOT-AUS</b> auslösen kann.</li>"
    "<li>Nur im eigenen WLAN; den Schlüssel bzw. QR-Code nicht weitergeben.</li>"
    "<li>Scharfschalten und das Lösen des NOT-AUS bleiben am Pult.</li>"
    "<li>Nach der Veranstaltung den Schalter wieder ausschalten.</li>"
    "</ul>"
    f'<a href="{LASER_BEDINGUNGEN}">Alle Bedingungen lesen …</a>')


def laser_freigabe_bestaetigen(parent=None) -> bool:
    """Das Bestaetigungsfenster vor „Laser vom Handy erlauben“. Vorgabe ist
    „Abbrechen“ — ein Enter im Showbetrieb gibt nichts frei."""
    dlg = QDialog(parent)
    dlg.setObjectName("laser_freigabe_dialog")
    dlg.setWindowTitle("Laser vom Handy erlauben")
    lay = QVBoxLayout(dlg)
    text = QLabel(LASER_TEXT)
    text.setObjectName("laser_freigabe_text")
    text.setWordWrap(True)
    text.setTextFormat(Qt.TextFormat.RichText)
    text.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse
                                 | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
    text.setOpenExternalLinks(False)
    text.linkActivated.connect(lambda _l: _bedingungen_oeffnen())
    text.setMinimumWidth(420)
    lay.addWidget(text)
    knoepfe = QDialogButtonBox()
    ja = knoepfe.addButton("Laser freigeben", QDialogButtonBox.ButtonRole.AcceptRole)
    ja.setObjectName("laser_freigabe_ja")
    nein = knoepfe.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
    nein.setObjectName("laser_freigabe_nein")
    ja.setAutoDefault(False)
    ja.setDefault(False)
    nein.setDefault(True)
    knoepfe.accepted.connect(dlg.accept)
    knoepfe.rejected.connect(dlg.reject)
    lay.addWidget(knoepfe)
    return dlg.exec() == QDialog.DialogCode.Accepted


def _bedingungen_oeffnen() -> None:
    try:
        from src.ui import hilfe
        hilfe.oeffne_doku(LASER_BEDINGUNGEN)
    except Exception as e:
        print(f"[web_remote_dialog] ERROR: Bedingungen nicht geoeffnet: {type(e).__name__}")


class WebRemoteDialog(QDialog):
    """Verbindungs-Dialog des Web-Remotes. ``steuerung`` braucht
    ``laeuft()``, ``starten()``, ``neu_starten()`` und ``melde(text)``."""

    PORT = 5000

    def __init__(self, parent=None, steuerung=None, laser_bestaetigen=None):
        super().__init__(parent)
        self.setObjectName("web_remote_dialog")
        self.setWindowTitle("Web-Remote: Verbindung & Token")
        self._st = steuerung
        self._laser_bestaetigen = laser_bestaetigen or laser_freigabe_bestaetigen
        lay = QVBoxLayout(self)
        # WEB-11: der Dialog folgt seinem Inhalt — der QR-Code erscheint und
        # verschwindet mit den Schaltern.
        lay.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("web_remote_status")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        self.btn_verbinden = QPushButton("📱 Handy verbinden")
        self.btn_verbinden.setObjectName("web_remote_handy_verbinden")
        self.btn_verbinden.setMinimumHeight(40)
        self.btn_verbinden.setStyleSheet("font-weight:bold; font-size:14px;")
        self.btn_verbinden.setToolTip(
            "Schaltet in einem Schritt alles ein, was das Handy braucht: "
            "LAN-/Handy-Remote, Handy-Konsole und das Web-Interface. "
            "Danach den QR-Code mit der Handy-Kamera scannen.")
        self.btn_verbinden.clicked.connect(self.handy_verbinden)
        lay.addWidget(self.btn_verbinden)

        # WEB-11: QR-Code (nur wenn das Handy ihn auch erreicht)
        from src.ui.widgets.handy_qr import HandyQrFeld
        self.qr_feld = HandyQrFeld(klein=False, parent=self)
        lay.addWidget(self.qr_feld)

        # Der Link der Handy-Konsole — die EINZIGE Stelle mit dem Schluessel.
        zeile = QHBoxLayout()
        self.edit_konsole = QLineEdit()
        self.edit_konsole.setReadOnly(True)
        self.edit_konsole.setObjectName("web_remote_konsole_link")
        self.edit_konsole.setMinimumWidth(320)
        zeile.addWidget(self.edit_konsole, 1)
        self.btn_kopieren = QPushButton("Link kopieren")
        self.btn_kopieren.setObjectName("web_remote_link_kopieren")
        self.btn_kopieren.clicked.connect(lambda: self._kopieren(self.edit_konsole.text()))
        zeile.addWidget(self.btn_kopieren)
        lay.addLayout(zeile)

        self.cb_konsole = QCheckBox("Handy-Konsole (bedient nur Elemente der Handy-Seiten)")
        self.cb_konsole.setObjectName("web_remote_handy_konsole")
        self.cb_konsole.setToolTip(
            "Ein: das Handy bedient die Elemente, die in der virtuellen Konsole "
            "auf einer Handy-Seite liegen — sonst nichts.")
        lay.addWidget(self.cb_konsole)

        self.cb_lan = QCheckBox("LAN-/Handy-Remote (aus = nur dieser PC)")
        self.cb_lan.setObjectName("web_remote_lan")
        lay.addWidget(self.cb_lan)

        self.cb_laser = QCheckBox("Laser vom Handy erlauben")
        self.cb_laser.setObjectName("web_remote_laser_vom_handy")
        self.cb_laser.setToolTip(
            "Aus (Vorgabe): Elemente mit Laser-Inhalt sind am Handy gesperrt.\n"
            "Ein: nur nach Bestätigung der Bedingungen.")
        lay.addWidget(self.cb_laser)

        # ── Erweitert ───────────────────────────────────────────────────────
        self.btn_erweitert = QToolButton()
        self.btn_erweitert.setObjectName("web_remote_erweitert")
        self.btn_erweitert.setText("Erweitert")
        self.btn_erweitert.setCheckable(True)
        self.btn_erweitert.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_erweitert.setArrowType(Qt.ArrowType.RightArrow)
        self.btn_erweitert.setAutoRaise(True)
        self.btn_erweitert.toggled.connect(self._erweitert_zeigen)
        lay.addWidget(self.btn_erweitert)
        self.erweitert = QFrame()
        self.erweitert.setObjectName("web_remote_erweitert_bereich")
        self.erweitert.setFrameShape(QFrame.Shape.StyledPanel)
        ew = QVBoxLayout(self.erweitert)
        self.cb_fest = QCheckBox("Feste Fernbedienung (GO, Executor-Fader, Blackout) — "
                                 "eigener Schlüssel")
        self.cb_fest.setObjectName("web_remote_feste_seite")
        self.cb_fest.setToolTip(
            "Die ältere feste Seite (http://…:5000/). Sie bedient Cuelisten, "
            "Executor-Fader und Blackout direkt — unabhängig von den Handy-Seiten.\n"
            "Ihr Link hat einen eigenen Schlüssel; der Link der Handy-Konsole "
            "öffnet sie nicht.")
        ew.addWidget(self.cb_fest)
        self.cb_roh = QCheckBox("Roh-DMX über die feste Fernbedienung (einzelne Kanäle)")
        self.cb_roh.setObjectName("web_remote_roh_dmx")
        self.cb_roh.setToolTip("Schreibt einzelne DMX-Kanäle direkt. Nur zum Einmessen.")
        ew.addWidget(self.cb_roh)
        fz = QHBoxLayout()
        self.edit_fest = QLineEdit()
        self.edit_fest.setReadOnly(True)
        self.edit_fest.setObjectName("web_remote_feste_link")
        fz.addWidget(self.edit_fest, 1)
        self.btn_fest_kopieren = QPushButton("Kopieren")
        self.btn_fest_kopieren.setObjectName("web_remote_feste_link_kopieren")
        self.btn_fest_kopieren.clicked.connect(lambda: self._kopieren(self.edit_fest.text()))
        fz.addWidget(self.btn_fest_kopieren)
        ew.addLayout(fz)
        self.erweitert.setVisible(False)
        lay.addWidget(self.erweitert)

        unten = QHBoxLayout()
        self.btn_erneuern = QPushButton("Schlüssel erneuern (neues Token)")
        self.btn_erneuern.setObjectName("web_remote_schluessel_erneuern")
        self.btn_erneuern.setToolTip(
            "Erzeugt neue Schlüssel. Alle bisherigen Links und QR-Codes werden "
            "sofort ungültig, verbundene Geräte getrennt.")
        self.btn_erneuern.clicked.connect(self._erneuern)
        unten.addWidget(self.btn_erneuern)
        unten.addStretch(1)
        zu = QPushButton("Schließen")
        zu.setObjectName("web_remote_schliessen")
        zu.clicked.connect(self.accept)
        unten.addWidget(zu)
        lay.addLayout(unten)

        self.lbl_hinweis = QLabel()
        self.lbl_hinweis.setObjectName("web_remote_hinweis")
        self.lbl_hinweis.setWordWrap(True)
        self.lbl_hinweis.setStyleSheet("color: #999;")
        lay.addWidget(self.lbl_hinweis)

        self.cb_konsole.toggled.connect(self._konsole_umgelegt)
        self.cb_lan.toggled.connect(self._lan_umgelegt)
        self.cb_laser.toggled.connect(self._laser_umgelegt)
        self.cb_fest.toggled.connect(self._fest_umgelegt)
        self.cb_roh.toggled.connect(self._roh_umgelegt)
        self.qr_feld.geaendert.connect(self.aktualisiere)
        self.aktualisiere()

    # ── Lesen ────────────────────────────────────────────────────────────────

    @staticmethod
    def _rs():
        from src.web import remote_settings
        return remote_settings

    def _laeuft(self) -> bool:
        try:
            return bool(self._st.laeuft()) if self._st is not None else False
        except Exception:
            return False

    def _bind(self) -> str:
        try:
            from src.web import app as web_app
            return web_app.bind_host() if self._laeuft() else ""
        except Exception:
            return ""

    def adresse(self) -> str:
        """Die Adresse, unter der der Server gerade wirklich erreichbar ist —
        bei „nur dieser PC“ ``127.0.0.1`` (QA96-36: nie die LAN-Adresse)."""
        rs = self._rs()
        lan = rs.is_lan_remote_enabled()
        bind = self._bind()
        if not lan or (bind and bind.startswith("127.")):
            return f"http://127.0.0.1:{self.PORT}"
        url = self.qr_feld.url()
        if url:
            return url.split("/konsole", 1)[0]
        from src.web.app import remote_url
        return remote_url(self.PORT)

    def aktualisiere(self) -> None:
        """Alle Anzeigen aus den Einstellungen und dem Serverzustand."""
        if getattr(self, "_im_aktualisieren", False):
            return                  # das QR-Feld meldet sich beim Nachziehen
        self._im_aktualisieren = True
        try:
            self._aktualisiere()
        finally:
            self._im_aktualisieren = False

    def _aktualisiere(self) -> None:
        rs = self._rs()
        self.qr_feld.aktualisiere()
        try:
            lan = rs.is_lan_remote_enabled()
            konsole = rs.is_vc_remote_enabled()
            laser = rs.is_laser_vom_handy_erlaubt()
            fest = rs.is_feste_seite_enabled()
            roh = rs.is_roh_dmx_enabled()
        except Exception:
            lan = konsole = laser = fest = roh = False
        for cb, wert in ((self.cb_lan, lan), (self.cb_konsole, konsole),
                         (self.cb_laser, laser), (self.cb_fest, fest), (self.cb_roh, roh)):
            cb.blockSignals(True)
            cb.setChecked(bool(wert))
            cb.blockSignals(False)
        self.cb_roh.setEnabled(bool(fest))
        laeuft = self._laeuft()
        adresse = self.adresse()
        lokal = adresse.startswith("http://127.0.0.1")
        if not laeuft:
            status = "Web-Interface: aus."
        elif lokal:
            status = f"Web-Interface läuft — nur dieser PC ({adresse[7:]})."
        else:
            status = f"Web-Interface läuft — im (W)LAN erreichbar ({adresse[7:]})."
        bereit = laeuft and konsole and not lokal
        if bereit:
            status += "  Handy-Konsole: bereit."
        elif konsole:
            status += "  Handy-Konsole: an."
        self.lbl_status.setText(status)
        # Der Schluessel steht nur im Link — und der nur, wenn das Handy ihn
        # gerade auch benutzen kann.
        link = self.qr_feld.url()
        if not link and konsole:
            try:
                k = rs.get_token()
            except Exception:
                k = ""
            link = f"{adresse}/konsole?k={k}" if (k and laeuft) else ""
        self.edit_konsole.setText(link)
        self.edit_konsole.setVisible(bool(link))
        self.btn_kopieren.setVisible(bool(link))
        self.btn_verbinden.setText("📱 Handy verbunden — QR-Code scannen" if bereit
                                   else "📱 Handy verbinden")
        if fest:
            try:
                f = rs.get_feste_token()
            except Exception:
                f = ""
            self.edit_fest.setText(f"{adresse}/?k={f}" if f else "")
        else:
            self.edit_fest.setText("")
        self.edit_fest.setVisible(bool(fest))
        self.btn_fest_kopieren.setVisible(bool(fest))
        # Was zu tun ist, sagt bei „nur dieser PC“ schon das QR-Feld.
        self.lbl_hinweis.setText("" if lokal else
                                 "Erreichbar für Geräte im selben (W)LAN — Zugriff "
                                 "nur mit Schlüssel.")
        self.lbl_hinweis.setVisible(not lokal)

    # ── Handlungen ───────────────────────────────────────────────────────────

    def handy_verbinden(self) -> None:
        """Ein Schritt: LAN an, Handy-Konsole an, Web-Interface an (bzw. neu
        gestartet, wenn es nur an diesem PC lauscht)."""
        rs = self._rs()
        try:
            war_lan = rs.is_lan_remote_enabled()
            rs.set_lan_remote_enabled(True)
            if not rs.is_vc_remote_enabled():
                rs.set_vc_remote_enabled(True)
                from src.web import vc_remote
                vc_remote.einstellung_geaendert()
            if self._st is not None:
                if not self._laeuft():
                    self._st.starten()
                elif not war_lan or self._bind().startswith("127."):
                    self._st.neu_starten()
                self._st.melde("Handy-Konsole bereit — den QR-Code mit dem Handy scannen.")
        except Exception as e:
            QMessageBox.warning(self, "Handy verbinden", str(e))
        self.qr_feld.aktualisiere(sofort=True)
        self.aktualisiere()

    def _konsole_umgelegt(self, an: bool) -> None:
        try:
            self._rs().set_vc_remote_enabled(bool(an))
            from src.web import vc_remote
            vc_remote.einstellung_geaendert()
        except Exception as e:
            QMessageBox.warning(self, "Handy-Konsole", str(e))
        self.aktualisiere()

    def _lan_umgelegt(self, an: bool) -> None:
        self._rs().set_lan_remote_enabled(bool(an))
        # NET-09-Falle: die Bind-Adresse wird NUR beim Start gelesen — ein
        # laufender Server muss neu starten, sonst bleibt der Port im LAN offen.
        if self._st is not None and self._laeuft():
            try:
                self._st.neu_starten()
            except Exception as e:
                QMessageBox.warning(self, "Web-Interface Fehler", str(e))
        self.aktualisiere()

    def _laser_umgelegt(self, an: bool) -> None:
        rs = self._rs()
        if an and not self._laser_bestaetigen(self):
            self.cb_laser.blockSignals(True)
            self.cb_laser.setChecked(False)
            self.cb_laser.blockSignals(False)
            return
        rs.set_laser_vom_handy(bool(an))
        if self._st is not None:
            self._st.melde("Laser vom Handy erlaubt." if an
                           else "Laser vom Handy gesperrt.")
        self.aktualisiere()

    def _fest_umgelegt(self, an: bool) -> None:
        rs = self._rs()
        rs.set_feste_seite_enabled(bool(an))
        if not an:
            rs.set_roh_dmx_enabled(False)
        self.aktualisiere()

    def _roh_umgelegt(self, an: bool) -> None:
        self._rs().set_roh_dmx_enabled(bool(an))
        self.aktualisiere()

    def _erweitert_zeigen(self, an: bool) -> None:
        self.btn_erweitert.setArrowType(Qt.ArrowType.DownArrow if an
                                        else Qt.ArrowType.RightArrow)
        self.erweitert.setVisible(bool(an))

    def _kopieren(self, text: str) -> None:
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        if self._st is not None:
            self._st.melde("Link kopiert.")

    def _erneuern(self) -> None:
        # Default bewusst „Nein“: ein Enter im Showbetrieb wuerfe sonst alle
        # Geraete raus.
        if QMessageBox.question(
                self, "Schlüssel erneuern",
                "Neue Schlüssel (Token) machen ALLE bisherigen Links, QR-Codes und "
                "angemeldeten Geräte sofort ungültig.\n\nFortfahren?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            # `regenerate_token` prueft selbst nach, ob wirklich persistiert
            # wurde, und wirft sonst.
            self._rs().regenerate_token()
        except Exception as e:
            QMessageBox.warning(self, "Schlüssel erneuern", str(e))
            self.aktualisiere()
            return
        # Ohne das liefe die Rotation ins Leere: der laufende Server kennt die
        # Schluessel aus seiner Konfiguration (CDX-24).
        from src.web.app import refresh_running_token
        erneuert = refresh_running_token()
        self.qr_feld.aktualisiere(sofort=True)
        self.aktualisiere()
        if self._st is not None:
            self._st.melde("Neue Schlüssel aktiv — alte Links sind ungültig."
                           if erneuert else
                           "Neue Schlüssel gespeichert (wirken beim nächsten Einschalten).")
