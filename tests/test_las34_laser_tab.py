"""LAS-34 — der neue Laser-Tab im Programmer (Entwurf „Tab A“).

Statt grosser Kaesten und einer Reglerliste stehen BAUSTEINE da, sobald das
Geraeteprofil Laser-Angaben macht (LAS-33): Sicherheitsleiste, Betriebsart als
Umschalter, Vorschau & Position, Muster-Galerie, Farbfelder, Regler mit
sprechenden Enden, gemerkte Muster. Geprueft wird je Baustein:

* er schreibt ueber den bisherigen Programmer-Weg, und zwar BYTEGLEICH zu dem,
  was die alte Bedienung bei gleicher Wahl schrieb;
* er faellt EINZELN auf die bisherige Bedienung zurueck, wenn das Profil dafuer
  nichts liefert oder die gewaehlten Laser sich unterscheiden;
* kein Kanal geht verloren — ueber alle Laser-Profile der Bibliothek.

Laser-Sicherheit: der NOT-AUS der Leiste geht denselben Weg wie bisher.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel  # noqa: E402

EL400_DATEI = ROOT / "fixtures" / "bibliothek" / "laserworld" / "el-400rgb-mk2.json"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ── Attrappen: Kanaele, Geraet, State ───────────────────────────────────────

class _Rng:
    def __init__(self, lo, hi, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = lo, hi, name, kind


class _Ch:
    def __init__(self, attr, num, ranges=None, name="", laser=None, default=0):
        self.attribute = attr
        self.channel_number = num
        self.ranges = ranges or []
        self.name = name or attr
        self.laser = laser
        self.default_value = default


def _el400(ohne=()) -> list:
    """Die Kanaele des EL-400RGB MK2 aus der Bibliotheksdatei. ``ohne`` =
    Attribute, deren Laser-Angaben entfallen (``"*"`` = alle)."""
    modus = json.loads(EL400_DATEI.read_text(encoding="utf-8"))["modi"][0]
    out = []
    for i, k in enumerate(modus["kanaele"], start=1):
        laser = copy.deepcopy(k.get("laser"))
        if "*" in ohne or k["attribut"] in ohne:
            laser = None
        out.append(_Ch(
            k["attribut"], i,
            [_Rng(b["von"], b["bis"], b["name"], b.get("art", ""))
             for b in k.get("bereiche", ())],
            k["name"], laser, int(k.get("default", 0) or 0)))
    return out


class _FX:
    def __init__(self, fid, chans, name="EL-400RGB MK2", protocol="dmx"):
        self.fid = fid
        self.label = self.fixture_name = self.name = name
        self.fixture_type = "laser"
        self.universe = 1
        self.address = 1 + 20 * fid
        self.protocol = protocol
        self.net_host = "10.0.0.9" if protocol != "dmx" else ""
        self._chans = chans


class _LO:
    def __init__(self, state):
        self.state = state
        self.armed = True
        self.rufe = []

    def estop_all(self):
        self.rufe.append("estop_all")
        self.state.laser_estop_active = True

    def set_armed(self, v):
        self.rufe.append(("set_armed", bool(v)))
        self.armed = bool(v)

    def clear_estop_all(self):
        self.rufe.append("clear_estop_all")

    def set_figure(self, fid, figure):
        pass

    def clear_figures(self):
        pass


class _State:
    def __init__(self, fixtures):
        self._fixtures = list(fixtures)
        self.programmer: dict = {}
        self.geschrieben: list = []
        self.laser_estop_active = False
        self.lo = _LO(self)

    def get_patched_fixtures(self):
        return list(self._fixtures)

    def get_selected_fids(self):
        return [f.fid for f in self._fixtures]

    def set_programmer_value(self, fid, attr, value, undoable=False, head=0):
        self.programmer.setdefault(fid, {})[attr] = int(value)
        self.geschrieben.append((fid, attr, int(value)))
        if attr in ("shutter", "gobo_wheel"):       # A3D-02: „wieder an“
            self.laser_estop_active = False

    def get_programmer_value(self, fid, attr, head=0):
        return self.programmer.get(fid, {}).get(attr)

    def ensure_laser_output(self):
        return self.lo


def _view(monkeypatch, fixtures):
    _app()
    import src.core.app_state as A
    import src.ui.views.laser_view as lv
    st = _State(fixtures)
    monkeypatch.setattr(lv, "get_state", lambda: st)
    monkeypatch.setattr(lv, "get_channels_for_patched", lambda f: f._chans)
    monkeypatch.setattr(A, "get_channels_for_patched", lambda f: f._chans,
                        raising=False)
    v = lv.LaserView(follow_selection=False)
    v.refresh_from_selection()
    return v, st


def _betriebsart(v, art):
    seg = next(s for s in v._umschalter.segmente if s.art == art)
    seg.click()
    return seg


# ── (1) Sicherheitsleiste ───────────────────────────────────────────────────

def test_sicherheitsleiste_ist_eine_zeile_ohne_kasten(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    leiste = v._dmx_safety_box
    assert leiste.isVisibleTo(v)
    assert not isinstance(leiste, QGroupBox)
    assert leiste.maximumHeight() <= 48
    titel = [b.title() for b in v.findChildren(QGroupBox) if b.isVisibleTo(v)]
    assert "Laser-Sicherheit" not in titel, titel
    # Der lange Erklaersatz steht nicht mehr dauerhaft auf der Flaeche.
    assert len(v._lbl_dmx_estop.text()) < 30
    assert "Blackout" in v._btn_dmx_estop.toolTip()


def test_zustand_folgt_der_betriebsart(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    assert v._lbl_dmx_estop.text() == "Laser AUS"       # Grundwert 0 = aus
    assert "EL-400RGB MK2" in v._lbl_modell.text()
    assert "1 Laser" in v._lbl_modell.text()
    _betriebsart(v, "statisch")
    assert v._lbl_dmx_estop.text() == "Laser AN"
    _betriebsart(v, "aus")
    assert v._lbl_dmx_estop.text() == "Laser AUS"


def test_zustand_meldet_an_wenn_die_ausgabe_den_laser_einschaltet(monkeypatch):
    """Eine laufende Szene schaltet den Laser ein, der Programmer weiss nichts
    davon: die Leiste darf dann nicht „AUS“ melden."""
    fx = _FX(1, _el400())
    v, st = _view(monkeypatch, [fx])

    class _Ausgabe:
        frame = bytearray(512)

        def get_display_frame(self, universe):
            return bytes(self.frame)

    st.output_manager = _Ausgabe()
    v._update_dmx_estop_label()
    assert v._lbl_dmx_estop.text() == "Laser AUS"
    st.output_manager.frame[fx.address - 1] = 174       # Betriebsart = Kanal 1
    v._update_dmx_estop_label()
    assert v._lbl_dmx_estop.text() == "Laser AN"
    assert st.geschrieben == []                          # nur gelesen
    # Umgekehrt: Programmer an, Ausgabe (noch) dunkel -> im Zweifel „an“.
    st.output_manager.frame[fx.address - 1] = 0
    _betriebsart(v, "statisch")
    assert v._lbl_dmx_estop.text() == "Laser AN"


def test_not_aus_loest_aus_wie_bisher(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    _betriebsart(v, "statisch")
    assert "NOT-AUS" in v._btn_dmx_estop.text()
    v._btn_dmx_estop.click()
    assert st.laser_estop_active is True
    # Reihenfolge der Verriegelung unveraendert: erst verriegeln, dann
    # ausdruecklich entwaffnen, erst danach die Geraete-Verriegelung loesen.
    assert st.lo.rufe == ["estop_all", ("set_armed", False), "clear_estop_all"]
    assert st.lo.armed is False
    assert v._lbl_dmx_estop.text() == "NOT-AUS aktiv"
    assert "Betriebsart oder Muster" in v._lbl_modell.text()
    # Der NOT-AUS schreibt selbst keinen Programmer-Wert.
    assert [g for g in st.geschrieben if g[1] != "shutter"] == []
    # Wieder an: Betriebsart bewusst neu waehlen.
    _betriebsart(v, "statisch")
    assert st.laser_estop_active is False
    assert v._lbl_dmx_estop.text() == "Laser AN"


def test_farbe_oder_lage_loesen_den_not_aus_nicht(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    v._btn_dmx_estop.click()
    v._farbfelder.felder[2].click()
    v._lage_gezogen(0.8, 0.2)
    v._sprech["zoom"].schieber.setValue(40)
    assert st.laser_estop_active is True
    assert v._lbl_dmx_estop.text() == "NOT-AUS aktiv"


def test_sperrzonen_abzeichen_fehlt_ohne_die_funktion(monkeypatch):
    import src.ui.views.laser_view as lv
    monkeypatch.setattr(lv, "SPERRZONEN_MODUL", "src.core.laser.gibt_es_nicht")
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    assert lv.sperrzonen_hinweis(object(), [1]) is None
    assert v._sperrzonen_abzeichen.isHidden()
    # Kein harter Import: die Datei nennt das Modul nur als Text.
    quelle = Path(lv.__file__).read_text(encoding="utf-8")
    assert "import sperrzonen" not in quelle
    assert "from src.core.laser.sperrzonen" not in quelle
    assert "from src.ui.visualizer.sperrzonen_ui" not in quelle


def test_sperrzonen_abzeichen_mit_der_funktion(monkeypatch):
    import src.ui.views.laser_view as lv

    class _Befund:
        def __init__(self, fid, status, text):
            self.fid, self.status, self.text = fid, status, text

    modul = types.ModuleType("las34_sperrzonen_attrappe")
    modul.STATUS_FREI = "frei"
    modul.state_befunde = lambda state: ("Sperrzonen: 1", [
        _Befund(1, "erreicht", "Laser 1: kann Zone „Publikum“ erreichen"),
        _Befund(1, "frei", "Laser 1: erreicht keine Zone"),
        _Befund(7, "erreicht", "Laser 7: kann Zone „Bar“ erreichen")])
    monkeypatch.setitem(sys.modules, "las34_sperrzonen_attrappe", modul)
    monkeypatch.setattr(lv, "SPERRZONEN_MODUL", "las34_sperrzonen_attrappe")
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    abz = v._sperrzonen_abzeichen
    assert not abz.isHidden()
    assert "Sperrzonen: 1 Hinweis" in abz.text()      # nur der gewaehlte Laser
    # Nie wie ein Schutz: „Nur Anzeige“ steht im Abzeichen selbst.
    assert "Nur Anzeige" in abz.text() and "schaltet nicht ab" in abz.text()
    assert "Publikum" in abz.toolTip() and "Bar" not in abz.toolTip()
    # Kaputte Auskunft -> kein Abzeichen, kein Absturz.
    modul.state_befunde = lambda state: 1 / 0
    v.refresh_from_selection()
    assert abz.isHidden()


def test_nur_netzwerk_laser_behaelt_die_scharfschaltung(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400(), protocol="etherdream")])
    assert v._safety_box.isVisibleTo(v)             # Scharf/Unscharf + NOT-AUS
    assert not v._dmx_safety_box.isVisibleTo(v)


# ── (2) Betriebsart ─────────────────────────────────────────────────────────

def test_betriebsart_segmente_mit_unterzeile(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    assert v._seg_box.isVisibleTo(v)
    assert v._mode_box.isHidden()                   # die Kacheln entfallen
    assert [(s.text(), s.unterzeile) for s in v._umschalter.segmente] == [
        ("Aus", "Laser dunkel"),
        ("Musik", "Gerät läuft selbst"),
        ("Auto", "Gerät läuft selbst"),
        ("Statische Muster", "LightOS steuert alles"),
        ("Dynamische Muster", "LightOS steuert, Muster bewegt sich")]
    assert all(s.minimumHeight() >= 36 for s in v._umschalter.segmente)
    # Man sieht, welche laeuft: genau ein Segment ist gewaehlt.
    _betriebsart(v, "auto")
    assert [s.art for s in v._umschalter.segmente if s.isChecked()] == ["auto"]


def test_betriebsart_schreibt_wie_die_bisherigen_kacheln(monkeypatch):
    from src.ui.views.laser_view import _range_value
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    bereiche = _el400()[0].ranges
    assert len(bereiche) == len(v._umschalter.segmente) == 5
    for seg, r in zip(v._umschalter.segmente, bereiche):
        seg.click()
        assert st.programmer[1]["shutter"] == _range_value(r), seg.text()


def test_musik_und_auto_sperren_muster_lage_farbe(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    gesperrt = (v._lage_feld, v._btn_mitte, v._galerie, v._farbfelder)
    _betriebsart(v, "statisch")
    assert all(w.isEnabled() for w in gesperrt)
    assert v._lbl_gesperrt.isHidden()
    for art in ("musik", "auto"):
        _betriebsart(v, art)
        assert not any(w.isEnabled() for w in gesperrt), art
        assert not v._lbl_gesperrt.isHidden(), art
        assert "Gerät läuft selbst" in v._lbl_gesperrt.text()
    # „Aus“ sperrt nicht (man stellt dort vor), „Dynamisch“ auch nicht.
    for art in ("aus", "dynamisch"):
        _betriebsart(v, art)
        assert all(w.isEnabled() for w in gesperrt), art
        assert v._lbl_gesperrt.isHidden()


def test_betriebsart_mit_luecke_bleibt_bei_den_kacheln(monkeypatch):
    """Deckt die Betriebsart-Liste nicht jeden Wertebereich ab, bliebe eine
    Betriebsart unwaehlbar — dann gelten die bisherigen Kacheln."""
    chans = _el400()
    chans[0].laser["betriebsart"] = chans[0].laser["betriebsart"][:3]
    v, _st = _view(monkeypatch, [_FX(1, chans)])
    assert v._seg_box.isHidden()
    assert not v._mode_box.isHidden()
    assert "shutter" in v.bedienbare_attribute()


# ── (3) Vorschau & Position ─────────────────────────────────────────────────

def test_ziehen_schreibt_richtig_herum(monkeypatch):
    """EL-400: beide Achsen laufen umgekehrt (X niedrig = rechts, Y niedrig =
    oben), 0–10 ist die Mittelstellung und gehoert nicht zum Regelweg."""
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    v._lage_gezogen(1.0, 1.0)                       # ganz rechts oben
    assert (st.programmer[1]["laser_x"], st.programmer[1]["laser_y"]) == (11, 11)
    v._lage_gezogen(0.0, 0.0)                       # ganz links unten
    assert (st.programmer[1]["laser_x"], st.programmer[1]["laser_y"]) == (255, 255)
    # Kein Zug schreibt in den Mittelbereich.
    for i in range(0, 101):
        v._lage_gezogen(i / 100.0, 1.0 - i / 100.0)
        assert st.programmer[1]["laser_x"] > 10
        assert st.programmer[1]["laser_y"] > 10


def test_ziehen_mit_der_maus(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    feld = v._lage_feld
    f = feld.feld()
    assert feld.width() >= 200 and feld.height() >= 200     # fingertauglich
    rechts_oben = QPoint(int(f.left() + 0.64 * f.width()),
                         int(f.bottom() - 0.67 * f.height()))
    QTest.mousePress(feld, Qt.MouseButton.LeftButton, pos=rechts_oben)
    QTest.mouseRelease(feld, Qt.MouseButton.LeftButton, pos=rechts_oben)
    x, y = st.programmer[1]["laser_x"], st.programmer[1]["laser_y"]
    assert 11 <= x < 133 and 11 <= y < 133          # rechts / oben = NIEDRIG
    assert v._lage_x.text().endswith("% rechts")
    assert v._lage_y.text().endswith("% oben")
    links_unten = QPoint(int(f.left() + 0.1 * f.width()),
                         int(f.bottom() - 0.1 * f.height()))
    QTest.mousePress(feld, Qt.MouseButton.LeftButton, pos=links_unten)
    assert st.programmer[1]["laser_x"] > 133 and st.programmer[1]["laser_y"] > 133
    assert v._lage_x.text().endswith("% links")
    assert v._lage_y.text().endswith("% unten")
    # Ausserhalb des Felds bleibt der Wert am Feldrand.
    QTest.mousePress(feld, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
    assert (st.programmer[1]["laser_x"], st.programmer[1]["laser_y"]) == (255, 11)


def test_lage_anzeige_und_mitte(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    assert (v._lage_x.text(), v._lage_y.text()) == ("Mitte", "Mitte")
    v._lage_gezogen(0.64, 0.67)
    assert (v._lage_x.text(), v._lage_y.text()) == ("28 % rechts", "34 % oben")
    v._btn_mitte.click()
    # „Mitte“ = der Mittelbereich des Profils (0–10 -> 5), nicht 128.
    assert (st.programmer[1]["laser_x"], st.programmer[1]["laser_y"]) == (5, 5)
    assert (v._lage_x.text(), v._lage_y.text()) == ("Mitte", "Mitte")
    assert v._lage_feld.lage() == (0.5, 0.5)


def test_lage_natuerliche_richtung(monkeypatch):
    chans = _el400()
    for ch in chans:
        if ch.attribute == "laser_x":
            ch.laser = {"version": 1, "richtung": {
                "ende_niedrig": "links", "ende_hoch": "rechts"}}
        if ch.attribute == "laser_y":
            ch.laser = {"version": 1, "richtung": {
                "ende_niedrig": "unten", "ende_hoch": "oben"}}
    v, st = _view(monkeypatch, [_FX(1, chans)])
    v._lage_gezogen(1.0, 1.0)
    assert (st.programmer[1]["laser_x"], st.programmer[1]["laser_y"]) == (255, 255)
    v._btn_mitte.click()                            # ohne Mittelbereich: 50 %
    assert (st.programmer[1]["laser_x"], st.programmer[1]["laser_y"]) == (128, 128)


def test_vorschau_zeigt_muster_farbe_groesse(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    stern = next(k for k in v._galerie.kacheln if k.muster.name == "Stern")
    gruen = next(f for f in v._farbfelder.felder if f.farbe.name == "gruen")
    QTest.mouseClick(stern, Qt.MouseButton.LeftButton)
    gruen.click()
    feld = v._lage_feld
    assert feld._muster.name == "Stern"
    assert feld._farbe.name() == "#2aff4a"
    assert abs(feld._groesse - 0.5) < 0.01          # Grundwert 128 = mittel
    v._sprech["zoom"].schieber.setValue(255)        # ganz rechts = gross
    assert feld._groesse == 1.0
    # Das Bild wird wirklich gemalt (kein leeres Feld).
    v.resize(936, 478)
    bild = feld.grab().toImage()
    gruene = sum(1 for x in range(0, bild.width(), 3)
                 for y in range(0, bild.height(), 3)
                 if bild.pixelColor(x, y).green() > 180
                 and bild.pixelColor(x, y).red() < 120)
    assert gruene > 20


def test_achsen_haken_bleibt_in_der_ausgabestufe(monkeypatch):
    """LAS-30: der Tab schreibt den MODELL-Wert — die Umkehr fuer einen
    haengenden Laser macht die Ausgabestufe, fuer jeden Schreiber gleich."""
    from src.core.laser.achsen import apply_laser_orientation
    normal, haengend = _FX(1, _el400()), _FX(1, _el400())
    haengend.invert_laser_x = True
    werte = []
    for fx in (normal, haengend):
        v, st = _view(monkeypatch, [fx])
        v._lage_gezogen(0.9, 0.5)
        werte.append(dict(st.programmer[1]))
    assert werte[0] == werte[1]                     # gleicher Modell-Wert
    draht = apply_laser_orientation(haengend, werte[1], haengend._chans)
    assert draht["laser_x"] != werte[1]["laser_x"]  # gedreht wird am Draht
    assert draht["laser_y"] == werte[1]["laser_y"]


# ── (4) Muster-Galerie ──────────────────────────────────────────────────────

def test_galerie_zeigt_die_musterliste(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    namen = [k.muster.name for k in v._galerie.kacheln]
    assert namen == ["Kreis", "vier kleine Kreise", "Strich",
                     "gepunkteter Kreis", "gepunktetes Dreieck", "Quadrat",
                     "Stern", "pulsierender Kreis"]
    assert "8 aus Profil" in v._lbl_muster_zahl.text()
    bewegt = [k for k in v._galerie.kacheln if k.muster.bewegt]
    assert [k.muster.name for k in bewegt] == ["pulsierender Kreis"]
    assert "bewegtes Muster" in bewegt[0].toolTip()
    # Schemabild, kein Foto — das steht dabei.
    assert "Schemazeichnungen" in v._lbl_schema.text()


def test_galerie_schreibt_die_bereichsmitte(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    for kachel in v._galerie.kacheln:
        QTest.mouseClick(kachel, Qt.MouseButton.LeftButton)
        m = kachel.muster
        assert st.programmer[1]["gobo_wheel"] == (m.von + m.bis) // 2
        assert v._galerie.gewaehlt() == m
    assert st.programmer[1]["gobo_wheel"] == 240


def test_alle_0_255_klappt_den_bisherigen_regler_auf(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    zeile = v._rows["gobo_wheel"]
    assert v._muster_alle_host.isHidden()
    v._btn_muster_alle.click()
    assert not v._muster_alle_host.isHidden()
    zeile._slider.setValue(100)                     # ein Wert ohne Eintrag
    assert st.programmer[1]["gobo_wheel"] == 100
    assert v._galerie.gewaehlt() is None
    QTest.mouseClick(v._galerie.kacheln[6], Qt.MouseButton.LeftButton)
    assert zeile._slider.value() == 192             # der Regler zieht mit
    v._btn_muster_alle.click()
    assert v._muster_alle_host.isHidden()


# ── (5) Farbfelder ──────────────────────────────────────────────────────────

def test_farbfelder_schreiben_den_belegten_wert(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    assert len(v._farbfelder.felder) == 8
    assert all(f.width() >= 36 and f.height() >= 36
               for f in v._farbfelder.felder)
    for feld in v._farbfelder.felder:
        feld.click()
        f = feld.farbe
        assert st.programmer[1]["laser_color"] == (f.von + f.bis) // 2
        assert v._farbfelder.gewaehlt() == f
    next(f for f in v._farbfelder.felder if f.farbe.name == "gruen").click()
    assert st.programmer[1]["laser_color"] == 120
    assert "Grün" in v._lbl_farbe.text() and "DMX 120" in v._lbl_farbe.text()


def test_farbe_aendert_die_helligkeit_nicht(monkeypatch):
    chans = _el400() + [_Ch("intensity", 10, name="Dimmer")]
    v, st = _view(monkeypatch, [_FX(1, chans)])
    texte = [l.text() for l in v._farbe_box.findChildren(QLabel)]
    assert "Farbe ändert die Helligkeit nicht." in texte
    st.geschrieben.clear()
    for feld in v._farbfelder.felder:
        feld.click()
    assert {attr for _fid, attr, _v in st.geschrieben} == {"laser_color"}


def test_farbe_alle_0_255(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    v._btn_farbe_alle.click()
    v._rows["laser_color"]._slider.setValue(200)
    assert st.programmer[1]["laser_color"] == 200
    assert v._farbfelder.gewaehlt() is None
    assert "kein Eintrag" in v._lbl_farbe.text()


# ── (6) Regler ──────────────────────────────────────────────────────────────

def test_groesse_laeuft_richtig_herum(monkeypatch):
    """Der Kanal zaehlt umgekehrt (0 = gross, 255 = klein); der Regler nicht."""
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    r = v._sprech["zoom"]
    assert r.titel.text() == "Größe"
    assert (r.ende_links.text(), r.ende_rechts.text()) == ("klein", "groß")
    r.schieber.setValue(r.schieber.minimum())       # ganz links = klein
    assert st.programmer[1]["zoom"] == 255
    assert r.wort.text() == "klein" and r.dmx_anzeige.text() == "DMX 255"
    r.schieber.setValue(r.schieber.maximum())       # ganz rechts = gross
    assert st.programmer[1]["zoom"] == 0
    assert r.wort.text() == "groß" and r.dmx_anzeige.text() == "DMX 0"
    # Jeder DMX-Wert ist erreichbar (ganze Schritte).
    erreicht = set()
    for s in range(r.schieber.minimum(), r.schieber.maximum() + 1):
        r.schieber.setValue(s)
        erreicht.add(st.programmer[1]["zoom"])
    assert erreicht == set(range(256))


def test_zeichentempo_ruhig_bis_schnell(monkeypatch):
    chans = _el400()
    scan = next(c for c in chans if c.attribute == "laser_scan_rate")
    scan.laser = {"version": 1, "richtung": {"ende_niedrig": "schnell",
                                             "ende_hoch": "langsam"}}
    v, st = _view(monkeypatch, [_FX(1, chans)])
    r = v._sprech["laser_scan_rate"]
    assert r.titel.text() == "Zeichentempo"
    assert (r.ende_links.text(), r.ende_rechts.text()) == ("ruhig", "schnell")
    r.schieber.setValue(r.schieber.minimum())       # links = ruhig = DMX 255
    assert st.programmer[1]["laser_scan_rate"] == 255
    assert r.wort.text() == "ruhig"
    r.schieber.setValue(r.schieber.maximum())       # rechts = schnell = DMX 0
    assert st.programmer[1]["laser_scan_rate"] == 0


def test_regler_ohne_richtung_ist_ein_normaler_regler(monkeypatch):
    """Das EL-400-Profil nennt fuer Zeichentempo, Mustertempo und
    Farbsegmente keine Richtung: 0..255, und das steht dabei."""
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    for attr, titel in (("laser_scan_rate", "Zeichentempo"),
                        ("effect_speed", "Mustertempo"),
                        ("laser_color_change", "Farbsegmente")):
        r = v._sprech[attr]
        assert r.titel.text() == titel
        assert (r.ende_links.text(), r.ende_rechts.text()) == ("0", "255")
        r.schieber.setValue(60)
        assert st.programmer[1][attr] == 60
        assert r.dmx_anzeige.text() == "DMX 60"
    assert "Richtung nicht im Profil" in v._sprech["laser_scan_rate"].zusatz.text()


def test_mustertempo_nur_bei_dynamischen_mustern(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    tempo = v._sprech["effect_speed"]
    assert "nur bei dynamischen Mustern" in tempo.zusatz.text()
    for art, an in (("statisch", False), ("dynamisch", True), ("musik", False),
                    ("aus", False), ("dynamisch", True)):
        _betriebsart(v, art)
        assert tempo.schieber.isEnabled() is an, art
    # Groesse und Zeichentempo bleiben bedienbar.
    _betriebsart(v, "statisch")
    assert v._sprech["zoom"].schieber.isEnabled()


# ── Bytegleich zur bisherigen Bedienung ─────────────────────────────────────

def test_dmx_werte_bytegleich_zur_alten_bedienung(monkeypatch):
    """Dieselbe Wahl einmal ueber die Bausteine, einmal ueber die bisherigen
    Kacheln und Regler (dasselbe Geraet ohne Laser-Angaben) -> derselbe
    Programmer-Inhalt."""
    from src.ui.views.laser_view import _range_value
    neu, st_neu = _view(monkeypatch, [_FX(1, _el400())])
    _betriebsart(neu, "statisch")
    QTest.mouseClick(next(k for k in neu._galerie.kacheln
                          if k.muster.name == "Stern"), Qt.MouseButton.LeftButton)
    next(f for f in neu._farbfelder.felder if f.farbe.name == "gruen").click()
    neu._sprech["zoom"].schieber.setValue(200)
    neu._sprech["laser_scan_rate"].schieber.setValue(60)
    neu._sprech["effect_speed"].schieber.setValue(30)
    neu._sprech["laser_color_change"].schieber.setValue(7)
    neu._lage_gezogen(0.64, 0.67)
    geschrieben_neu = dict(st_neu.programmer[1])

    alt, st_alt = _view(monkeypatch, [_FX(1, _el400(ohne="*"))])
    assert not alt._plan.neu
    statisch = next(r for r in _el400()[0].ranges if "Statisch" in r.name)
    alt._on_mode_tile_clicked(_range_value(statisch))
    for attr, wert in (("gobo_wheel", 192), ("laser_color", 120),
                       ("zoom", 255 - 200), ("laser_scan_rate", 60),
                       ("effect_speed", 30), ("laser_color_change", 7),
                       ("laser_x", geschrieben_neu["laser_x"]),
                       ("laser_y", geschrieben_neu["laser_y"])):
        alt._rows[attr]._slider.setValue(wert)
    assert geschrieben_neu == st_alt.programmer[1]
    assert geschrieben_neu == {
        "shutter": 174, "gobo_wheel": 192, "laser_color": 120, "zoom": 55,
        "laser_scan_rate": 60, "effect_speed": 30, "laser_color_change": 7,
        "laser_x": 99, "laser_y": 92}
    # Alles ging ueber set_programmer_value — kein anderer Ausgabeweg.
    assert {a for _f, a, _v in st_neu.geschrieben} == set(geschrieben_neu)


# ── (7) Gemerkte Muster ─────────────────────────────────────────────────────

class _Pal:
    def __init__(self, name):
        self.name = name


def test_gemerkte_muster_sind_die_laser_paletten(monkeypatch):
    from PySide6.QtWidgets import QPushButton, QToolButton
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    assert v._gemerkt_box.isVisibleTo(v)
    assert v._pal_box.isHidden()                    # derselbe Bestand, einmal
    angewendet, gemerkt = [], []
    # Auf der Klasse: die Knoepfe binden die Methode schwach (weak_slot).
    def _apply_palette(self, p):
        angewendet.append(p.name)

    def _save_palette(self):
        gemerkt.append(True)

    monkeypatch.setattr(type(v), "_apply_palette", _apply_palette)
    monkeypatch.setattr(type(v), "_save_palette", _save_palette)
    v._gemerkte_aufbauen([_Pal("Kreis rot"), _Pal("Stern bunt"), _Pal("Welle")])
    assert [b.text() for b in v._gemerkt_knoepfe] == ["Kreis rot", "Stern bunt"]
    assert all(b.height() >= 36 or b.maximumHeight() >= 36
               for b in v._gemerkt_knoepfe)
    v._gemerkt_knoepfe[1].click()
    assert angewendet == ["Stern bunt"]
    mehr = [b for b in v._gemerkt_box.findChildren(QToolButton) if b.menu()]
    assert len(mehr) == 1
    assert [a.text() for a in mehr[0].menu().actions()] == ["Welle"]
    mehr[0].menu().actions()[0].trigger()
    assert angewendet == ["Stern bunt", "Welle"]
    v._btn_merken.click()
    assert gemerkt == [True]
    assert isinstance(v._btn_merken, QPushButton)


def test_merken_legt_eine_laser_palette_an(monkeypatch):
    """Keine zweite Ablage: „+ merken…“ schreibt in die Paletten der Show."""
    from PySide6.QtWidgets import QInputDialog
    import src.core.engine.palette as pal
    v, st = _view(monkeypatch, [_FX(1, _el400())])

    class _Manager:
        def __init__(self):
            self.liste = []

        def find(self, name):
            return next((p for p in self.liste if p.name == name), None)

        def add(self, p):
            self.liste.append(p)

        def get_by_type(self, typ):
            return [p for p in self.liste if p.type == typ]

    manager = _Manager()
    monkeypatch.setattr(pal, "get_palette_manager", lambda: manager)
    monkeypatch.setattr(pal.Palette, "record_from_programmer",
                        lambda self, fids: setattr(self, "fixture_values", {
                            f: dict(st.programmer.get(f, {})) for f in fids}))
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Stern grün", True)))
    _betriebsart(v, "statisch")
    QTest.mouseClick(v._galerie.kacheln[6], Qt.MouseButton.LeftButton)
    v._btn_merken.click()
    assert [(p.name, p.type) for p in manager.liste] == [
        ("Stern grün", pal.PaletteType.LASER)]
    assert manager.liste[0].fixture_values[1]["gobo_wheel"] == 192
    assert [b.text() for b in v._gemerkt_knoepfe] == ["Stern grün"]


# ── (8) Mehrere Laser ───────────────────────────────────────────────────────

def test_mehrere_gleiche_laser_bedienung_wirkt_auf_alle(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400()), _FX(2, _el400())])
    assert "2 Laser" in v._lbl_modell.text()
    assert v._lbl_lage_hinweis.text() == "zeigt den ersten von 2 Lasern"
    _betriebsart(v, "dynamisch")
    QTest.mouseClick(v._galerie.kacheln[5], Qt.MouseButton.LeftButton)
    v._farbfelder.felder[3].click()
    v._lage_gezogen(0.2, 0.9)
    v._sprech["zoom"].schieber.setValue(10)
    assert st.programmer[1] == st.programmer[2]
    assert set(st.programmer[1]) == {"shutter", "gobo_wheel", "laser_color",
                                     "laser_x", "laser_y", "zoom"}
    assert v._lbl_dmx_estop.text() == "Laser AN"
    # Die Vorschau zeigt den ERSTEN Laser.
    st.programmer[2]["gobo_wheel"] = 0
    v._load_values()
    assert v._lage_feld._muster.name == "Quadrat"


def test_zustand_bei_teilweise_eingeschalteten_lasern(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400()), _FX(2, _el400())])
    st.programmer[1] = {"shutter": 174}
    v._load_values()
    assert v._lbl_dmx_estop.text() == "Laser AN (1 von 2)"


def test_unterschiedliche_profile_fallen_je_baustein_zurueck(monkeypatch):
    """Zwei Laser, die sich nur in der Musterliste unterscheiden: gemeinsam
    bleiben Betriebsart, Farbe, Lage und Regler — das Muster faellt auf den
    Regler zurueck."""
    anders = _el400()
    muster = next(c for c in anders if c.attribute == "gobo_wheel")
    muster.laser["muster"] = muster.laser["muster"][:3]
    v, st = _view(monkeypatch, [_FX(1, _el400()), _FX(2, anders)])
    plan = v._plan
    assert plan.muster is None
    assert plan.betriebsart is not None and plan.farben is not None
    assert plan.lage is not None and "zoom" in v._sprech
    assert v._muster_box.isHidden()
    assert not v._rows["gobo_wheel"].isHidden()
    v._rows["gobo_wheel"]._slider.setValue(64)
    assert st.programmer[1]["gobo_wheel"] == st.programmer[2]["gobo_wheel"] == 64
    assert v.bedienbare_attribute() >= {c.attribute for c in anders}


def test_laser_mit_und_ohne_angaben_gemischt(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400()), _FX(2, _el400(ohne="*"))])
    assert not v._plan.neu
    assert v._bausteine.isHidden() and v._seg_box.isHidden()
    assert not v._mode_box.isHidden()
    assert set(v._rows) == {c.attribute for c in _el400()} - {"shutter"}


# ── (9) Rueckfall je Baustein ───────────────────────────────────────────────

def test_ohne_profilangaben_die_bisherige_bedienung(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400(ohne="*"))])
    assert not v._plan.neu
    assert v._bausteine.isHidden()
    assert v._seg_box.isHidden() and not v._mode_box.isHidden()
    assert not v._pal_box.isHidden()
    assert set(v._rows) == {c.attribute for c in _el400()} - {"shutter"}
    assert v._sprech == {}
    # Die Sicherheitsleiste gilt fuer JEDEN DMX-Laser.
    assert v._dmx_safety_box.isVisibleTo(v)
    assert v._lbl_dmx_estop.text() == "Laser AUS"   # aus den Wertebereichen
    v._on_mode_tile_clicked(174)
    assert v._lbl_dmx_estop.text() == "Laser AN"


@pytest.mark.parametrize("ohne, zeilen, weg", [
    (("shutter",), set(), "_seg_box"),
    (("gobo_wheel",), {"gobo_wheel"}, "_muster_box"),
    (("laser_color",), {"laser_color"}, "_farbe_box"),
    (("laser_x",), {"laser_x", "laser_y"}, "_lage_box"),
    (("laser_y",), {"laser_x", "laser_y"}, "_lage_box"),
])
def test_jeder_baustein_faellt_einzeln_zurueck(monkeypatch, ohne, zeilen, weg):
    v, st = _view(monkeypatch, [_FX(1, _el400(ohne=ohne))])
    assert v._plan.neu                               # die anderen bleiben
    assert getattr(v, weg).isHidden()
    for name in ("_seg_box", "_muster_box", "_farbe_box", "_lage_box"):
        if name != weg:
            assert not getattr(v, name).isHidden(), name
    for attr in zeilen:                              # bisheriger Regler, sichtbar
        zeile = v._rows[attr]
        assert not zeile.isHidden() and not v._rows_host.isHidden()
        zeile._slider.setValue(77)
        assert st.programmer[1][attr] == 77
    if "shutter" in ohne:
        assert not v._mode_box.isHidden()
    assert v.bedienbare_attribute() >= {c.attribute for c in _el400()}


def test_groesse_ohne_richtung_bleibt_bedienbar(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400(ohne=("zoom",)))])
    r = v._sprech["zoom"]
    assert (r.ende_links.text(), r.ende_rechts.text()) == ("0", "255")
    r.schieber.setValue(200)
    assert st.programmer[1]["zoom"] == 200           # nicht gedreht


def test_kanal_mit_wertebereichen_behaelt_seine_zeile(monkeypatch):
    """Ein Regler ohne Richtungsangabe ersetzt keine Zeile, die benannte
    Wertebereiche zur Auswahl anbietet."""
    chans = _el400()
    seg = next(c for c in chans if c.attribute == "laser_color_change")
    seg.ranges = [_Rng(0, 127, "aus"), _Rng(128, 255, "Segmente")]
    v, _st = _view(monkeypatch, [_FX(1, chans)])
    assert "laser_color_change" not in v._sprech
    assert not v._rows["laser_color_change"].isHidden()


def test_fremde_kanaele_bleiben_als_regler(monkeypatch):
    chans = _el400() + [_Ch("gobo_rotation", 10, name="Rotation"),
                        _Ch("laser_grating", 11, name="Gitter")]
    v, _st = _view(monkeypatch, [_FX(1, chans)])
    assert {"gobo_rotation", "laser_grating"} <= set(v._rows)
    assert not v._rows_host.isHidden()
    assert v.bedienbare_attribute() >= {c.attribute for c in chans}


def test_kaputte_angaben_stoeren_nicht(monkeypatch):
    chans = _el400()
    chans[1].laser = {"version": 99, "muster": "kaputt"}
    chans[7].laser = "kein Objekt"
    v, _st = _view(monkeypatch, [_FX(1, chans)])
    assert v._plan.muster is None and v._plan.farben is None
    assert {"gobo_wheel", "laser_color"} <= set(v._rows)


# ── Echter Programmer: Bibliothek, Hoehe, Lampen-Vorschau ───────────────────

#: Der Programmer in einem Hauptfenster von 1500 x 850 (das Mass des Entwurfs).
PROGRAMMER = (1500, 664)


@pytest.fixture
def echt(tmp_path, monkeypatch):
    from src.core.app_state import get_state
    from src.core.database.fixture_db import ensure_builtins
    from src.core.show.show_file import reset_show
    import src.ui.views.programmer_view as pvm

    app = _app()
    monkeypatch.setattr(pvm, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pvm, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    ensure_builtins()
    reset_show()
    st = get_state()
    yield app, st, pvm
    st.laser_estop_active = False
    reset_show()


def _laser_profile():
    """``[(Kurzname, Profil-ID, Modus, Kanalzahl)]`` aller Laser der DB."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine
    from src.core.database.models import FixtureProfile
    out = []
    with Session(engine()) as s:
        for prof in s.execute(select(FixtureProfile).where(
                FixtureProfile.fixture_type == "laser")).scalars():
            for m in prof.modes:
                out.append((prof.short_name, int(prof.id), m.name,
                            len(m.channels)))
    return out


