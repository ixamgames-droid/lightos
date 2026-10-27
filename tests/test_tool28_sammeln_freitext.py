"""TOOL-28 — der Sammel-Lauf uebernimmt den Freitext auch bei vorhandener Zeile.

Frueher setzte ``tools/backlog_sammeln.py`` bei einem Fragment, dessen ID schon
als Zeile in ``BACKLOG.md`` stand, nur den Status; der Liefertext fiel mit dem
Fragment weg. Jetzt kommt jeder Absatz, der noch nicht in der Zeile steht, als
EIN ``**Nachtrag aus Fragment (eingesammelt <Datum>):** …`` an die letzte
Zelle. Alles laeuft nur auf Wegwerf-Dateien in ``tmp_path``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _modul():
    spec = importlib.util.spec_from_file_location(
        "_backlog_sammeln_tool28", REPO / "tools" / "backlog_sammeln.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bs = _modul()
HEUTE = "2026-10-27"

TABELLE = (
    "# Backlog\n\n"
    "| ID | Prio | Status | Titel | Details |\n|---|---|---|---|---|\n"
    "| FM-1 | P2 | todo | **Alt** | **Herkunft:** Nebenbefund aus FM-0. |\n"
    "| FM-2 | P3 | todo | **Anders** | z |\n"
    "\n| ID | Prio | Status | Item |\n|---|---|---|---|\n"
    "| QA-7 | P2 | todo | **Vier Spalten** Text. |\n"
)
NACHTRAG = f"**Nachtrag aus Fragment (eingesammelt {HEUTE}):**"


def _repo(tmp_path: Path, fragmente: dict[str, str], backlog: str = TABELLE) -> Path:
    (tmp_path / "BACKLOG.md").write_text(backlog, encoding="utf-8")
    (tmp_path / "backlog.d").mkdir()
    for id_, text in fragmente.items():
        _frag(tmp_path, id_).write_text(text, encoding="utf-8")
    return tmp_path


def _frag(repo: Path, id_: str) -> Path:
    """Pfad eines Wegwerf-Fragments in ``tmp_path`` (nie das echte backlog.d)."""
    return repo / "backlog.d" / f"{id_}.md"


def _zeile(repo: Path, id_: str) -> str:
    for z in (repo / "BACKLOG.md").read_text(encoding="utf-8").split("\n"):
        if z.startswith(f"| {id_} |"):
            return z
    raise AssertionError(f"{id_} fehlt")


def _spalten(zeile: str) -> int:
    return zeile.replace("\\|", "").count("|") - 1


def _sammeln(repo: Path, **kw) -> list[str]:
    aus: list[str] = []
    assert bs.sammeln(repo, heute=HEUTE, ausgabe=aus.append, **kw) == 0, aus
    return aus


FREITEXT = ("**Herkunft:** Nebenbefund aus FM-0.\n"
            "**Ergebnis:** Der Knopf\nspeichert jetzt.\n\n"
            "Test `tests/test_x.py` (3 Faelle).\n")


def test_fehlender_absatz_wird_angehaengt_vorhandener_nicht_doppelt(tmp_path):
    repo = _repo(tmp_path, {"FM-1": "ID: FM-1\nStatus: done\n\n" + FREITEXT})
    _sammeln(repo)
    z = _zeile(repo, "FM-1")
    assert z == ("| FM-1 | P2 | done | **Alt** | **Herkunft:** Nebenbefund aus FM-0. "
                 f"{NACHTRAG} **Ergebnis:** Der Knopf speichert jetzt. "
                 "Test `tests/test_x.py` (3 Faelle). |")
    assert z.count("Nebenbefund aus FM-0.") == 1
    assert z.count("Nachtrag aus Fragment") == 1
    assert not _frag(repo, "FM-1").exists(), "Fragment nicht entfernt"


def test_zweiter_lauf_haengt_nichts_an(tmp_path):
    repo = _repo(tmp_path, {"FM-1": "ID: FM-1\nStatus: done\n\n" + FREITEXT})
    _sammeln(repo)
    nach_eins = (repo / "BACKLOG.md").read_text(encoding="utf-8")
    # Dasselbe Fragment noch einmal (z. B. wieder aufgetaucht): keine Aenderung.
    _frag(repo, "FM-1").write_text(
        "ID: FM-1\nStatus: done\n\n" + FREITEXT, encoding="utf-8")
    aus = _sammeln(repo)
    assert (repo / "BACKLOG.md").read_text(encoding="utf-8") == nach_eins
    assert not [z for z in aus if "Nachtrag FM-1" in z], aus
    assert [z for z in aus if "Freitext FM-1: steht schon" in z], aus


def test_alles_schon_da_kein_nachtrag(tmp_path):
    repo = _repo(tmp_path, {"FM-1": "ID: FM-1\nStatus: done\n\n"
                                       "**Herkunft:**   Nebenbefund\naus FM-0.\n"})
    _sammeln(repo)
    assert _zeile(repo, "FM-1") == ("| FM-1 | P2 | done | **Alt** | "
                                     "**Herkunft:** Nebenbefund aus FM-0. |")


def test_spaltenzahl_bleibt_fuenf_und_vier_spalten(tmp_path):
    repo = _repo(tmp_path, {
        "FM-2": "ID: FM-2\nStatus: teils\n\n**Geliefert:** a.\n\n**Offen:** b.\n",
        "QA-7": "ID: QA-7\nStatus: done\n\nNeu geliefert.\n"})
    _sammeln(repo)
    z2, q7 = _zeile(repo, "FM-2"), _zeile(repo, "QA-7")
    assert _spalten(z2) == 5 and _spalten(q7) == 4
    assert z2.endswith(f"| z {NACHTRAG} **Geliefert:** a. **Offen:** b. |")
    assert q7 == f"| QA-7 | P2 | done | **Vier Spalten** Text. {NACHTRAG} Neu geliefert. |"


def test_senkrechter_strich_wird_escaped():
    """Ein Fragment mit '|' lehnt --pruefen ab; die Funktion escapt trotzdem,
    damit ein Freitext nie die Zeile zerschneidet."""
    f = bs.Fragment(id="FM-2", status="teils", datei="FM-2.md",
                    details="a | b", freitext="**Ergebnis:** a | b\nund\nc")
    neu, protokoll, fertig, fehler = bs.baue_backlog(TABELLE, [f], {}, HEUTE)
    assert not fehler
    z = next(z for z in neu.split("\n") if z.startswith("| FM-2 |"))
    assert z == f"| FM-2 | P3 | teils | **Anders** | z {NACHTRAG} **Ergebnis:** a \\| b und c |"
    assert _spalten(z) == 5
    # Idempotent auch mit escaptem Strich.
    neu2, *_ = bs.baue_backlog(neu, [f], {}, HEUTE)
    assert neu2 == neu


def test_dry_run_und_pruefen_schreiben_nichts_zeigen_aber_den_nachtrag(tmp_path):
    repo = _repo(tmp_path, {"FM-2": "ID: FM-2\nStatus: teils\n\nGeliefert: Teil 1.\n"})
    for art in ({"dry_run": True}, {"pruefen": True}):
        aus = _sammeln(repo, **art)
        treffer = [z for z in aus if "Nachtrag FM-2" in z]
        assert len(treffer) == 1 and "Geliefert: Teil 1." in treffer[0], aus
        assert (repo / "BACKLOG.md").read_text(encoding="utf-8") == TABELLE
        assert _frag(repo, "FM-2").is_file()


def test_review_wird_done_und_bekommt_nachtrag(tmp_path):
    repo = _repo(tmp_path, {"FM-2": "ID: FM-2\nStatus: review\n"
                                       "Status-Notiz: Teil 1\n\nLiefertext.\n"})
    _sammeln(repo, pr=1234)
    assert _zeile(repo, "FM-2") == (
        f"| FM-2 | P3 | done ({HEUTE}, [PR #1234](https://github.com/ixamgames-droid/"
        f"lightos/pull/1234)) — Teil 1 | **Anders** | z {NACHTRAG} Liefertext. |")


def test_neue_zeile_unveraendert_ohne_nachtrag(tmp_path):
    repo = _repo(tmp_path, {"FM-3": "ID: FM-3\nPrioritaet: P2\nStatus: todo\n"
                                       "Titel: Neu\n\n**Was:** etwas.\n"})
    _sammeln(repo)
    assert _zeile(repo, "FM-3") == "| FM-3 | P2 | todo | **Neu** | **Was:** etwas. |"


def test_absaetze_teilt_an_marken_und_leerzeilen():
    assert bs.absaetze("**A:** eins. **B (x):** zwei\n**C:** drei\n\nvier\nfuenf") == [
        "**A:** eins.", "**B (x):** zwei", "**C:** drei", "vier fuenf"]
    assert bs.absaetze("") == []


# ------------------------------------------------- Gegenpruefung TOOL-28

def test_fett_zitierte_marke_mitten_im_satz_teilt_nicht():
    """„**Herkunft:** eigen“ mitten im Satz ist Zitat, kein neuer Absatz:
    sonst haengt nur ein abgerissenes Satzstueck an (FM-77)."""
    assert bs.absaetze("**A:** Die Zeile „**Herkunft:** eigen“ steht.") == [
        "**A:** Die Zeile „**Herkunft:** eigen“ steht."]
    zeile = "| FM-2 | P3 | todo | **Anders** | Die Zeile „**Herkunft:** eigen“ steht. |"
    fehlend, zurueck = bs.fehlende_absaetze(
        zeile, "**A:** Die Zeile „**Herkunft:** eigen“ steht.")
    assert fehlend == ["**A:** Die Zeile „**Herkunft:** eigen“ steht."]
    assert zurueck == []


def test_abgewandelter_absatz_mit_vorhandener_marke_wird_nur_gemeldet(tmp_path):
    """Steht die Marke (``**Test:**``) schon in der Zeile, ist ein abweichender
    Fragment-Absatz meist eine alte Fassung: nicht still anhaengen, melden."""
    backlog = TABELLE.replace("| z |", "| z **Test:** `t1.py`. |")
    repo = _repo(tmp_path, {"FM-2": "ID: FM-2\nStatus: done\n\n"
                                       "**Test:** `t1.py`, `t2.py`.\n**Neu:** x.\n"},
                 backlog=backlog)
    aus = _sammeln(repo, dry_run=True)
    hinweis = [z for z in aus if "Hinweis FM-2" in z]
    assert len(hinweis) == 1 and "**Test:**" in hinweis[0] and "t2.py" in hinweis[0], aus
    aus = _sammeln(repo)
    z = _zeile(repo, "FM-2")
    assert z.count("**Test:**") == 1, z
    assert z.endswith(f"**Test:** `t1.py`. {NACHTRAG} **Neu:** x. |"), z
    assert [x for x in aus if "Hinweis FM-2" in x], aus
    assert not [x for x in aus if "steht schon vollstaendig" in x], aus


def test_nur_zurueckgehaltenes_gilt_nicht_als_vollstaendig(tmp_path):
    backlog = TABELLE.replace("| z |", "| z **Offen:** nichts mehr. |")
    repo = _repo(tmp_path, {"FM-2": "ID: FM-2\nStatus: done\n\n**Offen:** Schritt 3.\n"},
                 backlog=backlog)
    aus = _sammeln(repo)
    assert _zeile(repo, "FM-2").endswith("| z **Offen:** nichts mehr. |")
    assert [x for x in aus if "Hinweis FM-2" in x], aus
    assert not [x for x in aus if "steht schon vollstaendig" in x], aus


def test_leerzeilen_absaetze_ueber_den_echten_lesepfad(tmp_path):
    """Ohne Marken trennt nur die Leerzeile — das muss auch ueber
    ``lies_fragment``/``sammeln`` ankommen, nicht nur in ``absaetze()``."""
    repo = _repo(tmp_path, {"FM-2": "ID: FM-2\nStatus: done\n\nz\n\nzweiter\nTeil.\n"})
    _sammeln(repo)
    assert _zeile(repo, "FM-2") == f"| FM-2 | P3 | done | **Anders** | z {NACHTRAG} zweiter Teil. |"


def test_doppelter_leerraum_in_der_zeile_gilt_als_vorhanden(tmp_path):
    backlog = TABELLE.replace("| z |", "| z  und   mehr. |")
    repo = _repo(tmp_path, {"FM-2": "ID: FM-2\nStatus: done\n\nz und mehr.\n"},
                 backlog=backlog)
    _sammeln(repo)
    assert _zeile(repo, "FM-2") == "| FM-2 | P3 | done | **Anders** | z  und   mehr. |"


def test_zeile_endet_auf_escaptem_strich_ohne_abschluss():
    z = "| X-1 | P2 | todo | **T** | a \\|"
    assert bs.mit_nachtrag(z, ["**Neu:** y"], HEUTE) == f"{z} {NACHTRAG} **Neu:** y"


def test_escapter_backslash_vor_dem_schlussstrich():
    """``C:\\\\|``: der Backslash ist escaped, der Strich schliesst die Zelle —
    der Nachtrag gehoert davor, sonst entsteht eine Spalte mehr."""
    z = "| X-1 | P2 | todo | **T** | Pfad C:\\\\|"
    neu = bs.mit_nachtrag(z, ["**Neu:** y"], HEUTE)
    assert neu == f"| X-1 | P2 | todo | **T** | Pfad C:\\\\ {NACHTRAG} **Neu:** y |"
