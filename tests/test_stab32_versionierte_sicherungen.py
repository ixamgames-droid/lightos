"""STAB-32: versionierte Sicherungen statt einer einzigen Auto-Save-Datei.

Vorher gab es genau eine Sicherung (``auto_save.lshow``); ein kaputter oder
ungewollter Stand ueberschrieb darin den letzten guten, und ein manuelles
Speichern ueber eine vorhandene Datei liess vom Vorgaenger nichts uebrig.

Geprueft wird (alles im Temp-App-Datenordner, nie in echten App-Daten):

* Staffelung mit injizierter Uhr, Groessengrenze, Reste einer alten Sitzung;
* Schreiben: der eingefrorene Stand ueberlebt das Ersetzen der Quelle, keine
  Temp-Reste, auch ohne Hardlinks; ein Schreibfehler blockiert nichts;
* Hauptfenster: Sicherung vor dem Ueberschreiben, vor dem Verwerfen (Neue Show,
  Show laden), beim Auto-Save; Dialog-Liste; Oeffnen als neue Show laesst
  Original und Sicherung unveraendert;
* das Diagnosepaket nimmt Sicherungen nicht mit.
"""
import datetime
import hashlib
import json
import os
import shutil
import tempfile
import unittest
import uuid
import zipfile
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.show import show_file as SF
from src.core.show import sicherungen as S

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

JETZT = datetime.datetime(2026, 10, 10, 12, 0, 0)


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True, scope="module")
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def daten(tmp_path, monkeypatch):
    """Eigener App-Datenordner je Test."""
    ordner = tmp_path / "LightOS"
    ordner.mkdir()
    monkeypatch.setattr(S, "app_data_dir", lambda: str(ordner))
    yield ordner
    S.warte_bis_fertig()


def _lege_an(show: str, zeit: datetime.datetime, groesse: int = 10,
             anlass: str = S.ANLASS_AUTO) -> str:
    pfad = S.neuer_pfad(show, anlass, zeit)
    with open(pfad, "wb") as f:
        f.write(b"x" * groesse)
    return pfad


def _show_zip(pfad, geraete: int, funktionen: int):
    daten = {"version": "1.2", "patch": [{"fid": i} for i in range(geraete)],
             "functions": {"functions": [{"id": i} for i in range(funktionen)]}}
    with zipfile.ZipFile(pfad, "w") as zf:
        zf.writestr("show.json", json.dumps(daten))


