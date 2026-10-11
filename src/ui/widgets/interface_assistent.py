"""OUT-70: Assistent „Interface einrichten…“.

Zeigt, was am Rechner haengt, in Klartext — und je Geraet den naechsten
Schritt. Drei Reiter: **USB-Geräte**, **Netzwerk (Art-Net / sACN)**,
**Testsignal**.

Der Assistent rechnet nichts selbst: Befunde und Texte kommen aus
``src/core/dmx/interfaces.py``, das Testsignal aus ``testsignal.py``. Er

* sendet nichts an ein Geraet, solange der Nutzer nicht „einrichten“ oder
  „Testsignal senden“ drueckt,
* installiert nichts und fuehrt keinen Befehl aus (Befehle stehen zum Kopieren
  da, Treiber-Seiten oeffnet der Browser),
* aendert keine Netzwerkeinstellung — die Adressen werden nur angezeigt.

Eingerichtet wird ueber die bestehenden Wege des Ausgabe-Dialogs
(``einrichten``-Rueckruf), nicht ueber einen zweiten.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from src.core.dmx import interfaces, testsignal
from src.ui.widgets.flow_layout import FlowLayout

DOKU_REL = "anleitung_ausgabe_einrichten/INTERFACES.md"

_FARBE = {
    interfaces.AMPEL_GRUEN: "#5fd35f", interfaces.AMPEL_GELB: "#ffb454",
    interfaces.AMPEL_ROT: "#ff5c5c", interfaces.AMPEL_BLAU: "#6aa9ff",
    interfaces.AMPEL_GRAU: "#8a8a8a",
}

NETZ_TEXT = (
    "Ethernet→DMX-Adapter (Art-Net- oder sACN-Nodes) brauchen keinen Treiber: "
    "LightOS schickt die DMX-Daten über das Netzwerk. Das geht auch ohne "
    "Router, mit einem LAN-Kabel direkt vom PC zum Adapter. PC und Adapter "
    "brauchen dafür Adressen im selben Netz (zum Beispiel 192.168.1.10 und "
    "192.168.1.50) — die Adresse des PCs stellst du im Betriebssystem ein; "
    "LightOS zeigt sie hier nur an und ändert nichts.")

NETZ_SUCHE = ("Die Adresse des Adapters steht auf dem Gerät oder in seiner "
              "Anleitung. Automatisch suchen kann LightOS Art-Net-Geräte noch "
              "nicht.")

KOPF_TEXT = ("LightOS liest nur, was das Betriebssystem über angeschlossene "
             "Geräte weiß. Es wird nichts gesendet, nichts installiert und "
             "nichts von selbst eingerichtet.")


def _standard_suche(output_manager=None):
    """Befunde holen — laeuft im Hilfs-Thread, fasst kein Qt-Objekt an."""
    ziele = (interfaces.eingerichtete_ziele(output_manager)
             if output_manager is not None else {})
    bib = None
    try:
        from src.core.dmx.udmx import bibliothek_status
        s = bibliothek_status()
        bib = bool(s.get("pyusb") and s.get("libusb"))
    except Exception:                                    # noqa: BLE001
        bib = None
    return interfaces.erkenne(eingerichtet=ziele, usb_bibliothek=bib)


class GeraeteKarte(QFrame):
    """Ein gefundenes Geraet: Ampel, Klartext, Aktionen."""

    def __init__(self, befund, assistent, universum: int = 1):
        super().__init__()
        self.befund = befund
        self._assistent = assistent
        self.setObjectName("ifcKarte")
        farbe = _FARBE.get(befund.ampel, "#8a8a8a")
        self.setStyleSheet(
            f"#ifcKarte {{ border: 1px solid #3a3a3a; border-left: 4px solid "
            f"{farbe}; border-radius: 4px; background: rgba(255,255,255,0.03); }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(4)

        kopf = QHBoxLayout()
        self.lbl_titel = QLabel(befund.titel)
        self.lbl_titel.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.lbl_titel.setWordWrap(True)
        self.lbl_titel.setMinimumWidth(80)
        kopf.addWidget(self.lbl_titel, 1)
        self.lbl_ampel = QLabel(f"●  {befund.wort}")
        self.lbl_ampel.setStyleSheet(f"color: {farbe}; font-weight: bold;")
        self.lbl_ampel.setAccessibleName(f"Befund: {befund.wort}")
        kopf.addWidget(self.lbl_ampel, 0, Qt.AlignmentFlag.AlignTop)
        for lbl_breit in (self.lbl_titel,):
            lbl_breit.setSizePolicy(QSizePolicy.Policy.Ignored,
                                    QSizePolicy.Policy.Preferred)
        lay.addLayout(kopf)

        zusatz = befund.unterzeile()
        if befund.vermutet:
            zusatz += " · Zuordnung vermutet"
        self.lbl_kennung = QLabel(zusatz)
        self.lbl_kennung.setStyleSheet("color: #9a9a9a;")
        self.lbl_kennung.setWordWrap(True)
        self.lbl_kennung.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.lbl_kennung)

        self.lbl_text = QLabel(befund.text)
        self.lbl_text.setWordWrap(True)
        lay.addWidget(self.lbl_text)

        # Linux: was einmalig einzurichten ist — zum Lesen und Kopieren.
        self.hilfe = QWidget()
        hl = QVBoxLayout(self.hilfe)
        hl.setContentsMargins(0, 4, 0, 0)
        self.lbl_hilfe = QLabel(befund.hilfe)
        self.lbl_hilfe.setWordWrap(True)
        hl.addWidget(self.lbl_hilfe)
        self.txt_befehl = QPlainTextEdit(befund.befehl)
        self.txt_befehl.setReadOnly(True)
        self.txt_befehl.setStyleSheet("font-family: monospace;")
        zeilen = max(1, befund.befehl.count("\n") + 1)
        self.txt_befehl.setFixedHeight(18 * zeilen + 16)
        hl.addWidget(self.txt_befehl)
        zeile = QHBoxLayout()
        self.btn_kopieren = QPushButton("Befehl kopieren")
        self.btn_kopieren.clicked.connect(self._kopieren)
        zeile.addWidget(self.btn_kopieren)
        hinweis = QLabel("LightOS führt den Befehl nicht aus — im Terminal "
                         "einfügen.")
        hinweis.setStyleSheet("color: #9a9a9a;")
        zeile.addWidget(hinweis, 1)
        hl.addLayout(zeile)
        self._hilfe_offen = bool(befund.befehl) and befund.code in (
            interfaces.B_KEINE_BERECHTIGUNG,)
        self.hilfe.setVisible(self._hilfe_offen)
        lay.addWidget(self.hilfe)

        self.lbl_ergebnis = QLabel("")
        self.lbl_ergebnis.setWordWrap(True)
        self.lbl_ergebnis.setVisible(False)
        lay.addWidget(self.lbl_ergebnis)

        # Umbrechend: bei schmalem Fenster rutschen Knoepfe in die naechste
        # Zeile, statt die Karte breiter als das Fenster zu machen.
        knoepfe = FlowLayout(h_spacing=8, v_spacing=6)
        self.spin_universum = None
        self.btn_einrichten = None
        kann = bool(befund.einrichten_als) and befund.code in (
            interfaces.B_BEREIT, interfaces.B_TYP_UNKLAR)
        if kann:
            wahl = QWidget()
            wl = QHBoxLayout(wahl)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(QLabel("Universe:"))
            self.spin_universum = QSpinBox()
            self.spin_universum.setRange(1, 32)
            self.spin_universum.setValue(universum)
            self.spin_universum.valueChanged.connect(self._knopf_text)
            wl.addWidget(self.spin_universum)
            knoepfe.addWidget(wahl)
            self.btn_einrichten = QPushButton("")
            self.btn_einrichten.setDefault(False)
            self.btn_einrichten.clicked.connect(self._einrichten)
            knoepfe.addWidget(self.btn_einrichten)
            self._knopf_text()
        self.btn_treiber = None
        if befund.link:
            self.btn_treiber = QPushButton("Treiber-Seite des Herstellers öffnen")
            self.btn_treiber.setToolTip(befund.link)
            self.btn_treiber.clicked.connect(self._treiber_seite)
            knoepfe.addWidget(self.btn_treiber)
        self.btn_zugriff = None
        # Nur anbieten, wo das Zugriffsrecht die Frage sein kann — nicht an
        # jeder Karte (ein Geraet, das „bereit“ ist, hat sein Recht schon).
        if (befund.befehl and not self._hilfe_offen and befund.code in (
                interfaces.B_TREIBER_FEHLT, interfaces.B_BELEGT)):
            self.btn_zugriff = QPushButton("Zugriffsrecht einrichten (Anleitung)")
            self.btn_zugriff.clicked.connect(self._hilfe_zeigen)
            knoepfe.addWidget(self.btn_zugriff)
        self.btn_anleitung = QPushButton("Anleitung öffnen")
        self.btn_anleitung.clicked.connect(self._anleitung)
        knoepfe.addWidget(self.btn_anleitung)
        lay.addLayout(knoepfe)

    # Bound-Methods statt Lambdas (kein Zyklus Karte -> Knopf -> Lambda).
    def _knopf_text(self, *_):
        art = "Enttec-Pro-kompatibel" if self.befund.einrichten_als == "Enttec" \
            else self.befund.einrichten_als
        self.btn_einrichten.setText(
            f"Als Ausgabe für Universe {self.spin_universum.value()} "
            f"einrichten ({art})")

    def _einrichten(self):
        self._assistent.einrichten_geklickt(self)

    def _treiber_seite(self):
        self._assistent.oeffne_url(self.befund.link)

    def _anleitung(self):
        self._assistent.oeffne_anleitung()

    def _hilfe_zeigen(self):
        self._hilfe_offen = not self._hilfe_offen
        self.hilfe.setVisible(self._hilfe_offen)

    def _kopieren(self):
        try:
            QApplication.clipboard().setText(self.befund.befehl)
            self.btn_kopieren.setText("Kopiert")
        except Exception:                                # noqa: BLE001
            pass

    def zeige_ergebnis(self, text: str):
        self.lbl_ergebnis.setText(text)
        self.lbl_ergebnis.setVisible(bool(text))


class InterfaceAssistent(QDialog):
    """``befunde`` gesetzt = nichts wird gesucht (Tests, Bilder).

    ``einrichten(art, ziel, universum) -> str`` legt die Ausgabe an und liefert
    den Statussatz; ohne Rueckruf gibt es keine Einrichten-Wirkung.
    """

    def __init__(self, parent=None, *, befunde=None, state=None,
                 einrichten=None, netzkarten=None, suche=None,
                 oeffne_url=None, oeffne_doku=None):
        super().__init__(parent)
        self.setWindowTitle("DMX-Interface einrichten")
        self.setMinimumSize(760, 560)
        self._state = state
        self._einrichten = einrichten
        self._suche = suche
        self._oeffne_url = oeffne_url
        self._oeffne_doku = oeffne_doku
        self._netzkarten = netzkarten
        self._such_thread = None
        self._such_ergebnis: dict = {}
        self._laeufe: dict[int, testsignal.Testsignal] = {}
        #: Der Aufrufer (Ausgabe-Dialog) wechselt danach in den Art-Net-Reiter.
        self.artnet_gewuenscht = False
        self.karten: list[GeraeteKarte] = []

        lay = QVBoxLayout(self)
        kopf = QLabel(KOPF_TEXT)
        kopf.setWordWrap(True)
        kopf.setStyleSheet("color: #b0b0b0;")
        lay.addWidget(kopf)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._baue_usb(), "USB-Geräte")
        self.tabs.addTab(self._baue_netz(), "Netzwerk (Art-Net / sACN)")
        self.tabs.addTab(self._baue_test(), "Testsignal")
        self.tabs.currentChanged.connect(self._tab_gewechselt)
        lay.addWidget(self.tabs, 1)

        unten = QHBoxLayout()
        unten.addStretch(1)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        unten.addWidget(zu)
        lay.addLayout(unten)

        self._test_timer = QTimer(self)
        self._test_timer.setInterval(200)
        self._test_timer.timeout.connect(self._test_stand)

        if befunde is not None:
            self.zeige_befunde(list(befunde))
        else:
            self.suche_starten()

    # ── Reiter USB ───────────────────────────────────────────────────────────

    def _baue_usb(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        zeile = QHBoxLayout()
        self.lbl_usb_stand = QLabel("Suche …")
        zeile.addWidget(self.lbl_usb_stand, 1)
        self.btn_suchen = QPushButton("Neu suchen")
        self.btn_suchen.clicked.connect(self.suche_starten)
        zeile.addWidget(self.btn_suchen)
        lay.addLayout(zeile)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._liste = QWidget()
        self._liste_lay = QVBoxLayout(self._liste)
        self._liste_lay.setContentsMargins(0, 0, 0, 0)
        self._liste_lay.setSpacing(8)
        self._liste_lay.addStretch(1)
        self._scroll.setWidget(self._liste)
        lay.addWidget(self._scroll, 1)
        return w

    def _om(self):
        return getattr(self._state, "output_manager", None)

    def suche_starten(self):
        """Im Hilfs-Thread suchen; ein Timer holt das Ergebnis ab (der Thread
        bekommt nur ein Dict und die Suchfunktion, nie den Dialog)."""
        t = self._such_thread
        if t is not None and t.is_alive():
            return
        self.lbl_usb_stand.setText("Suche …")
        ergebnis: dict = {}
        self._such_ergebnis = ergebnis
        suche, om = self._suche, self._om()

        def lauf(ziel=ergebnis):
            try:
                ziel["befunde"] = suche() if suche else _standard_suche(om)
            except Exception as e:                       # noqa: BLE001
                ziel["fehler"] = f"{type(e).__name__}: {e}"

        self._such_thread = threading.Thread(
            target=lauf, name="InterfaceSuche", daemon=True)
        self._such_thread.start()
        timer = getattr(self, "_such_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(100)
            timer.timeout.connect(self._suche_abholen)
            self._such_timer = timer
        timer.start()

    def _suche_abholen(self):
        t = self._such_thread
        if t is not None and t.is_alive():
            return
        self._such_timer.stop()
        e = self._such_ergebnis
        if "fehler" in e:
            self.zeige_befunde([])
            self.lbl_usb_stand.setText(f"Suche gescheitert: {e['fehler']}")
            return
        self.zeige_befunde(list(e.get("befunde") or []))

    def _freies_universum(self) -> int:
        belegt = set()
        try:
            belegt = {int(e["universum"]) for e in self._om().ausgabe_status()}
        except Exception:                                # noqa: BLE001
            pass
        return next((u for u in range(1, 33) if u not in belegt), 1)

    def zeige_befunde(self, befunde: list):
        for k in self.karten:
            self._liste_lay.removeWidget(k)
            k.deleteLater()
        self.karten = []
        alt = getattr(self, "_lbl_leer", None)
        if alt is not None:
            self._liste_lay.removeWidget(alt)
            alt.deleteLater()
            self._lbl_leer = None
        frei = self._freies_universum()
        for i, b in enumerate(befunde):
            karte = GeraeteKarte(b, self, universum=frei)
            self._liste_lay.insertWidget(i, karte)
            self.karten.append(karte)
        if not befunde:
            self._lbl_leer = QLabel(
                "Kein DMX-Interface am USB gefunden.\n\nEingesteckt? Ein "
                "Adapter, der hier fehlt, wird vom Betriebssystem nicht "
                "gesehen (Kabel, anderer USB-Anschluss) — oder er ist ein "
                "Netzwerk-Adapter: dann weiter im Reiter „Netzwerk“.")
            self._lbl_leer.setWordWrap(True)
            self._liste_lay.insertWidget(0, self._lbl_leer)
            self.lbl_usb_stand.setText("Nichts gefunden")
        else:
            n = len(befunde)
            self.lbl_usb_stand.setText(
                f"{n} Gerät{'e' if n != 1 else ''} gefunden")

    def einrichten_geklickt(self, karte: GeraeteKarte):
        b = karte.befund
        universum = karte.spin_universum.value()
        if self._einrichten is None:
            karte.zeige_ergebnis("Einrichten ist hier nicht möglich.")
            return
        vorhandene = []
        try:
            vorhandene = [e for e in self._om().ausgabe_status()
                          if int(e["universum"]) == universum]
        except Exception:                                # noqa: BLE001
            pass
        if vorhandene and not self._frage(
                f"Universe {universum} gibt schon über "
                f"{vorhandene[0].get('weg')} aus. Diese Ausgabe ersetzen?",
                "Ersetzen"):
            return
        try:
            text = self._einrichten(b.einrichten_als, b.einrichten_ziel, universum)
        except Exception as e:                           # noqa: BLE001
            text = f"Fehler: {e}"
        karte.zeige_ergebnis(str(text or ""))
        self._test_neu()

    def oeffne_url(self, link: str):
        if not link.startswith("https://"):
            return
        if self._oeffne_url is not None:
            self._oeffne_url(link)
            return
        from src.ui import hilfe
        hilfe.oeffne(QUrl(link))

    def oeffne_anleitung(self):
        if self._oeffne_doku is not None:
            self._oeffne_doku(DOKU_REL)
            return
        from src.ui import hilfe
        hilfe.oeffne_doku(DOKU_REL)

    # ── Reiter Netzwerk ──────────────────────────────────────────────────────

    def _lies_netzkarten(self) -> list:
        if self._netzkarten is not None:
            return list(self._netzkarten)
        try:
            from src.core.dmx.output_iface import list_output_interfaces
            return list_output_interfaces()
        except Exception:                                # noqa: BLE001
            return []

    def _baue_netz(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        self.lbl_netz = QLabel(NETZ_TEXT)
        self.lbl_netz.setWordWrap(True)
        lay.addWidget(self.lbl_netz)

        titel = QLabel("Adressen dieses Rechners (nur Anzeige)")
        titel.setStyleSheet("font-weight: bold;")
        lay.addWidget(titel)
        self._netz_gitter = QGridLayout()
        self._netz_gitter.setHorizontalSpacing(24)
        self._netz_gitter.setColumnStretch(3, 1)
        lay.addLayout(self._netz_gitter)
        self.netz_zeilen: list[tuple[str, str, str]] = []
        self._netz_fuellen()

        self.lbl_netz_suche = QLabel(NETZ_SUCHE)
        self.lbl_netz_suche.setWordWrap(True)
        self.lbl_netz_suche.setStyleSheet("color: #9a9a9a;")
        lay.addWidget(self.lbl_netz_suche)

        knoepfe = QHBoxLayout()
        self.btn_artnet = QPushButton("Art-Net-Ausgabe einrichten")
        self.btn_artnet.clicked.connect(self._artnet_einrichten)
        knoepfe.addWidget(self.btn_artnet)
        self.btn_netz_anleitung = QPushButton(
            "Anleitung „LAN-Kabel direkt am PC“ öffnen")
        self.btn_netz_anleitung.clicked.connect(self.oeffne_anleitung)
        knoepfe.addWidget(self.btn_netz_anleitung)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)
        lay.addStretch(1)
        return w

    def _netz_fuellen(self):
        g = self._netz_gitter
        karten = [k for k in self._lies_netzkarten()
                  if not str(k.get("ip", "")).startswith("127.")]
        self.netz_zeilen = [(str(k.get("name") or ""), str(k.get("ip") or ""),
                             str(k.get("netmask") or "unbekannt"))
                            for k in karten]
        if not karten:
            leer = QLabel(
                "Keine Netzwerkkarte mit IPv4-Adresse gefunden. Kabel "
                "eingesteckt? Bei einer Direktverbindung muss dem PC im "
                "Betriebssystem eine feste Adresse gegeben werden.")
            leer.setWordWrap(True)
            leer.setStyleSheet("color: #ffb454;")
            g.addWidget(leer, 0, 0, 1, 4)
            return
        for spalte, text in enumerate(("Netzwerkkarte", "IPv4-Adresse",
                                       "Netzmaske")):
            kopf = QLabel(text)
            kopf.setStyleSheet("color: #9a9a9a;")
            g.addWidget(kopf, 0, spalte)
        for zeile, werte in enumerate(self.netz_zeilen, start=1):
            for spalte, text in enumerate(werte):
                lbl = QLabel(text)
                lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse)
                if spalte == 1:
                    lbl.setStyleSheet("font-family: monospace; font-weight: bold;")
                g.addWidget(lbl, zeile, spalte)

    def _artnet_einrichten(self):
        self.artnet_gewuenscht = True
        self.accept()

    # ── Reiter Testsignal ────────────────────────────────────────────────────

    def _baue_test(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        text = QLabel(
            f"Das Testsignal fährt Kanal 1 des gewählten Ausgangs "
            f"{int(testsignal.DAUER_S)} Sekunden langsam auf und ab und setzt "
            f"ihn danach auf 0. Ein Dimmer oder Scheinwerfer auf Adresse 1 "
            f"wird dabei heller und dunkler. Blackout und NOT-AUS gelten "
            f"weiter. Für Universen mit Lasern gibt es kein Testsignal.")
        text.setWordWrap(True)
        lay.addWidget(text)
        self._test_box = QVBoxLayout()
        self._test_box.setSpacing(6)
        lay.addLayout(self._test_box)
        lay.addStretch(1)
        self.test_zeilen: list[dict] = []
        self._test_neu()
        return w

    def _fixtures(self):
        try:
            return list(self._state.get_patched_fixtures())
        except Exception:                                # noqa: BLE001
            return []

    def _test_neu(self):
        box = getattr(self, "_test_box", None)
        if box is None:
            return
        while box.count():
            item = box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.test_zeilen = []
        om = self._om()
        try:
            ausgaben = list(om.ausgabe_status()) if om is not None else []
        except Exception:                                # noqa: BLE001
            ausgaben = []
        if not ausgaben:
            leer = QLabel("Noch keine Ausgabe eingerichtet — erst im Reiter "
                          "„USB-Geräte“ oder „Netzwerk“ einen Ausgang anlegen.")
            leer.setWordWrap(True)
            leer.setStyleSheet("color: #9a9a9a;")
            box.addWidget(leer)
            return
        fixtures = self._fixtures()
        for e in ausgaben:
            universum = int(e["universum"])
            rahmen = QFrame()
            rahmen.setObjectName("ifcTest")
            rahmen.setStyleSheet("#ifcTest { border: 1px solid #3a3a3a; "
                                 "border-radius: 4px; }")
            zl = QGridLayout(rahmen)
            zl.setContentsMargins(10, 6, 10, 6)
            zl.setColumnStretch(0, 1)
            name = QLabel(f"Universe {universum} · {e.get('weg')} → "
                          f"{e.get('ziel') or 'Standardziel'}")
            name.setStyleSheet("font-weight: bold;")
            zl.addWidget(name, 0, 0)
            knopf = QPushButton("Testsignal senden")
            zl.addWidget(knopf, 0, 1)
            stand = QLabel("")
            stand.setWordWrap(True)
            zl.addWidget(stand, 1, 0, 1, 2)
            grund = testsignal.sperre_grund(om, universum, fixtures)
            if grund:
                knopf.setEnabled(False)
                knopf.setText("Testsignal gesperrt")
                stand.setText(grund)
                stand.setStyleSheet("color: #ffb454;")
            else:
                stand.setVisible(False)
            zeile = {"universum": universum, "knopf": knopf, "stand": stand,
                     "gesperrt": bool(grund)}
            knopf.setProperty("universum", universum)
            knopf.clicked.connect(self._test_geklickt)
            self.test_zeilen.append(zeile)
            box.addWidget(rahmen)

    def _frage(self, text: str, ja: str) -> bool:
        """Rueckfrage mit „Abbrechen“ als Vorgabe."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Bitte bestätigen")
        box.setText(text)
        knopf = box.addButton(ja, QMessageBox.ButtonRole.AcceptRole)
        nein = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(nein)
        box.exec()
        return box.clickedButton() is knopf

    def _test_geklickt(self):
        universum = self.sender().property("universum")
        self.testsignal_senden(int(universum))

    def testsignal_senden(self, universum: int) -> str:
        """Rueckfrage, dann Start. Liefert ``""`` (laeuft), den Sperrgrund oder
        ``"abgebrochen"``."""
        zeile = next((z for z in self.test_zeilen
                      if z["universum"] == universum), None)
        om = self._om()
        grund = testsignal.sperre_grund(om, universum, self._fixtures())
        if grund:
            if zeile:
                zeile["stand"].setText(grund)
                zeile["stand"].setVisible(True)
            return grund
        if not self._frage(
                f"Testsignal auf Universe {universum} senden?\n\n"
                f"{testsignal.FRAGE}", "Testsignal senden"):
            return "abgebrochen"
        lauf = testsignal.Testsignal(om, universum, fixtures=self._fixtures)
        grund = lauf.start()
        if grund:
            if zeile:
                zeile["stand"].setText(grund)
                zeile["stand"].setVisible(True)
            return grund
        self._laeufe[universum] = lauf
        if zeile:
            zeile["knopf"].setEnabled(False)
            zeile["stand"].setStyleSheet("")
            zeile["stand"].setText("Testsignal läuft — Kanal 1 fährt auf und ab …")
            zeile["stand"].setVisible(True)
        self._test_timer.start()
        return ""

    def _test_stand(self):
        for universum, lauf in list(self._laeufe.items()):
            if lauf.laeuft:
                continue
            del self._laeufe[universum]
            zeile = next((z for z in self.test_zeilen
                          if z["universum"] == universum), None)
            if zeile is None:
                continue
            zeile["knopf"].setEnabled(True)
            zeile["stand"].setText(
                lauf.abbruch_grund or
                "Fertig, Kanal 1 steht wieder auf 0. Hat ein Gerät reagiert? "
                "Wenn nicht: Kabel, Adresse 1 am Gerät und Adapter-Typ prüfen.")
        if not self._laeufe:
            self._test_timer.stop()

    def _tab_gewechselt(self, index: int):
        if index == 2 and not self._laeufe:
            self._test_neu()

    def _alle_tests_stoppen(self):
        for lauf in list(self._laeufe.values()):
            lauf.stopp()
        self._laeufe.clear()
        self._test_timer.stop()

    def done(self, r):
        self._alle_tests_stoppen()
        super().done(r)

    def closeEvent(self, e):
        self._alle_tests_stoppen()
        super().closeEvent(e)