def _patch(st, fid, pid, modus, n, typ="laser", adr=1):
    from src.core.database.models import PatchedFixture
    st.add_fixture(PatchedFixture(
        fid=fid, label=f"G{fid}", fixture_profile_id=pid, mode_name=modus,
        universe=1, address=adr, channel_count=n, fixture_type=typ),
        undoable=False)


def test_kein_kanal_geht_verloren_ueber_alle_laser_der_bibliothek(echt):
    """Wie UI-89 es fuer den EL-400 prueft — hier fuer JEDEN Laser und Modus:
    was der Laser-Reiter fuehrt, ist dort auch bedienbar."""
    from src.core.app_state import get_channels_for_patched
    from src.core.show.show_file import reset_show
    from src.ui.views.laser_view import LaserView, im_laser_reiter
    app, st, _pvm = echt
    profile = _laser_profile()
    kurz = {p[0] for p in profile}
    # Die mitgelieferte Bibliothek ist dabei.
    for datei in (ROOT / "fixtures" / "bibliothek").rglob("*.json"):
        d = json.loads(datei.read_text(encoding="utf-8"))
        if d.get("typ") == "laser":
            assert d["kurzname"] in kurz, datei.name
    assert len(profile) >= 6
    mit_bausteinen = 0
    for kurzname, pid, modus, n in profile:
        reset_show()
        _patch(st, 1, pid, modus, n)
        st.set_selected_fids([1])
        fx = next(f for f in st.get_patched_fixtures() if f.fid == 1)
        v = LaserView(follow_selection=False)
        try:
            v.refresh_from_selection()
            attrs = {ch.attribute for ch in get_channels_for_patched(fx)
                     if im_laser_reiter(ch.attribute)}
            fehlt = attrs - v.bedienbare_attribute()
            assert not fehlt, (kurzname, modus, sorted(fehlt))
            # Kein Attribut doppelt bedient (Baustein UND Zeile) — ausser
            # hinter „alle 0–255“.
            doppelt = (set(v._rows) & v._plan.abgedeckt()) - {
                k.attribut for k in (v._plan.muster, v._plan.farben) if k}
            assert not doppelt, (kurzname, modus, sorted(doppelt))
            mit_bausteinen += bool(v._plan.neu)
        finally:
            v.deleteLater()
            app.processEvents()
    assert mit_bausteinen >= 1                        # mindestens der EL-400