def _hash(pfad) -> str:
    with open(pfad, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ── Aufbewahrung ─────────────────────────────────────────────────────────────

def test_staffelung_mit_injizierter_uhr(daten):
    # heute: alle 5 min von 06:00 bis 11:55 (72 Stueck)
    t = JETZT - datetime.timedelta(minutes=5)
    while t >= JETZT.replace(hour=6, minute=0):
        _lege_an("Abend", t)
        t -= datetime.timedelta(minutes=5)
    # die 20 Tage davor: je 09:00, 15:00, 21:00
    for tage in range(1, 21):
        tag = JETZT - datetime.timedelta(days=tage)
        for stunde in (9, 15, 21):
            _lege_an("Abend", tag.replace(hour=stunde, minute=0))
    assert len(S.liste_sicherungen("Abend")) == 72 + 60

    S.raeume_auf(JETZT)
    bleibt = {e.zeit for e in S.liste_sicherungen("Abend")}

    def am(tage, stunde, minute=0):
        return (JETZT - datetime.timedelta(days=tage)).replace(hour=stunde, minute=minute)

    # die letzten 10
    for i in range(1, 11):
        assert JETZT - datetime.timedelta(minutes=5 * i) in bleibt
    # je Stunde der letzten 24 h die neueste
    for stunde in range(6, 12):
        assert am(0, stunde, 55) in bleibt
    assert am(0, 10, 50) not in bleibt and am(0, 6, 0) not in bleibt
    assert am(1, 21) in bleibt and am(1, 15) in bleibt     # < 24 h alt
    assert am(1, 9) not in bleibt                          # 27 h alt, 21:00 gewinnt
    # je Tag der letzten 14 Tage die neueste
    for tage in range(2, 15):
        assert am(tage, 21) in bleibt
        assert am(tage, 15) not in bleibt and am(tage, 9) not in bleibt
    # aelter als 14 Tage: weg
    for tage in range(15, 21):
        for stunde in (9, 15, 21):
            assert am(tage, stunde) not in bleibt
    assert len(bleibt) == 30


def test_auto_saves_verdraengen_keine_anlass_sicherung(daten):
    """Review: der Stand vor einem Ueberschreiben/Verwerfen darf nicht nach
    zehn Auto-Saves derselben Stunde verschwinden."""
    start = JETZT.replace(minute=0, second=0)
    vor_speichern = _lege_an("Abend", start, anlass=S.ANLASS_VOR_SPEICHERN)
    vor_verwerfen = _lege_an("Abend", start + datetime.timedelta(seconds=30),
                             anlass=S.ANLASS_VOR_VERWERFEN)
    for i in range(1, 13):
        _lege_an("Abend", start + datetime.timedelta(minutes=i))
    S.raeume_auf(start + datetime.timedelta(minutes=13))
    pfade = {e.pfad for e in S.liste_sicherungen("Abend")}
    assert vor_speichern in pfade and vor_verwerfen in pfade
    assert len([e for e in S.liste_sicherungen("Abend")
                if e.anlass == S.ANLASS_AUTO]) == S.BEHALTE_LETZTE


def test_staffelung_je_show_getrennt(daten):
    for i in range(15):
        _lege_an("A", JETZT - datetime.timedelta(seconds=i + 1))
        _lege_an("B", JETZT - datetime.timedelta(seconds=i + 1))
    S.raeume_auf(JETZT)
    assert len(S.liste_sicherungen("A")) == S.BEHALTE_LETZTE
    assert len(S.liste_sicherungen("B")) == S.BEHALTE_LETZTE
    assert len(S.liste_sicherungen()) == 2 * S.BEHALTE_LETZTE


def test_groessengrenze_loescht_aelteste_zuerst(daten):
    pfade = [_lege_an("Gross", JETZT - datetime.timedelta(days=t), groesse=1000)
             for t in range(5)]                          # pfade[0] = neueste
    geloescht = S.raeume_auf(JETZT, max_bytes=2500)
    assert sorted(geloescht) == sorted(pfade[2:])
    assert [e.pfad for e in S.liste_sicherungen()] == pfade[:2]
    # die neueste bleibt auch dann, wenn sie allein die Grenze sprengt
    S.raeume_auf(JETZT, max_bytes=10)
    assert [e.pfad for e in S.liste_sicherungen()] == pfade[:1]


def test_standardgrenzen():
    assert (S.BEHALTE_LETZTE, S.STUNDEN, S.TAGE) == (10, 24, 14)
    assert S.MAX_GESAMT_BYTES == 500 * 1024 * 1024


def test_reste_einer_alten_sitzung(daten):
    """Ein eingefrorener Link ohne Kopie (Programm vorher beendet) wird zur
    Sicherung; eine halbe Temp-Kopie verschwindet; fremde Temp-Dateien (die von
    ``save_show``) bleiben unangetastet."""
    ziel = S.neuer_pfad("Rest", S.ANLASS_AUTO, JETZT)
    with open(ziel + ".stufe", "wb") as f:
        f.write(b"alt")
    halb = S.neuer_pfad("Rest", S.ANLASS_AUTO, JETZT - datetime.timedelta(minutes=1))
    with open(halb + ".tmp", "wb") as f:
        f.write(b"halb")
    fremd = os.path.join(S.sicherungs_dir(), ".show-abc.lshow.tmp")
    with open(fremd, "wb") as f:
        f.write(b"gehoert save_show")
    S.raeume_auf(JETZT)
    assert sorted(os.listdir(S.sicherungs_dir())) == sorted(
        [os.path.basename(ziel), os.path.basename(fremd)])
    with open(ziel, "rb") as f:
        assert f.read() == b"alt"


# ── Schreiben ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hardlinks", [True, False])
def test_sicherung_haelt_den_stand_vor_dem_ersetzen(daten, tmp_path, monkeypatch, hardlinks):
    if not hardlinks:
        def _kein_link(*a, **k):
            raise OSError("Dateisystem kann keine Hardlinks")
        monkeypatch.setattr(S.os, "link", _kein_link)
    quelle = tmp_path / "Meine Show.lshow"
    quelle.write_bytes(b"ALTER STAND")
    ziel = S.sichere_datei(str(quelle), "Meine Show", S.ANLASS_VOR_SPEICHERN, JETZT)
    # so speichert LightOS: neue Datei, per os.replace ueber die alte
    neu = tmp_path / "neu.tmp"
    neu.write_bytes(b"NEUER STAND")
    os.replace(neu, quelle)
    assert S.warte_bis_fertig()

    assert os.path.dirname(ziel) == str(daten / "sicherungen")
    assert os.path.basename(ziel) == "Meine Show__20261010-120000__vor-speichern.lshow"
    with open(ziel, "rb") as f:
        assert f.read() == b"ALTER STAND"
    assert quelle.read_bytes() == b"NEUER STAND"
    # atomar: keine Temp-/Stufen-Reste; eigenstaendige Datei (kein Hardlink mehr)
    assert os.listdir(daten / "sicherungen") == [os.path.basename(ziel)]
    assert os.stat(ziel).st_nlink == 1
    (e,) = S.liste_sicherungen("Meine Show")
    assert (e.zeit, e.anlass, e.groesse) == (JETZT, S.ANLASS_VOR_SPEICHERN, 11)


def test_link_ist_die_sicherung_die_quelle_wird_nie_gelesen(daten, tmp_path, monkeypatch):
    """Review-Punkt Windows: las der Hintergrund-Thread den Hardlink, hielt er
    einen Zugriff auf DIESELBE Datei wie die Show offen — ``os.replace`` der
    Show scheitert dann unter Windows. Der Link selbst ist die Sicherung; es
    wird weder kopiert noch geoeffnet."""
    def _nie(*a, **k):
        raise AssertionError("die Quelle/der Link darf nicht gelesen werden")
    monkeypatch.setattr(S.shutil, "copyfile", _nie)
    quelle = tmp_path / "Meine Show.lshow"
    quelle.write_bytes(b"ALTER STAND")
    ziel = S.sichere_datei(str(quelle), "Meine Show", S.ANLASS_VOR_SPEICHERN, JETZT)
    # sofort da — nicht erst, wenn ein Hintergrund-Auftrag durch ist
    assert ziel and os.path.isfile(ziel)
    assert os.path.samefile(ziel, quelle)
    neu = tmp_path / "neu.tmp"
    neu.write_bytes(b"NEUER STAND")
    os.replace(neu, quelle)                 # darf sofort folgen
    with open(ziel, "rb") as f:
        assert f.read() == b"ALTER STAND"
    assert os.stat(ziel).st_nlink == 1
    assert S.warte_bis_fertig()
    assert os.listdir(daten / "sicherungen") == [os.path.basename(ziel)]


def test_kopie_ohne_hardlink_wird_bei_gesperrter_quelle_wiederholt(
        daten, tmp_path, monkeypatch):
    def _kein_link(*a, **k):
        raise OSError("Dateisystem kann keine Hardlinks")
    monkeypatch.setattr(S.os, "link", _kein_link)
    monkeypatch.setattr(S, "KOPIER_PAUSE_S", 0.0)
    echt, versuche = shutil.copyfile, []

    def _gesperrt(q, z, *a, **k):
        versuche.append(q)
        if len(versuche) < 3:
            raise PermissionError(13, "wird von einem anderen Prozess verwendet")
        return echt(q, z, *a, **k)
    monkeypatch.setattr(S.shutil, "copyfile", _gesperrt)
    quelle = tmp_path / "Meine Show.lshow"
    quelle.write_bytes(b"ALTER STAND")
    ziel = S.sichere_datei(str(quelle), "Meine Show", S.ANLASS_AUTO, JETZT)
    assert len(versuche) == 3
    with open(ziel, "rb") as f:
        assert f.read() == b"ALTER STAND"
    assert S.warte_bis_fertig()
    assert os.listdir(daten / "sicherungen") == [os.path.basename(ziel)]

    # dauerhaft gesperrt: kein Wurf, kein Rest, nur ein Logeintrag
    versuche.clear()
    monkeypatch.setattr(S.shutil, "copyfile",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError(13, "zu")))
    assert S.sichere_datei(str(quelle), "Meine Show", S.ANLASS_AUTO,
                           JETZT + datetime.timedelta(minutes=1)) is None
    assert os.listdir(daten / "sicherungen") == [os.path.basename(ziel)]


