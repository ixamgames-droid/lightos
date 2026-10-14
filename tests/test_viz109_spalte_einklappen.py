"""VIZ-109: rechte Spalte des 3D-Visualizers per Knopf ein-/ausklappen.

Geprueft wird die Kopplung Knopf <-> Splitter <-> gemerkter Zustand an einem
echten ``QSplitter`` (ohne WebEngine): umschalten, Breite wiederherstellen,
Zustand ueber einen Neuaufbau hinweg, von Hand zugezogene Leiste, und dass die
linke Seite (die 3D-Ansicht) dabei dasselbe, durchgehend sichtbare Widget bleibt.
"""
import json
import os
import re

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter, QWidget

import src.ui.views.programmer_view as PV
import src.ui.visualizer.spalte_einklappen as SE
from _qt_lifecycle import destroy_all_top_level_widgets

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FENSTER = os.path.join(_ROOT, "src", "ui", "visualizer", "visualizer_window.py")
_ANLEITUNG = os.path.join(_ROOT, "docs", "anleitung_3d_visualizer_2026",
                          "ANLEITUNG_3D_BUEHNE.md")


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    """Einstellungs-Ablage in einen Wegwerf-Ordner umlenken."""
    pfad = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(PV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(PV, "_PREFS_PATH", str(pfad))

    def lesen():
        return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
    return lesen


class _Zaehler(QObject):
    """Zaehlt Hide-Ereignisse eines Widgets."""

    def __init__(self, ziel):
        super().__init__(ziel)
        self.hides = 0
        ziel.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Hide:
            self.hides += 1
        return False


def _aufbau(breite=1200):
    """Splitter wie im Visualizer: links Ansicht, rechts Spalte ab 330 px."""
    sp = QSplitter()
    links = QWidget()
    rechts = QWidget()
    rechts.setMinimumWidth(330)
    sp.addWidget(links)
    sp.addWidget(rechts)
    sp.setStretchFactor(0, 1)
    sp.setStretchFactor(1, 0)
    sp.setCollapsible(0, False)
    knopf = SE.baue_knopf()
    klappe = SE.SpaltenKlappe(sp, knopf, 1)
    sp.resize(breite, 600)
    sp.show()
    _app.processEvents()
    _app.processEvents()
    return sp, links, rechts, knopf, klappe


def _von_hand(sp, groessen):
    """Wie Ziehen an der Leiste: Groessen setzen + das Signal des Ziehens."""
    sp.setSizes(groessen)
    sp.splitterMoved.emit(sp.sizes()[0], 1)


def test_knopf_klappt_ein_und_aus(prefs):
    sp, links, rechts, knopf, klappe = _aufbau()
    assert not klappe.eingeklappt
    assert sp.sizes()[1] >= 330
    assert knopf.text() == SE.PFEIL_EINKLAPPEN
    assert knopf.toolTip() == "Rechte Spalte einklappen (F9)"

    knopf.click()
    assert klappe.eingeklappt
    assert sp.sizes()[1] == 0
    assert knopf.text() == SE.PFEIL_AUSKLAPPEN
    assert knopf.toolTip() == "Rechte Spalte ausklappen (F9)"

    knopf.click()
    assert not klappe.eingeklappt
    assert sp.sizes()[1] >= 330
    assert knopf.text() == SE.PFEIL_EINKLAPPEN


def test_ausklappen_bringt_die_vorherige_breite_zurueck(prefs):
    sp, links, rechts, knopf, klappe = _aufbau()
    gesamt = sum(sp.sizes())
    _von_hand(sp, [gesamt - 400, 400])
    assert sp.sizes()[1] == 400

    klappe.umschalten()
    assert sp.sizes()[1] == 0
    assert klappe.gemerkte_breite == 400
    klappe.umschalten()
    assert sp.sizes()[1] == 400
    # Die Ansicht bekommt beim Einklappen den ganzen Platz, danach den Rest.
    assert sum(sp.sizes()) == gesamt


def test_ansicht_bleibt_dasselbe_sichtbare_widget(prefs):
    sp, links, rechts, knopf, klappe = _aufbau()
    zaehler = _Zaehler(links)
    for _ in range(3):
        klappe.umschalten()
        _app.processEvents()
        assert sp.widget(0) is links
        assert sp.widget(1) is rechts
        assert links.isVisible()
        assert links.parent() is sp
    assert zaehler.hides == 0
    assert sp.count() == 2


def test_zustand_und_breite_ueberleben_schliessen_und_oeffnen(prefs):
    sp, links, rechts, knopf, klappe = _aufbau()
    gesamt = sum(sp.sizes())
    _von_hand(sp, [gesamt - 380, 380])
    klappe.umschalten()
    assert prefs() == {SE.PREF_EINGEKLAPPT: True, SE.PREF_BREITE: 380}

    # Fenster nur versteckt und wieder gezeigt (so schliesst der Visualizer).
    sp.hide()
    sp.show()
    _app.processEvents()
    assert sp.sizes()[1] == 0 and klappe.eingeklappt

    # Programm neu gestartet: neuer Splitter, neuer Knopf, selbe Ablage.
    sp.close()
    sp2, _l, _r, knopf2, klappe2 = _aufbau()
    assert klappe2.eingeklappt
    assert sp2.sizes()[1] == 0
    assert knopf2.text() == SE.PFEIL_AUSKLAPPEN
    klappe2.umschalten()
    assert sp2.sizes()[1] == 380
    assert prefs()[SE.PREF_EINGEKLAPPT] is False


def test_offene_spalte_kommt_mit_gemerkter_breite_wieder(prefs):
    PV._save_prefs({SE.PREF_EINGEKLAPPT: False, SE.PREF_BREITE: 410})
    sp, links, rechts, knopf, klappe = _aufbau()
    assert not klappe.eingeklappt
    assert sp.sizes()[1] == 410


def test_von_hand_zugezogen_zeigt_der_knopf_den_richtigen_zustand(prefs):
    sp, links, rechts, knopf, klappe = _aufbau()
    gesamt = sum(sp.sizes())
    _von_hand(sp, [gesamt - 390, 390])
    meldungen = []
    klappe.geaendert.connect(meldungen.append)

    _von_hand(sp, [gesamt, 0])
    assert klappe.eingeklappt
    assert knopf.text() == SE.PFEIL_AUSKLAPPEN
    assert knopf.toolTip() == SE.TIPP_AUSKLAPPEN
    assert klappe.gemerkte_breite == 390      # 0 ueberschreibt die Breite nicht
    assert meldungen == [True]

    knopf.click()                              # Knopf oeffnet auf die alte Breite
    assert sp.sizes()[1] == 390

    klappe.umschalten()
    _von_hand(sp, [gesamt - 350, 350])         # von Hand wieder aufgezogen
    assert not klappe.eingeklappt
    assert knopf.text() == SE.PFEIL_EINKLAPPEN
    assert klappe.gemerkte_breite == 350
    klappe.sichern()
    assert prefs() == {SE.PREF_EINGEKLAPPT: False, SE.PREF_BREITE: 350}


def test_ziehen_schreibt_verzoegert_nicht_je_mausbewegung(prefs, monkeypatch):
    sp, links, rechts, knopf, klappe = _aufbau()
    schreibvorgaenge = []
    monkeypatch.setattr(SE, "_speichere_prefs", schreibvorgaenge.append)
    gesamt = sum(sp.sizes())
    for b in (340, 350, 360, 370):
        _von_hand(sp, [gesamt - b, b])
    assert schreibvorgaenge == []
    klappe.sichern()
    assert schreibvorgaenge == [{SE.PREF_EINGEKLAPPT: False, SE.PREF_BREITE: 370}]


def test_kaputte_ablage_stoert_nicht(prefs):
    PV._save_prefs({SE.PREF_EINGEKLAPPT: "ja", SE.PREF_BREITE: "breit"})
    sp, links, rechts, knopf, klappe = _aufbau()
    assert klappe.gemerkte_breite == 0
    klappe.umschalten()          # war "ja" -> eingeklappt -> jetzt offen
    assert sp.sizes()[1] >= 330


def test_fehler_beim_speichern_im_log_format(monkeypatch, capsys):
    """Codex-Review #1082 (CDX-59): Fehler im Log als ``[modul] ERROR: …``
    (AGENTS.md)."""
    def kaputt(_werte):
        raise OSError("Platte voll")
    monkeypatch.setattr(PV, "_save_prefs", kaputt)
    SE._speichere_prefs({SE.PREF_BREITE: 300})
    zeile = capsys.readouterr().out.strip()
    assert zeile.startswith("[spalte_einklappen] ERROR: "), zeile
    assert "Platte voll" in zeile


def test_gemerkte_breite_ueber_der_hoechstbreite_wird_begrenzt(prefs):
    """Ein zu grosser gemerkter Wert darf weder einen leeren Streifen neben
    der Spalte lassen noch der Ansicht die Breite nehmen."""
    def aufbau_mit_hoechstbreite():
        sp = QSplitter()
        links, rechts = QWidget(), QWidget()
        rechts.setMinimumWidth(330)
        rechts.setMaximumWidth(420)
        sp.addWidget(links)
        sp.addWidget(rechts)
        sp.setStretchFactor(0, 1)
        sp.setCollapsible(0, False)
        klappe = SE.SpaltenKlappe(sp, SE.baue_knopf(), 1)
        sp.resize(1200, 600)
        sp.show()
        _app.processEvents()
        _app.processEvents()
        return sp, links, rechts, klappe

    PV._save_prefs({SE.PREF_EINGEKLAPPT: False, SE.PREF_BREITE: 5000})
    sp, links, rechts, klappe = aufbau_mit_hoechstbreite()
    assert sp.sizes()[1] == 420 and rechts.width() == 420
    assert links.width() > 600
    assert klappe.gemerkte_breite == 420

    sp.close()
    PV._save_prefs({SE.PREF_EINGEKLAPPT: True, SE.PREF_BREITE: 5000})
    sp, links, rechts, klappe = aufbau_mit_hoechstbreite()
    assert sp.sizes()[1] == 0
    klappe.umschalten()
    assert sp.sizes()[1] == 420 and rechts.width() == 420
    assert links.width() > 600
    assert prefs()[SE.PREF_BREITE] == 420


def test_fenster_haengt_knopf_und_taste_an_den_vorhandenen_splitter():
    with open(_FENSTER, encoding="utf-8") as f:
        quelle = f.read()
    assert "SpaltenKlappe(splitter, self._btn_spalte, 1, self)" in quelle
    assert "left_lay.addWidget(self._view, 1)" in quelle
    # Die Ansicht wird weiterhin genau einmal gebaut.
    assert quelle.count("self._view = QWebEngineView" + "()") == 1
    # F9 ist im Fenster nur einmal belegt.
    assert len(re.findall(r'\("F9",', quelle)) == 1
    assert SE.TASTE == "F9"


def test_anleitung_nennt_knopf_und_taste():
    with open(_ANLEITUNG, encoding="utf-8") as f:
        text = f.read()
    assert "Rechte Spalte einklappen" in text
    assert "| `F9` |" in text


class _AnsichtOhneWebEngine(QWidget):
    """Platzhalter fuer die 3D-Ansicht — das Fenster wird echt gebaut, nur
    Chromium bleibt draussen."""

    def page(self):
        return MagicMock()

    def settings(self):
        return MagicMock()


def test_echtes_fenster_knopf_und_f9(prefs, monkeypatch):
    import src.ui.visualizer.visualizer_window as VW
    monkeypatch.setattr(VW, "QWebEngineView", _AnsichtOhneWebEngine)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_channel", lambda self: None)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_service_target",
                        lambda self: None)
    fenster = VW.VisualizerWindow()
    fenster._bridge = MagicMock()
    fenster.show()
    _app.processEvents()
    _app.processEvents()

    sp = fenster.centralWidget()
    assert isinstance(sp, QSplitter)
    ansicht = fenster._view
    offen = sp.sizes()[1]
    assert offen > 0
    # Der Knopf sitzt rechts an der Ansicht, also direkt an der Spalte.
    assert fenster._btn_spalte.geometry().left() == ansicht.geometry().right() + 1

    fenster._btn_spalte.click()
    _app.processEvents()
    assert sp.sizes()[1] == 0
    assert fenster._view is ansicht and ansicht.isVisible()
    assert fenster._btn_spalte.isVisible()
    assert ansicht.width() > 0

    QTest.keyClick(fenster, Qt.Key.Key_F9)
    _app.processEvents()
    # Zurueck kommt die vorherige Breite, hoechstens aber so viel, wie die
    # Spalte fuellen kann (kein leerer Streifen daneben).
    spalte = sp.widget(1)
    assert sp.sizes()[1] == min(offen, spalte.maximumWidth())
    assert spalte.width() == sp.sizes()[1]
    assert prefs()[SE.PREF_EINGEKLAPPT] is False