def _programmer(echt, vorher_zu=False):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine
    from src.core.database.models import FixtureProfile
    app, st, pvm = echt
    if vorher_zu:
        pvm._save_prefs({"programmer_bottom_collapsed": True})
    adr = 1
    with Session(engine()) as s:
        for fid, kurz, typ in ((1, "EL400RGBMK2", "laser"), (2, "PARD", "par"),
                               (3, "PANGFB4", "laser")):
            prof = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == kurz)).scalars().first()
            m = prof.modes[0]
            _patch(st, fid, int(prof.id), m.name, len(m.channels), typ, adr)
            adr += len(m.channels)
    pv = pvm.ProgrammerView()
    pv.resize(*PROGRAMMER)
    pv.show()
    pv._refresh_fixture_list()
    app.processEvents()

    def waehle(*fids):
        st.set_selected_fids(list(fids))
        for _ in range(3):
            app.processEvents()

    return app, st, pvm, pv, waehle


def test_tab_passt_ohne_scrollen(echt):
    app, st, pvm, pv, waehle = _programmer(echt)
    try:
        waehle(1)
        lv = pv._embedded_laser
        assert lv.isVisible() and lv._plan.neu
        assert lv._scroll.verticalScrollBar().maximum() == 0
        assert lv._scroll.horizontalScrollBar().maximum() == 0
        sicht = lv._scroll.viewport()
        for w in (lv._lage_feld, lv._btn_mitte, lv._galerie, lv._btn_merken,
                  lv._lbl_schema, lv._farbfelder, *lv._sprech.values()):
            assert w.isVisibleTo(lv), w
            oben = w.mapTo(sicht, QPoint(0, 0))
            assert oben.y() >= 0 and oben.x() >= 0, w
            assert oben.y() + w.height() <= sicht.height(), w
            assert oben.x() + w.width() <= sicht.width(), w
        # Nichts Altes daneben: keine Regler-Zeilen, keine grossen Kaesten.
        assert lv._rows_host.isHidden() and lv._pal_box.isHidden()
        assert lv._pattern_box.isHidden() and lv._mode_box.isHidden()
        assert set(lv._rows) == {"gobo_wheel", "laser_color"}  # „alle 0–255“
    finally:
        pv.close()
        pv.deleteLater()
        app.processEvents()