def _zwoelf_alte(show="Alt"):
    """Zwoelf Anlass-Sicherungen, alle aelter als die Tages-Staffel: die
    Staffelung behaelt nur die zehn neuesten."""
    basis = JETZT - datetime.timedelta(days=60)
    return [_lege_an(show, basis - datetime.timedelta(days=i),
                     anlass=S.ANLASS_VOR_SPEICHERN) for i in range(12)]


def test_angehaltenes_aufraeumen_loescht_nichts_und_wird_nachgeholt(daten):
    pfade = _zwoelf_alte()
    assert not S.aufraeumen_ist_angehalten()
    with S.aufraeumen_angehalten():
        with S.aufraeumen_angehalten():                 # schachtelbar
            assert S.raeume_auf(JETZT) == []
        assert S.aufraeumen_ist_angehalten()
        assert S.raeume_auf(JETZT, max_bytes=1) == []   # auch die Groessengrenze
        assert S.warte_bis_fertig()
        assert all(os.path.isfile(p) for p in pfade)
    assert not S.aufraeumen_ist_angehalten()
    assert S.warte_bis_fertig()                         # nachgeholt
    assert [os.path.isfile(p) for p in pfade] == [True] * 10 + [False] * 2


def test_schon_laufender_durchgang_loescht_nach_dem_anhalten_nichts_mehr(
        daten, monkeypatch):
    """Die Pause greift am Loeschen selbst — ein Durchgang, der seine Liste
    schon berechnet hat, verliert das Rennen gegen ``aufraeumen_angehalten``."""
    pfade = _zwoelf_alte()
    echt = S.zu_behalten
    mitten_drin = []

    def _haelt_an(eintraege, jetzt):
        behalten = echt(eintraege, jetzt)
        halter = S.aufraeumen_angehalten()
        halter.__enter__()                  # Dialog geht JETZT auf
        mitten_drin.append(halter)
        return behalten
    monkeypatch.setattr(S, "zu_behalten", _haelt_an)
    assert S.raeume_auf(JETZT) == []
    assert all(os.path.isfile(p) for p in pfade)
    monkeypatch.setattr(S, "zu_behalten", echt)
    mitten_drin[0].__exit__(None, None, None)
    assert S.warte_bis_fertig()
    assert sum(os.path.isfile(p) for p in pfade) == 10


