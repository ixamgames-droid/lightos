"""FM-85: Klicktest-Befunde Matrix-Effekte.

1. Wechsel auf einen anderen Effekt mit ungespeicherten Aenderungen fragt nach
   (Speichern / Verwerfen / Zurueck); bei „Zurueck" bleibt die Auswahl.
2. Titel im Programmer ist ehrlich, wenn die Liste auch ungebundene Effekte zeigt.
3. Unbrauchbare Medien werden nicht kopiert, das alte Medium bleibt.
4. Algorithmen mit deutschen Anzeigenamen; gespeicherte Schluessel unveraendert.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                    # noqa: E402
from PySide6.QtGui import QColor, QImage                         # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

from src.core.engine import matrix_media as MM                   # noqa: E402
from src.core.engine.rgb_matrix import (RgbAlgorithm,            # noqa: E402
                                        RgbMatrixInstance)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ansicht(app):
    from src.core.engine.function_manager import get_function_manager
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    fm = get_function_manager()
    fm.stop_all()
    vorher = {f.id for f in fm.all()}
    a = fm.new_rgb_matrix(name="FM85 A")
    b = fm.new_rgb_matrix(name="FM85 B")
    v = RgbMatrixView()
    v._rebuild_from_state()
    yield v, a, b
    v.deleteLater()
    fm.stop_all()
    for f in list(fm.all()):
        if f.id not in vorher:
            fm.remove(f.id)


def _zeile(v, inst):
    return next(i for i, m in enumerate(v._visible_instances()) if m.id == inst.id)


def _entwurf_aendern(v, a):
    v._list.setCurrentRow(_zeile(v, a))
    assert v._saved is a
    v._current.color1 = (0, 0, 255)
    v._update_dirty()
    assert v._ist_dirty()


# ── 1: Rueckfrage beim Wechsel ────────────────────────────────────────────────

def test_wechsel_zurueck_behaelt_entwurf_und_auswahl(ansicht):
    v, a, b = ansicht
    _entwurf_aendern(v, a)
    fragen = []
    v._frage_ungespeichert = lambda: fragen.append(1) or "zurueck"
    v._list.setCurrentRow(_zeile(v, b))
    assert fragen == [1]
    assert v._saved is a
    assert v._list.currentRow() == _zeile(v, a)
    assert tuple(v._current.color1) == (0, 0, 255)
    assert tuple(a.color1) != (0, 0, 255)


def test_wechsel_verwerfen(ansicht):
    v, a, b = ansicht
    alt = tuple(a.color1)
    _entwurf_aendern(v, a)
    v._frage_ungespeichert = lambda: "verwerfen"
    v._list.setCurrentRow(_zeile(v, b))
    assert v._saved is b
    assert tuple(a.color1) == alt


def test_wechsel_speichern(ansicht):
    v, a, b = ansicht
    _entwurf_aendern(v, a)
    v._frage_ungespeichert = lambda: "speichern"
    v._list.setCurrentRow(_zeile(v, b))
    assert tuple(a.color1) == (0, 0, 255)
    assert v._saved is b
    assert v._list.currentRow() == _zeile(v, b)


def test_ohne_aenderung_keine_frage(ansicht):
    v, a, b = ansicht
    v._list.setCurrentRow(_zeile(v, a))
    v._frage_ungespeichert = lambda: pytest.fail("keine Rueckfrage erwartet")
    v._list.setCurrentRow(_zeile(v, b))
    assert v._saved is b


# ── 2: ehrlicher Titel ────────────────────────────────────────────────────────

def test_titel_nennt_ungebundene(ansicht):
    v, a, b = ansicht
    a.source_group = "Flat-Pars"
    v._follow_selection = True
    v._group_context = lambda: ("Flat-Pars", {"Flat-Pars", "Spider"})
    v._rebuild_from_state()
    v._update_group_header()
    txt = v._group_header.text()
    assert "ohne Gruppenbindung" in txt, txt
    labels = [v._list.item(i).text() for i in range(v._list.count())]
    assert any(t.startswith("FM85 B") and "ohne Gruppe" in t for t in labels)
    assert "FM85 A" in labels


# ── 3: Medien vorher pruefen ──────────────────────────────────────────────────

def test_unbrauchbares_medium_wird_nicht_kopiert(app):
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    ordner = tempfile.mkdtemp(prefix="fm85_")
    medien = os.path.join(ordner, "medien")
    MM.set_media_dir_for_test(medien)
    try:
        gif = os.path.join(ordner, "gut.gif")
        img = QImage(2, 2, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))
        assert img.save(gif, "GIF") or img.save(gif.replace(".gif", ".png"), "PNG")
        gut = gif if os.path.isfile(gif) else gif.replace(".gif", ".png")
        mp4 = os.path.join(ordner, "clip.mp4")
        kaputt = os.path.join(ordner, "kaputt.png")
        with open(mp4, "wb") as f:
            f.write(b"\0" * 64)
        with open(kaputt, "wb") as f:
            f.write(b"kein bild")
        assert MM.pruefen(gut) == ""
        assert "Video" in MM.pruefen(mp4)
        assert "nicht lesbar" in MM.pruefen(kaputt)

        v = RgbMatrixView()
        m = RgbMatrixInstance("M", cols=2, rows=2)
        m.algorithm = RgbAlgorithm.MEDIA
        v._current = m
        v._load_ui(m)
        rel = v.medium_setzen(gut)
        assert rel and m.params["media_path"] == rel
        for schlecht in (mp4, kaputt):
            assert v.medium_setzen(schlecht) == ""
            assert m.params["media_path"] == rel
        assert sorted(os.listdir(medien)) == [rel]
        assert "Nicht übernommen" in v._medien_status.text()
        v.deleteLater()
    finally:
        MM.set_media_dir_for_test(None)


# ── 4: deutsche Anzeigenamen ──────────────────────────────────────────────────

def test_algorithmen_deutsch_schluessel_bleiben(ansicht):
    v, a, b = ansicht
    texte = [v._algo_combo.itemText(i) for i in range(v._algo_combo.count())]
    for englisch in ("Plain", "Wipe", "Wave", "Gradient", "Rainbow", "Fill",
                     "Random", "Color Fade", "Sine Plasma"):
        assert englisch not in texte, englisch
    daten = [v._algo_combo.itemData(i) for i in range(v._algo_combo.count())]
    assert daten == [x.value for x in RgbAlgorithm]
    v._list.setCurrentRow(_zeile(v, a))
    v._algo_combo.setCurrentText(RgbAlgorithm.WIPE.value)
    assert v._algo_combo.currentText() == "Wischen"
    assert v._current.algorithm is RgbAlgorithm.WIPE
    assert v._current.to_dict()["algorithm"] == "Wipe"


def test_alte_show_mit_englischem_schluessel_laedt(ansicht):
    v, a, b = ansicht
    alt = {"name": "Alt", "algorithm": "Sine Plasma", "cols": 2, "rows": 2}
    m = RgbMatrixInstance.from_dict(alt)
    assert m.algorithm is RgbAlgorithm.SINEPLASMA
    v._current = m
    v._load_ui(m)
    assert v._algo_combo.currentText() == "Plasma (Sinus)"
    assert v._algo_combo.wert() == "Sine Plasma"