def test_lampen_vorschau_klappt_nur_fuer_reine_laser_ein(echt):
    app, st, pvm, pv, waehle = _programmer(echt)
    try:
        tp = pv._tile_preview
        waehle(2)                                   # PAR: wie eingestellt
        assert not tp.is_collapsed() and not pv._color_preview.isHidden()
        waehle(1)                                   # reiner Laser: zu
        assert tp.is_collapsed() and pv._color_preview.isHidden()
        # Der gemerkte Zustand der anderen Geraete bleibt.
        assert pvm._load_prefs().get("programmer_bottom_collapsed", False) is False
        tp.toggle_collapsed()                       # von Hand auf: gilt nur jetzt
        assert pvm._load_prefs().get("programmer_bottom_collapsed", False) is False
        waehle(2)
        assert not tp.is_collapsed() and not pv._color_preview.isHidden()
        waehle(1, 2)                                # gemischt: nicht einklappen
        assert not tp.is_collapsed() and not pv._color_preview.isHidden()
        waehle(3)                                   # Laser MIT Dimmer/RGB: auch nicht
        assert not tp.is_collapsed() and not pv._color_preview.isHidden()
        waehle(1)
        assert tp.is_collapsed()
        waehle()                                    # leere Auswahl: wie vorher
        assert not tp.is_collapsed() and not pv._color_preview.isHidden()
    finally:
        pv.close()
        pv.deleteLater()
        app.processEvents()