def _echtes_fenster(monkeypatch):
    import src.ui.visualizer.visualizer_window as VW
    monkeypatch.setattr(VW, "QWebEngineView", _AnsichtOhneWebEngine)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_channel", lambda self: None)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_service_target",
                        lambda self: None)
    fenster = VW.VisualizerWindow()
    fenster._bridge = MagicMock()
    fenster.show()
    _app.processEvents()
    _app.processEvents()
    return fenster


def test_reiter_taste_klappt_die_eingeklappte_spalte_aus(prefs, monkeypatch):
    """S und F wechseln den Reiter — bei eingeklappter Spalte saehe man das
    nicht. Die Taste holt die Spalte deshalb in der gemerkten Breite zurueck."""
    fenster = _echtes_fenster(monkeypatch)
    sp = fenster.centralWidget()
    # Gemerkte Breite: hoechstens so viel, wie die Spalte fuellen kann.
    offen = min(sp.sizes()[1], sp.widget(1).maximumWidth())
    assert offen > 0
    # F soll hier der Reiter-Sprung sein, nicht "Fit Auswahl".
    monkeypatch.setattr(fenster, "_focus_is_in_3d", lambda: False)

    for taste, reiter in ((Qt.Key.Key_S, 1), (Qt.Key.Key_F, 0)):
        fenster._tabs.setCurrentIndex(2)
        fenster._spalten_klappe.setze_eingeklappt(True)
        _app.processEvents()
        assert sp.sizes()[1] == 0

        QTest.keyClick(fenster, taste)
        _app.processEvents()
        assert fenster._tabs.currentIndex() == reiter
        assert sp.sizes()[1] == offen, taste
        assert fenster._spalten_klappe.eingeklappt is False
        assert fenster._btn_spalte.toolTip() == SE.TIPP_EINKLAPPEN
    assert prefs()[SE.PREF_EINGEKLAPPT] is False