def test_ohne_pause_bleibt_das_aufraeumen_wie_es_war(daten):
    pfade = _zwoelf_alte()
    assert sorted(S.raeume_auf(JETZT)) == sorted(pfade[10:])


def test_gleiche_sekunde_ueberschreibt_nichts(daten, tmp_path):
    quelle = tmp_path / "a.lshow"
    quelle.write_bytes(b"eins")
    p1 = S.sichere_datei(str(quelle), "a", S.ANLASS_AUTO, JETZT)
    quelle.write_bytes(b"zwei")
    p2 = S.sichere_datei(str(quelle), "a", S.ANLASS_AUTO, JETZT)
    S.warte_bis_fertig()
    assert p1 != p2 and len(S.liste_sicherungen("a")) == 2


def test_showname_wird_dateinamen_tauglich(daten, tmp_path):
    quelle = tmp_path / "q.lshow"
    quelle.write_bytes(b"x")
    ziel = S.sichere_datei(str(quelle), "Fest/Saal: A__B?", S.ANLASS_AUTO, JETZT)
    S.warte_bis_fertig()
    assert os.path.dirname(ziel) == S.sicherungs_dir()
    (e,) = S.liste_sicherungen("Fest/Saal: A__B?")
    assert e.show == "Fest_Saal_ A_B"


def test_schreibfehler_wirft_nicht_und_wird_geloggt(tmp_path, monkeypatch):
    """Der Sicherungsordner laesst sich nicht anlegen (dort liegt eine Datei)."""
    ordner = tmp_path / "LightOS"
    ordner.mkdir()
    (ordner / "sicherungen").write_bytes(b"keine Mappe")
    monkeypatch.setattr(S, "app_data_dir", lambda: str(ordner))
    meldungen = []
    from src.core import diagnose_log
    monkeypatch.setattr(diagnose_log, "melde_still",
                        lambda tag, exc=None, text="": meldungen.append((tag, exc)))
    quelle = tmp_path / "q.lshow"
    quelle.write_bytes(b"x")
    assert S.sichere_datei(str(quelle), "q", S.ANLASS_AUTO, JETZT) is None
    assert S.sichere_stand(lambda p: None, "q", S.ANLASS_VOR_VERWERFEN, JETZT) is None

    def _kaputt(pfad):
        raise OSError("Datentraeger voll")
    (ordner / "sicherungen").unlink()
    assert S.sichere_stand(_kaputt, "q", S.ANLASS_VOR_VERWERFEN, JETZT) is None
    assert S.raeume_auf(JETZT, ordner=str(tmp_path / "gibtsnicht")) == []
    assert [m[0] for m in meldungen] == ["sicherung"] * 3
    assert quelle.read_bytes() == b"x"


def test_kurzinfo_liest_ohne_zu_laden(daten, tmp_path):
    gut = tmp_path / "gut.lshow"
    _show_zip(gut, geraete=3, funktionen=2)
    with mock.patch.object(SF, "load_show", side_effect=AssertionError("geladen")):
        assert S.kurzinfo(str(gut)) == "3 Geräte · 2 Funktionen"
    kaputt = tmp_path / "kaputt.lshow"
    kaputt.write_bytes(b"kein zip")
    assert S.kurzinfo(str(kaputt)) == "nicht lesbar"


# ── Diagnosepaket ────────────────────────────────────────────────────────────

def test_diagnosepaket_nimmt_keine_sicherungen_mit(daten, tmp_path, monkeypatch):
    from src.core import diagnose_log as d
    (daten / "logs").mkdir()
    (daten / "logs" / "lightos.log").write_text("12:00:00.000   start\n", encoding="utf-8")
    quelle = tmp_path / "Geheime Hochzeit.lshow"
    _show_zip(quelle, 1, 1)
    S.sichere_datei(str(quelle), "Geheime Hochzeit", S.ANLASS_AUTO, JETZT)
    S.warte_bis_fertig()
    assert len(S.liste_sicherungen("Geheime Hochzeit")) == 1
    monkeypatch.setattr(d, "app_data_dir", lambda: str(daten))
    monkeypatch.setattr(d, "crash_log_path", lambda: str(daten / "crash.log"))
    monkeypatch.setenv("LIGHTOS_LOG_DIR", str(daten / "logs"))

    ziel = d.erstelle_diagnosepaket(str(tmp_path / "paket.zip"), "1.0.0")
    with zipfile.ZipFile(ziel) as zf:
        namen = zf.namelist()
        alles = "\n".join(zf.read(n).decode("utf-8") for n in namen)
    assert "logs/lightos.log" in namen
    assert not [n for n in namen if n.endswith(".lshow") or "sicherung" in n.lower()]
    assert "Geheime Hochzeit" not in alles and "show.json" not in alles
    assert "Sicherungen" in d.PAKET_INHALT.split("NICHT enthalten")[1]


# ── Hauptfenster ─────────────────────────────────────────────────────────────