def test_eingeklappte_vorschau_bleibt_eingeklappt(echt):
    app, st, pvm, pv, waehle = _programmer(echt, vorher_zu=True)
    try:
        tp = pv._tile_preview
        assert tp.is_collapsed()
        waehle(1)
        assert tp.is_collapsed()
        waehle(2)
        assert tp.is_collapsed()                    # nicht „versehentlich auf“
        assert pvm._load_prefs()["programmer_bottom_collapsed"] is True
    finally:
        pv.close()
        pv.deleteLater()
        app.processEvents()


def test_echter_el400_not_aus_und_ausgabe(echt):
    """Im echten State: der NOT-AUS der Leiste setzt den Laser-Latch, und die
    Bausteine schreiben in den Programmer (kein eigener Ausgabeweg)."""
    app, st, pvm, pv, waehle = _programmer(echt)
    try:
        waehle(1)
        lv = pv._embedded_laser
        _betriebsart(lv, "statisch")
        QTest.mouseClick(next(k for k in lv._galerie.kacheln
                              if k.muster.name == "Stern"),
                         Qt.MouseButton.LeftButton)
        next(f for f in lv._farbfelder.felder if f.farbe.name == "gruen").click()
        assert st.programmer[1] == {"shutter": 174, "gobo_wheel": 192,
                                    "laser_color": 120}
        assert lv._lbl_dmx_estop.text() == "Laser AN"
        assert "EL-400RGB MK2" in lv._lbl_modell.text()
        lv._btn_dmx_estop.click()
        assert st.laser_estop_active is True
        assert lv._lbl_dmx_estop.text() == "NOT-AUS aktiv"
        # Farbe loest ihn nicht, die Betriebsart schon (A3D-02).
        lv._farbfelder.felder[0].click()
        assert st.laser_estop_active is True
        _betriebsart(lv, "statisch")
        assert st.laser_estop_active is False
    finally:
        pv.close()
        pv.deleteLater()
        app.processEvents()