def test_nur_die_reiter_taste_klappt_aus(prefs, monkeypatch):
    """Andere Tasten und ein Reiterwechsel per Programm lassen die Spalte zu."""
    fenster = _echtes_fenster(monkeypatch)
    sp = fenster.centralWidget()
    fenster._spalten_klappe.setze_eingeklappt(True)
    _app.processEvents()
    assert sp.sizes()[1] == 0

    # Per Programm (Wiederherstellen, Sprung nach dem Anlegen): bleibt zu.
    for reiter in (1, 2, 0):
        fenster._tabs.setCurrentIndex(reiter)
        _app.processEvents()
        assert sp.sizes()[1] == 0

    # Tasten ohne Bezug zur Spalte: bleibt zu.
    for taste in (Qt.Key.Key_V, Qt.Key.Key_E):
        QTest.keyClick(fenster, taste)
        _app.processEvents()
        assert sp.sizes()[1] == 0, taste

    # F mit Fokus in der 3D-Ansicht heisst "Fit Auswahl" — kein Reiterwechsel.
    monkeypatch.setattr(fenster, "_focus_is_in_3d", lambda: True)
    monkeypatch.setattr(fenster, "_on_fit_selected", lambda: None)
    fenster._tabs.setCurrentIndex(2)
    QTest.keyClick(fenster, Qt.Key.Key_F)
    _app.processEvents()
    assert fenster._tabs.currentIndex() == 2
    assert sp.sizes()[1] == 0
    assert fenster._spalten_klappe.eingeklappt is True