class HauptfensterSicherungenTest(unittest.TestCase):
    """Ein Hauptfenster fuer alle Tests (der Bau ist teuer); je Test ein
    frischer App-Datenordner fuer die Sicherungen und eine frisch geoeffnete
    Show mit einer Cueliste."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.core.app_state import get_state
        from src.ui import main_window as mw
        cls.mw = mw
        cls.state = get_state()
        SF.reset_show()
        cls.win = mw.MainWindow()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        SF.reset_show()
        cls.app.processEvents()

    def setUp(self):
        from src.core.engine.cue_stack import CueStack
        self._tmp = tempfile.TemporaryDirectory(prefix="stab32_")
        self.addCleanup(self._tmp.cleanup)
        self.ordner = os.path.join(self._tmp.name, "LightOS")
        os.makedirs(self.ordner)
        p = mock.patch.object(S, "app_data_dir", lambda: self.ordner)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(S.warte_bis_fertig)     # laeuft VOR p.stop (LIFO)
        for name, wert in (("_add_recent_file", lambda *a: None),
                           ("_load_recent_files", lambda: [])):
            p = mock.patch.object(self.mw, name, wert)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(self.mw.QMessageBox, "warning", lambda *a, **k: None)
        p.start()
        self.addCleanup(p.stop)

        SF.reset_show()
        self.state.cue_stacks.append(CueStack("Erster Stand"))
        self.pfad = os.path.join(self._tmp.name, "Sommerfest.lshow")
        SF.save_show(self.pfad)
        self.win._open_show_path(self.pfad)
        self.app.processEvents()
        self.app.processEvents()
        self.assertFalse(self.win._has_unsaved_changes(), "Vorbedingung")

    def _aendern(self, name="Zweiter Stand"):
        from src.core.engine.cue_stack import CueStack
        self.state.cue_stacks.append(CueStack(name))
        self.assertTrue(self.win._has_unsaved_changes(), "Vorbedingung")

    def _cuelisten(self, pfad) -> list:
        with zipfile.ZipFile(pfad) as zf:
            daten = json.loads(zf.read("show.json").decode("utf-8"))
        return [s.get("name") for s in daten.get("cue_stacks", [])]

    def _sicherungen(self, show="Sommerfest"):
        S.warte_bis_fertig()
        return S.liste_sicherungen(show)

    # -- Menue ----------------------------------------------------------------

    def test_menue_datei_hat_aeltere_version(self):
        from PySide6.QtGui import QAction
        treffer = [a for a in self.win.menuBar().findChildren(QAction)
                   if a.text() == "Ältere Version öffnen…"]
        self.assertEqual(1, len(treffer))
        from src.ui.widgets import sicherungen_dialog as D
        offen = []
        with mock.patch.object(D.SicherungenDialog, "exec",
                               lambda dlg: offen.append(dlg) or D.QDialog.DialogCode.Rejected):
            treffer[0].trigger()
        self.assertEqual(1, len(offen), "der Menuepunkt oeffnet den Dialog")

    # -- Anlaesse -------------------------------------------------------------

    def test_sicherung_vor_dem_ueberschreiben(self):
        vorher = _hash(self.pfad)
        self._aendern()
        self.assertTrue(self.win._do_save(self.pfad))
        (e,) = self._sicherungen()
        self.assertEqual(S.ANLASS_VOR_SPEICHERN, e.anlass)
        self.assertEqual(vorher, _hash(e.pfad), "Sicherung = Stand VOR dem Speichern")
        self.assertEqual(["Erster Stand"], self._cuelisten(e.pfad))
        self.assertEqual(["Erster Stand", "Zweiter Stand"], self._cuelisten(self.pfad))

    def test_erstes_speichern_in_neue_datei_sichert_nichts(self):
        neu = os.path.join(self._tmp.name, "Ganz neu.lshow")
        self.assertTrue(self.win._do_save(neu))
        self.assertEqual([], self._sicherungen("Ganz neu"))
        self.assertEqual([], self._sicherungen())

    def _verwerfen(self, aktion):
        with mock.patch.object(self.mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(self.mw.QMessageBox, "question",
                               lambda *a, **k: QMessageBox.StandardButton.Discard):
            aktion()
        self.app.processEvents()

    def test_neue_show_sichert_verworfene_aenderungen(self):
        self._aendern()
        self._verwerfen(self.win._new_show)
        self.assertEqual([], [s.name for s in self.state.cue_stacks], "Show geleert")
        (e,) = self._sicherungen()
        self.assertEqual(S.ANLASS_VOR_VERWERFEN, e.anlass)
        self.assertEqual(["Erster Stand", "Zweiter Stand"], self._cuelisten(e.pfad))
        self.assertEqual(["Erster Stand"], self._cuelisten(self.pfad),
                         "die Show-Datei selbst bleibt beim Verwerfen unberuehrt")

    def test_show_laden_sichert_verworfene_aenderungen(self):
        andere = os.path.join(self._tmp.name, "Andere.lshow")
        SF.save_show(andere)
        self._aendern("Nur im Speicher")
        self._verwerfen(lambda: self.win._open_show_nach_rueckfrage(andere))
        self.assertEqual(andere, self.win._current_show_path)
        (e,) = self._sicherungen()
        self.assertEqual(S.ANLASS_VOR_VERWERFEN, e.anlass)
        self.assertIn("Nur im Speicher", self._cuelisten(e.pfad))

    def test_ohne_aenderungen_keine_sicherung_beim_wechsel(self):
        with mock.patch.object(self.mw.QMessageBox, "question",
                               lambda *a, **k: QMessageBox.StandardButton.Yes):
            self.win._new_show()
        self.assertEqual([], self._sicherungen())

    def test_abbrechen_sichert_nichts(self):
        self._aendern()
        with mock.patch.object(self.mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(self.mw.QMessageBox, "question",
                               lambda *a, **k: QMessageBox.StandardButton.Cancel):
            self.win._new_show()
        self.assertEqual([], self._sicherungen())
        self.assertEqual(2, len(self.state.cue_stacks), "Show blieb offen")

    def test_auto_save_legt_zusaetzlich_eine_version_ab(self):
        auto = os.path.join(self.ordner, "auto_save.lshow")
        self._aendern()
        self.win._autosave_dirty = True
        with mock.patch.object(self.win, "_autosave_path", lambda: auto):
            self.win._do_autosave()
        self.assertTrue(os.path.isfile(auto), "Absturz-Wiederherstellung braucht die Datei")
        (e,) = self._sicherungen()
        self.assertEqual(S.ANLASS_AUTO, e.anlass)
        self.assertEqual(_hash(auto), _hash(e.pfad))
        self.assertTrue(self.win._has_unsaved_changes(),
                        "Auto-Save gilt weiterhin nicht als Speichern")

    def test_schreibfehler_blockiert_das_speichern_nicht(self):
        with open(os.path.join(self.ordner, "sicherungen"), "wb") as f:
            f.write(b"keine Mappe")
        self._aendern()
        self.assertTrue(self.win._do_save(self.pfad), "Speichern muss trotzdem klappen")
        self.assertEqual(["Erster Stand", "Zweiter Stand"], self._cuelisten(self.pfad))
        self.assertFalse(self.win._has_unsaved_changes())
        # … und das Verwerfen ebenso wenig
        self._aendern("Dritter")
        self._verwerfen(self.win._new_show)
        self.assertEqual([], [s.name for s in self.state.cue_stacks])

    # -- Dialog ---------------------------------------------------------------

    def _drei_versionen(self):
        """Zwei Versionen von „Sommerfest", eine einer anderen Show."""
        alt = os.path.join(self._tmp.name, "alt.lshow")
        _show_zip(alt, geraete=4, funktionen=7)
        S.sichere_datei(alt, "Sommerfest", S.ANLASS_AUTO,
                        datetime.datetime(2026, 10, 9, 20, 15, 0))
        S.sichere_datei(self.pfad, "Sommerfest", S.ANLASS_VOR_SPEICHERN,
                        datetime.datetime(2026, 10, 10, 8, 30, 0))
        S.sichere_datei(alt, "Winterball", S.ANLASS_AUTO,
                        datetime.datetime(2026, 10, 10, 9, 0, 0))
        S.warte_bis_fertig()

    def test_dialog_listet_die_versionen_der_aktuellen_show(self):
        from src.ui.widgets.sicherungen_dialog import SicherungenDialog, groesse_text
        self._drei_versionen()
        self.assertEqual("Sommerfest", self.win._sicherungs_name())
        dlg = SicherungenDialog(self.win._sicherungs_name(), self.win)
        try:
            dlg.kurzinfos_fertig_laden()
            zeilen = dlg.zeilen_text()
            self.assertEqual(
                [["10.10.2026 08:30", "Sommerfest", "vor dem Überschreiben",
                  groesse_text(os.path.getsize(self.pfad)), "0 Geräte · 0 Funktionen"],
                 ["09.10.2026 20:15", "Sommerfest", "Auto-Save",
                  zeilen[1][3], "4 Geräte · 7 Funktionen"]], zeilen)
            self.assertRegex(zeilen[1][3], r"^\d+(,\d)? (KB|MB)$")
            self.assertEqual(dlg.eintraege()[0], dlg.auswahl(), "neueste vorgewaehlt")
            # optional: alle Shows
            dlg._alle.setChecked(True)
            dlg.kurzinfos_fertig_laden()
            self.assertEqual(["Winterball", "Sommerfest", "Sommerfest"],
                             [z[1] for z in dlg.zeilen_text()])
            dlg.waehle(2)
            self.assertEqual("09.10.2026 20:15", dlg.auswahl().zeit_text)
        finally:
            dlg.deleteLater()

    def test_dialog_ohne_sicherungen(self):
        from src.ui.widgets.sicherungen_dialog import SicherungenDialog
        dlg = SicherungenDialog("Sommerfest", self.win)
        try:
            self.assertEqual([], dlg.zeilen_text())
            self.assertIsNone(dlg.auswahl())
        finally:
            dlg.deleteLater()

    # -- Oeffnen --------------------------------------------------------------

    def test_oeffnen_als_neue_show_laesst_original_und_sicherung_unveraendert(self):
        self._aendern()
        self.assertTrue(self.win._do_save(self.pfad))       # Datei: 2 Cuelisten
        (e,) = self._sicherungen()                          # Sicherung: 1 Cueliste
        original, sicherung = _hash(self.pfad), _hash(e.pfad)
        zuletzt = []
        with mock.patch.object(self.mw, "_add_recent_file", zuletzt.append):
            self.win._oeffne_sicherung(e)
        self.app.processEvents()

        self.assertEqual(["Erster Stand"], [s.name for s in self.state.cue_stacks],
                         "der aeltere Stand ist geladen")
        self.assertIsNone(self.win._current_show_path, "neue, ungespeicherte Show")
        self.assertEqual(f"LightOS  -  Sommerfest (Sicherung vom {e.zeit_text})",
                         self.win.windowTitle())
        self.assertTrue(self.win._has_unsaved_changes())
        self.assertEqual([], zuletzt, "Sicherung gehoert nicht in die Zuletzt-Liste")
        self.assertEqual("Sommerfest", self.win._sicherungs_name())

        # Strg+S fragt nach einem Ziel, statt Original oder Sicherung zu treffen
        dialoge = []

        def _unter(*a, **k):
            dialoge.append(a)
            return ("", "")
        with mock.patch.object(self.mw.QFileDialog, "getSaveFileName", _unter):
            self.assertFalse(self.win._save_show())
        self.assertEqual(1, len(dialoge))
        self.assertEqual(original, _hash(self.pfad))
        self.assertEqual(sicherung, _hash(e.pfad))
        self.assertEqual([e], self._sicherungen(), "Oeffnen legt keine Sicherung an")

        # unter neuem Namen gespeichert -> normale Show
        ziel = os.path.join(self._tmp.name, "Sommerfest alt.lshow")
        with mock.patch.object(self.mw.QFileDialog, "getSaveFileName",
                               lambda *a, **k: (ziel, "")):
            self.assertTrue(self.win._save_show())
        self.assertEqual(ziel, self.win._current_show_path)
        self.assertFalse(self.win._has_unsaved_changes())
        self.assertEqual(original, _hash(self.pfad))
        self.assertEqual(sicherung, _hash(e.pfad))

    # -- Gewaehlte Version gegen das Aufraeumen geschuetzt ----------------------

    def _zehn_alte_versionen(self):
        """Zehn Anlass-Sicherungen von „Sommerfest" (je 1 Cueliste), alle
        aelter als die Tages-Staffel: die AELTESTE ist die zehnte — die
        naechste neue Anlass-Sicherung schiebt genau sie hinaus."""
        basis = datetime.datetime.now() - datetime.timedelta(days=40)
        for i in range(10):
            ziel = S.neuer_pfad("Sommerfest", S.ANLASS_VOR_SPEICHERN,
                                basis - datetime.timedelta(days=i))
            shutil.copyfile(self.pfad, ziel)
        alle = S.liste_sicherungen("Sommerfest")
        self.assertEqual(10, len(alle))
        self.assertEqual([], S.raeume_auf(), "Vorbedingung: noch alle in der Staffel")
        return alle[-1]

    def _oeffne_nach_dem_hintergrund(self, aktion):
        """``aktion`` ausfuehren; das Laden wartet vorher, bis der
        Hintergrund-Thread durch ist — so trifft das Rennen sicher ein."""
        echt = self.win._open_show_path
        beim_laden = []

        def _spaet(path, *a, **k):
            S.warte_bis_fertig()
            beim_laden.append(os.path.isfile(path))
            return echt(path, *a, **k)
        with mock.patch.object(self.win, "_open_show_path", _spaet):
            aktion()
        self.app.processEvents()
        return beim_laden

    def test_verwerfen_loescht_die_gewaehlte_version_nicht(self):
        """Codex-Befund (P1): „Verwerfen" legt eine neue Sicherung an; deren
        Aufraeumen loeschte die gewaehlte (zehnte) Version, bevor sie geladen
        war."""
        for name, unterdrueckt, antwort in (
                ("Verwerfen", False, QMessageBox.StandardButton.Discard),
                ("ohne Rueckfrage", True, None)):
            with self.subTest(name):
                self.setUp()
                wahl = self._zehn_alte_versionen()
                self._aendern()
                with mock.patch.object(self.mw, "_exit_prompt_suppressed",
                                       lambda: unterdrueckt), \
                     mock.patch.object(self.mw.QMessageBox, "question",
                                       lambda *a, **k: antwort):
                    beim_laden = self._oeffne_nach_dem_hintergrund(
                        lambda: self.win._oeffne_sicherung(wahl))
                self.assertEqual([True], beim_laden,
                                 "gewaehlte Sicherung vor dem Laden geloescht")
                self.assertEqual(["Erster Stand"],
                                 [s.name for s in self.state.cue_stacks],
                                 "die gewaehlte aeltere Version ist geladen")
                self.assertIn("Sicherung vom", self.win.windowTitle())
                # der verworfene Stand liegt als neueste Version da
                neueste = self._sicherungen()[0]
                self.assertEqual(S.ANLASS_VOR_VERWERFEN, neueste.anlass)
                self.assertEqual(["Erster Stand", "Zweiter Stand"],
                                 self._cuelisten(neueste.pfad))
                self.assertFalse(S.aufraeumen_ist_angehalten())

    def test_speichern_vor_dem_oeffnen_loescht_die_gewaehlte_version_nicht(self):
        wahl = self._zehn_alte_versionen()
        self._aendern()
        with mock.patch.object(self.mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(self.mw.QMessageBox, "question",
                               lambda *a, **k: QMessageBox.StandardButton.Save):
            beim_laden = self._oeffne_nach_dem_hintergrund(
                lambda: self.win._oeffne_sicherung(wahl))
        self.assertEqual([True], beim_laden)
        self.assertEqual(["Erster Stand"], [s.name for s in self.state.cue_stacks])
        self.assertEqual(["Erster Stand", "Zweiter Stand"], self._cuelisten(self.pfad))

    def test_auto_save_bei_offenem_dialog_loescht_keine_gelistete_version(self):
        from src.ui.widgets import sicherungen_dialog as D
        wahl = self._zehn_alte_versionen()
        auto = os.path.join(self.ordner, "auto_save.lshow")
        gesehen = []

        def _dialog_laeuft(dlg):
            # waehrend der Dialog offen ist: eine neue Anlass-Sicherung + Aufraeumen
            S.sichere_datei(self.pfad, "Sommerfest", S.ANLASS_VOR_SPEICHERN)
            self.win._autosave_dirty = True
            with mock.patch.object(self.win, "_autosave_path", lambda: auto):
                self.win._do_autosave()
            S.warte_bis_fertig()
            gesehen.append(S.aufraeumen_ist_angehalten())
            dlg.waehle(len(dlg.eintraege()) - 1)
            self.assertEqual(wahl.pfad, dlg.auswahl().pfad)
            return D.QDialog.DialogCode.Accepted
        with mock.patch.object(D.SicherungenDialog, "exec", _dialog_laeuft):
            beim_laden = self._oeffne_nach_dem_hintergrund(
                self.win._aeltere_version_oeffnen)
        self.assertEqual([True], gesehen)
        self.assertEqual([True], beim_laden)
        self.assertIn("Sicherung vom", self.win.windowTitle())
        self.assertFalse(S.aufraeumen_ist_angehalten())
        S.warte_bis_fertig()
        self.assertFalse(os.path.isfile(wahl.pfad),
                         "nach dem Laden wird das Aufraeumen nachgeholt")

    def test_fehlende_sicherung_laesst_die_offene_show_unveraendert(self):
        """Ist die gewaehlte Datei doch weg (von Hand geloescht), wird die
        offene Show weder zum Verwerfen angeboten noch geleert."""
        self._drei_versionen()
        wahl = S.liste_sicherungen("Sommerfest")[0]
        os.remove(wahl.pfad)
        self._aendern()
        vorher = self._sicherungen()
        fragen, warnungen = [], []
        with mock.patch.object(self.mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(self.mw.QMessageBox, "question",
                               lambda *a, **k: fragen.append(a) or
                               QMessageBox.StandardButton.Discard), \
             mock.patch.object(self.mw.QMessageBox, "warning",
                               lambda *a, **k: warnungen.append(a[2])):
            self.win._oeffne_sicherung(wahl)
            self.assertEqual([], fragen, "nichts zu verwerfen anbieten")
            self.assertEqual(1, len(warnungen))
            self.assertIn("gibt es nicht mehr", warnungen[0])
            # … und selbst der Ladeversuch auf die fehlende Datei leert nichts
            self.win._open_show_path(wahl.pfad, sicherung=wahl)
            self.assertEqual(2, len(warnungen))
        self.assertEqual(["Erster Stand", "Zweiter Stand"],
                         [s.name for s in self.state.cue_stacks])
        self.assertEqual(self.pfad, self.win._current_show_path)
        self.assertTrue(self.win._has_unsaved_changes())
        self.assertEqual(vorher, self._sicherungen(), "keine Sicherung angelegt")

    def test_menuepunkt_oeffnet_die_auswahl(self):
        from src.ui.widgets import sicherungen_dialog as D
        self._drei_versionen()
        with mock.patch.object(D.SicherungenDialog, "exec",
                               lambda dlg: D.QDialog.DialogCode.Accepted):
            self.win._aeltere_version_oeffnen()
        self.app.processEvents()
        self.assertEqual("LightOS  -  Sommerfest (Sicherung vom 10.10.2026 08:30)",
                         self.win.windowTitle())
        self.assertIsNone(self.win._current_show_path)

    def test_rueckfrage_nennt_die_sicherung(self):
        self._drei_versionen()
        self.win._oeffne_sicherung(S.liste_sicherungen("Sommerfest")[0])
        fragen = []

        def _abbrechen(*a, **k):
            fragen.append(a[2])
            return QMessageBox.StandardButton.Cancel
        with mock.patch.object(self.mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(self.mw.QMessageBox, "question", _abbrechen):
            self.win._new_show()
        self.assertEqual(1, len(fragen))
        self.assertIn("aus einer Sicherung", fragen[0])
