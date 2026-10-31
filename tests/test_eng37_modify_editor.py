"""ENG-37 Schritt 1: Haken „Modify-Effekt" und Gruppe „Modify" im Matrix-Editor.

Der Haken sitzt unter „Stil", die Gruppe „Modify" (Betriebsart, Staerke) ist
ein FESTER Block, der nur ein- und ausgeblendet wird — nichts wird im Signal
des Hakens gebaut oder geloescht (Lehre aus STAB-38).

Geprueft wird zweifach:

1. im selben Prozess: Felder, Sichtbarkeit, Entwurf/Speichern, Vorschau;
2. als Schleife in einem KINDPROZESS mit echter Bedienung (Haken anklicken,
   Aufklappliste der Betriebsart oeffnen und Eintrag anklicken, Stil wechseln)
   — ein nativer Absturz reisst so den Testlauf nicht mit
   (Muster tests/test_stab38_matrix_parameterfelder.py).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_ROLLE = os.environ.get("ENG37_ARBEITER", "")
_MARKE = "ENG37-UEBERLEBT"


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _ansicht(stil="Dimmer"):
    """Matrix-Ansicht mit einer EIGENEN, frischen Matrix (Lauflicht)."""
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    ansicht = RgbMatrixView()
    ansicht._add()
    assert ansicht._current is not None
    ansicht._algo_combo.setCurrentText(RgbAlgorithm.CHASE.value)
    ansicht._style_combo.setCurrentText(stil)
    return ansicht


@pytest.fixture
def ansicht():
    from PySide6.QtWidgets import QApplication
    from _qt_lifecycle import destroy_all_top_level_widgets
    _app()
    a = _ansicht()
    eigene = a._saved
    yield a
    # Die Matrix liegt im geteilten FunctionManager — wieder entfernen.
    try:
        from src.core.engine.function_manager import get_function_manager
        if eigene is not None:
            get_function_manager().remove(eigene.id)
    except Exception:
        pass
    destroy_all_top_level_widgets(QApplication.instance())


# ── 1. Felder und Sichtbarkeit ───────────────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestFelder:

    def test_haken_und_gruppe_sind_da_und_zunaechst_aus(self, ansicht):
        assert ansicht._cb_modify.text() == "Modify-Effekt"
        assert ansicht._cb_modify.isChecked() is False
        assert ansicht._cb_modify.isEnabled()
        assert ansicht._grp_modify.title() == "Modify"
        assert ansicht._grp_modify.isHidden()
        assert ansicht._current.modify is False
        assert not [k for k in ansicht._current.to_dict() if k.startswith("modify")]

    def test_haken_zeigt_die_gruppe_und_schreibt_den_entwurf(self, ansicht):
        ansicht._cb_modify.setChecked(True)
        assert not ansicht._grp_modify.isHidden()
        assert ansicht._current.modify is True
        assert ansicht._current.modify_wirksam() is True
        texte = [ansicht._modify_mode_combo.itemText(i)
                 for i in range(ansicht._modify_mode_combo.count())]
        assert texte == ["Addieren", "Abziehen", "Abdunkeln"]
        assert ansicht._modify_strength_spin.value() == 100
        assert (ansicht._modify_strength_spin.minimum(),
                ansicht._modify_strength_spin.maximum()) == (0, 100)

    def test_betriebsart_und_staerke_landen_im_entwurf(self, ansicht):
        ansicht._cb_modify.setChecked(True)
        ansicht._modify_mode_combo.setCurrentIndex(
            ansicht._modify_mode_combo.findData("dim"))
        ansicht._modify_strength_spin.setValue(35)
        assert (ansicht._current.modify_mode,
                ansicht._current.modify_strength) == ("dim", 35)

    def test_haken_raus_blendet_aus_und_merkt_die_einstellungen(self, ansicht):
        ansicht._cb_modify.setChecked(True)
        gruppe = ansicht._grp_modify
        combo = ansicht._modify_mode_combo
        combo.setCurrentIndex(combo.findData("sub"))
        ansicht._modify_strength_spin.setValue(60)
        ansicht._cb_modify.setChecked(False)
        assert gruppe.isHidden()
        assert ansicht._current.modify is False
        assert (ansicht._current.modify_mode,
                ansicht._current.modify_strength) == ("sub", 60)
        ansicht._cb_modify.setChecked(True)
        # dieselben Widgets, nicht neu gebaut
        assert ansicht._grp_modify is gruppe and ansicht._modify_mode_combo is combo
        assert combo.currentData() == "sub"
        assert ansicht._modify_strength_spin.value() == 60

    def test_felder_bleiben_dieselben_objekte(self, ansicht):
        """Feste Felder: An/Aus und Stilwechsel bauen nichts neu."""
        import shiboken6
        teile = (ansicht._cb_modify, ansicht._grp_modify,
                 ansicht._modify_mode_combo, ansicht._modify_strength_spin,
                 ansicht._modify_hint)
        for _ in range(5):
            ansicht._cb_modify.setChecked(True)
            ansicht._style_combo.setCurrentText("RGB")
            ansicht._style_combo.setCurrentText("Dimmer")
            ansicht._cb_modify.setChecked(False)
        _app().processEvents()
        assert teile == (ansicht._cb_modify, ansicht._grp_modify,
                         ansicht._modify_mode_combo, ansicht._modify_strength_spin,
                         ansicht._modify_hint)
        assert all(shiboken6.isValid(t) for t in teile)

    @pytest.mark.parametrize("stil", ["Shutter"])     # RGB/RGBW: frei seit ENG-38
    def test_andere_stile_sperren_den_haken(self, ansicht, stil):
        ansicht._cb_modify.setChecked(True)
        assert not ansicht._grp_modify.isHidden()
        ansicht._style_combo.setCurrentText(stil)
        assert not ansicht._cb_modify.isEnabled()
        assert ansicht._grp_modify.isHidden()
        assert ansicht._current.modify_wirksam() is False
        assert "Dimmer" in ansicht._cb_modify.toolTip()
        ansicht._style_combo.setCurrentText("Dimmer")
        assert ansicht._cb_modify.isEnabled()
        assert not ansicht._grp_modify.isHidden()

    def test_hinweis_bei_dimmer_min_ueber_null(self, ansicht):
        ansicht._cb_modify.setChecked(True)
        assert "Grundbetrag" not in ansicht._modify_hint.text()
        assert "Snaps" in ansicht._modify_hint.text()
        assert "Chaser-Schritt" in ansicht._modify_hint.text()
        ansicht._imin_spin.setValue(40)
        assert "Grundbetrag" in ansicht._modify_hint.text()
        ansicht._imin_spin.setValue(0)
        assert "Grundbetrag" not in ansicht._modify_hint.text()


# ── 2. Entwurf, Speichern, Wiederoeffnen ─────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestEntwurf:

    def _speichern(self, ansicht):
        ansicht._save_edit()
        assert ansicht._dirty_lbl.text() == ""

    def test_haken_meldet_aenderung_und_laesst_sich_speichern(self, ansicht):
        self._speichern(ansicht)
        ansicht._cb_modify.setChecked(True)
        assert ansicht._dirty_lbl.text() != ""
        assert ansicht._saved.modify is False      # erst beim Speichern
        self._speichern(ansicht)
        assert ansicht._saved.modify is True
        assert ansicht._saved.to_dict()["modify"] is True

    def test_wiederoeffnen_zeigt_die_gespeicherten_werte(self, ansicht):
        ansicht._cb_modify.setChecked(True)
        ansicht._modify_mode_combo.setCurrentIndex(
            ansicht._modify_mode_combo.findData("sub"))
        ansicht._modify_strength_spin.setValue(45)
        self._speichern(ansicht)
        ansicht._select(ansicht._list.currentRow())
        assert ansicht._dirty_lbl.text() == ""
        assert ansicht._cb_modify.isChecked()
        assert not ansicht._grp_modify.isHidden()
        assert ansicht._modify_mode_combo.currentData() == "sub"
        assert ansicht._modify_strength_spin.value() == 45

    def test_haken_entfernen_und_speichern_nimmt_ihn_wirklich_weg(self, ansicht):
        ansicht._cb_modify.setChecked(True)
        self._speichern(ansicht)
        ansicht._cb_modify.setChecked(False)
        self._speichern(ansicht)
        assert ansicht._saved.modify is False
        assert "modify" not in ansicht._saved.to_dict()

    def test_unberuehrte_matrix_bleibt_ohne_aenderungshinweis(self, ansicht):
        self._speichern(ansicht)
        vorher = ansicht._saved.to_dict()
        ansicht._select(ansicht._list.currentRow())
        assert ansicht._dirty_lbl.text() == ""
        assert ansicht._saved.to_dict() == vorher
        assert not [k for k in vorher if k.startswith("modify")]


# ── 3. Vorschau zeichnet in allen drei Arten ─────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
def test_vorschau_zeichnet_modify_eingefaerbt(ansicht):
    from PySide6.QtGui import QColor, QImage
    from src.ui.views import rgb_matrix_view as V
    vorschauen = [w for w in ansicht.findChildren(V.QWidget)
                  if hasattr(w, "_grid") and hasattr(w, "_matrix")]
    assert vorschauen, "Vorschau-Widget nicht gefunden"
    vorschau = vorschauen[0]
    vorschau.resize(320, 80)
    m = vorschau._matrix
    assert m is not None

    def bild():
        vorschau._grid = [(255, 255, 255)] * (m.cols * m.rows)
        img = QImage(vorschau.size(), QImage.Format.Format_RGB32)
        img.fill(QColor("#000000"))
        vorschau.render(img)
        return img

    def farbe(img):
        c = QColor(img.pixel(vorschau.width() // 2, vorschau.height() - 12))
        return (c.red(), c.green(), c.blue())

    m.fixture_grid = list(range(1, m.cols * m.rows + 1))
    m.modify = False
    normal = farbe(bild())
    assert normal == (255, 255, 255)
    m.modify, m.modify_mode = True, "add"
    add = farbe(bild())
    m.modify_mode = "sub"
    sub = farbe(bild())
    m.modify_mode = "dim"
    bild()                                   # Schraffur: darf nur nicht werfen
    assert add == (255, 176, 0)
    assert sub == (64, 140, 255)


# ── 4. Schleife im Kindprozess ───────────────────────────────────────────────


def test_arbeiter():
    """Kindprozess: echte Matrix-Ansicht (offscreen). Haken anklicken,
    Betriebsart ueber die Aufklappliste waehlen, Staerke stellen, Stil
    wechseln, Haken wieder raus — runde um runde."""
    if not _ROLLE:
        pytest.skip("nur als Kindprozess")
    import faulthandler
    faulthandler.enable()
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    _app()
    ansicht = _ansicht()
    ansicht.resize(1400, 900)
    ansicht.show()
    QTest.qWait(50)
    # Das Einblenden laedt die Matrix frisch aus dem gespeicherten Stand —
    # Stil danach so stellen, wie es der Bediener taete.
    ansicht._style_combo.setCurrentText("Dimmer")
    QTest.qWait(15)
    assert ansicht._cb_modify.isEnabled(), ansicht._style_combo.currentText()
    runden = int(os.environ.get("ENG37_RUNDEN", "20"))
    arten = ("sub", "dim", "add")

    def haken_klicken(soll: bool):
        cb = ansicht._cb_modify
        QTest.mouseClick(cb, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(8, max(1, cb.height() // 2)))
        if cb.isChecked() != soll:           # Klick ging daneben (Layout)
            print("KLICK-ERSATZ", flush=True)
            cb.click()
        assert cb.isChecked() is soll

    for nr in range(runden):
        print("RUNDE", nr, flush=True)
        haken_klicken(True)
        QTest.qWait(15)
        assert ansicht._grp_modify.isVisible()
        assert ansicht._current.modify is True
        art = arten[nr % len(arten)]
        box = ansicht._modify_mode_combo
        zeile = box.findData(art)
        if _ROLLE == "liste":
            box.showPopup()
            QTest.qWait(25)
            liste = box.view()
            mitte = liste.visualRect(liste.model().index(zeile, 0)).center()
            QTest.mouseMove(liste.viewport(), mitte)
            QTest.mouseClick(liste.viewport(), Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, mitte)
        else:
            box.setCurrentIndex(zeile)
        QTest.qWait(15)
        assert ansicht._current.modify_mode == art
        ansicht._modify_strength_spin.setValue(10 + (nr * 7) % 90)
        if nr % 4 == 3:
            # Stilwechsel baut die Parameterfelder neu — der Modify-Block bleibt
            ansicht._style_combo.setCurrentText("Shutter")
            QTest.qWait(15)
            assert not ansicht._grp_modify.isVisible()
            ansicht._style_combo.setCurrentText("Dimmer")
            QTest.qWait(15)
            assert ansicht._grp_modify.isVisible()
        haken_klicken(False)
        QTest.qWait(15)
        assert not ansicht._grp_modify.isVisible()
        assert ansicht._current.modify is False

    print(_MARKE, flush=True)
    # Bewusst hart beenden: geprueft wird die Schleife, nicht der Abbau am
    # Prozessende (eigenes Thema, eigene Tests). Unter Windows ohne DLL-Abbau
    # (QA-101), sonst stirbt das Kind mitunter erst NACH der Marke.
    from _kind_ausstieg import harter_ausstieg
    harter_ausstieg(0)


def _kind_umgebung(tmp_path, rolle: str, runden: int) -> dict:
    """Eigener Sandkasten fuer das Kind (nie die Show-DB des Elternlaufs erben)."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["ENG37_ARBEITER"] = rolle
    env["ENG37_RUNDEN"] = str(runden)
    env["LIGHTOS_SHOW_DB"] = str(tmp_path / "show.db")
    env["LIGHTOS_CRASH_LOG"] = str(tmp_path / "crash.log")
    daten = tmp_path / "daten"
    daten.mkdir(exist_ok=True)
    env["XDG_DATA_HOME"] = str(daten)
    env["APPDATA"] = str(daten)
    # Freigegebenen Speicher sofort ueberschreiben (glibc; anderswo wirkungslos)
    # — damit ein Zugriff auf ein geloeschtes Widget nicht zufaellig gut geht.
    env["GLIBC_TUNABLES"] = "glibc.malloc.tcache_count=0:glibc.malloc.perturb=165"
    env.pop("LIGHTOS_UNIVERSES_JSON", None)
    env.pop("LIGHTOS_SACN_CID", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _schleife_im_kind(tmp_path, rolle: str, runden: int):
    fertig = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-s",
         "-p", "no:cacheprovider", "-o", "addopts=",
         f"tests/{Path(__file__).name}::test_arbeiter"],
        cwd=str(REPO), env=_kind_umgebung(tmp_path, rolle, runden),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=105)
    aus = (fertig.stdout or "") + "\n" + (fertig.stderr or "")
    geschafft = len(re.findall(r"^RUNDE ", aus, flags=re.M))
    assert fertig.returncode == 0 and _MARKE in aus, (
        f"Kindprozess ({rolle}) endete mit {fertig.returncode} nach "
        f"{geschafft} von {runden} Runden — nativer Absturz oder Fehler:\n"
        f"{aus[-3000:]}")
    assert geschafft == runden


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(115)
def test_haken_zwanzigmal_und_betriebsart_ueber_die_liste(tmp_path):
    """Wie am Bildschirm: Haken anklicken, Aufklappliste, Eintrag anklicken."""
    _schleife_im_kind(tmp_path, "liste", runden=20)


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(115)
def test_haken_zwanzigmal_und_betriebsart_per_programm(tmp_path):
    _schleife_im_kind(tmp_path, "index", runden=20)