# ── Erster Start ohne gemerkte Breite: kein leerer Streifen ──────────────────

class _BreiterWunsch(QWidget):
    """Spalte, deren Wunschbreite ueber ihrer Hoechstbreite liegt — so wie die
    echte Spalte mit ihren Reitern (558 gegen 420 px)."""

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(558, 400)


def _aufbau_breiter_wunsch(breite=1400):
    sp = QSplitter()
    links, rechts = QWidget(), _BreiterWunsch()
    rechts.setMinimumWidth(330)
    rechts.setMaximumWidth(420)
    sp.addWidget(links)
    sp.addWidget(rechts)
    sp.setStretchFactor(0, 1)
    sp.setStretchFactor(1, 0)
    sp.setCollapsible(0, False)
    klappe = SE.SpaltenKlappe(sp, SE.baue_knopf(), 1)
    sp.resize(breite, 600)
    sp.show()
    _app.processEvents()
    _app.processEvents()
    return sp, links, rechts, klappe


def _kein_streifen(sp, spalte):
    """Die Spalte fuellt, was der Splitter ihr gibt, und reicht bis zum Rand."""
    _app.processEvents()
    _app.processEvents()
    assert sp.sizes()[1] == spalte.width(), (sp.sizes(), spalte.width())
    assert sp.sizes()[1] <= spalte.maximumWidth()
    assert spalte.geometry().right() == sp.contentsRect().right()
    assert sum(sp.sizes()) + sp.handleWidth() == sp.contentsRect().width()


def test_erster_start_ohne_gemerkte_breite_laesst_keinen_streifen(prefs):
    sp, links, rechts, klappe = _aufbau_breiter_wunsch()
    assert klappe.gemerkte_breite == 0          # wirklich der erste Start
    assert sp.sizes()[1] == 420
    _kein_streifen(sp, rechts)
    assert links.width() == 1400 - 420 - sp.handleWidth()
    # Beim Vergroessern und Verkleinern bekommt die Ansicht den Unterschied.
    for breite in (1900, 2400, 1000, 1500):
        sp.resize(breite, 600)
        _kein_streifen(sp, rechts)
        assert sp.sizes()[1] == 420, breite
        assert links.width() == breite - 420 - sp.handleWidth()
    # Einklappen merkt sich die Breite, die die Spalte wirklich hatte.
    klappe.umschalten()
    assert klappe.gemerkte_breite == 420
    klappe.umschalten()
    _kein_streifen(sp, rechts)


def test_einklappen_aus_zu_breitem_stand_merkt_die_hoechstbreite(prefs):
    """Auch wenn jemand einklappt, bevor die Korrektur gelaufen ist, darf sich
    kein Wert ueber der Hoechstbreite festsetzen."""
    sp, links, rechts, klappe = _aufbau_breiter_wunsch()
    gesamt = sum(sp.sizes())
    sp.setSizes([gesamt - 558, 558])             # der alte Fehlstand
    klappe.umschalten()
    assert klappe.gemerkte_breite == 420
    assert prefs()[SE.PREF_BREITE] == 420
    klappe.umschalten()
    assert sp.sizes()[1] == 420
    _kein_streifen(sp, rechts)


def test_echtes_fenster_erster_start_ohne_streifen(prefs, monkeypatch):
    fenster = _echtes_fenster(monkeypatch)
    sp = fenster.centralWidget()
    spalte = sp.widget(1)
    # Voraussetzung des Befunds: die Spalte wuenscht sich mehr, als sie darf.
    assert spalte.sizeHint().width() > spalte.maximumWidth() == 420
    _kein_streifen(sp, spalte)
    assert sp.sizes()[1] == 420
    for breite in (1900, 1100, 1600):
        fenster.resize(breite, 850)
        _kein_streifen(sp, spalte)
        assert sp.sizes()[1] == 420, breite
    assert fenster._view.width() + fenster._btn_spalte.width() == sp.sizes()[0]


# ── S und F gleich verlaesslich ──────────────────────────────────────────────

def test_fokus_in_der_eingeklappten_spalte_schluckt_s_und_f_nicht(prefs, monkeypatch):
    """Der Splitter schiebt die eingeklappte Spalte nur aus dem Bild. Stand der
    Fokus in einem ihrer Eingabefelder, gingen S und F als Text dorthin — und
    die Spalte blieb zu."""
    from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit
    fenster = _echtes_fenster(monkeypatch)
    fenster.activateWindow()
    _app.processEvents()
    sp = fenster.centralWidget()
    spalte = sp.widget(1)
    monkeypatch.setattr(fenster, "_on_fit_selected", lambda: None)

    for taste, reiter in ((Qt.Key.Key_S, 1), (Qt.Key.Key_F, 0)):
        fenster._tabs.setCurrentIndex(2 if reiter == 0 else 0)
        _app.processEvents()
        felder = [w for w in fenster._tabs.currentWidget().findChildren(QWidget)
                  if isinstance(w, (QLineEdit, QAbstractSpinBox))
                  and not isinstance(w.parentWidget(), QAbstractSpinBox)
                  and w.isVisible() and w.isEnabled()
                  and w.focusPolicy() != Qt.FocusPolicy.NoFocus]
        assert felder, "kein Eingabefeld auf dem Reiter"
        felder[0].setFocus()
        _app.processEvents()
        assert spalte.isAncestorOf(fenster.focusWidget())

        fenster._btn_spalte.click()
        _app.processEvents()
        assert sp.sizes()[1] == 0
        fokus = fenster.focusWidget()
        assert fokus is None or not spalte.isAncestorOf(fokus)

        QTest.keyClick(fenster, taste)
        _app.processEvents()
        assert fenster._tabs.currentIndex() == reiter, taste
        assert sp.sizes()[1] == 420, taste
        assert fenster._spalten_klappe.eingeklappt is False


def test_von_hand_zugezogen_gibt_den_fokus_ebenfalls_ab(prefs):
    from PySide6.QtWidgets import QLineEdit, QVBoxLayout
    sp, links, rechts, knopf, klappe = _aufbau()
    feld = QLineEdit()
    QVBoxLayout(rechts).addWidget(feld)
    feld.setFocus()
    _app.processEvents()
    assert sp.focusWidget() is feld
    _von_hand(sp, [sum(sp.sizes()), 0])
    assert klappe.eingeklappt
    assert sp.focusWidget() is not feld


def test_f_in_der_3d_ansicht_bleibt_fit_auswahl_und_sagt_es(prefs, monkeypatch):
    """F hat in der 3D-Ansicht eine eigene Bedeutung (A3D-29, Kamera-Menue
    „Fit Auswahl  (F)"). Die bleibt — bei eingeklappter Spalte nennt die
    Statuszeile aber, womit man ausklappt."""
    import src.ui.visualizer.visualizer_window as VW
    fenster = _echtes_fenster(monkeypatch)
    sp = fenster.centralWidget()
    gerufen = []
    monkeypatch.setattr(fenster, "_focus_is_in_3d", lambda: True)
    monkeypatch.setattr(fenster, "_on_fit_selected", lambda: gerufen.append(1))

    # Spalte offen: Fit Auswahl, kein Hinweis.
    vorher = fenster._lbl_info.text()
    QTest.keyClick(fenster, Qt.Key.Key_F)
    _app.processEvents()
    assert gerufen == [1] and fenster._lbl_info.text() == vorher

    fenster._spalten_klappe.setze_eingeklappt(True)
    QTest.keyClick(fenster, Qt.Key.Key_F)
    _app.processEvents()
    assert gerufen == [1, 1]
    assert sp.sizes()[1] == 0
    assert fenster._lbl_info.text() == VW.HINWEIS_F_IN_DER_ANSICHT
    assert "F9" in VW.HINWEIS_F_IN_DER_ANSICHT and " S " in VW.HINWEIS_F_IN_DER_ANSICHT
    # S hat in der 3D-Ansicht keine zweite Bedeutung und klappt immer aus.
    QTest.keyClick(fenster, Qt.Key.Key_S)
    _app.processEvents()
    assert sp.sizes()[1] == 420 and fenster._tabs.currentIndex() == 1
    with open(_ANLEITUNG, encoding="utf-8") as f:
        anleitung = f.read()
    assert "Fit Auswahl" in anleitung and "nur, solange der Fokus **nicht**" in anleitung
