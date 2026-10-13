"""LIZ-1: Urhebervermerk in gespeicherten Shows und im Diagnosepaket."""
from __future__ import annotations

import datetime as dt
import json
import os
import zipfile

import pytest

from src.core import diagnose_log, ed25519, lizenz
from src.core.show import show_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _show_json(pfad) -> tuple[bytes, dict]:
    with zipfile.ZipFile(pfad) as zf:
        roh = zf.read("show.json")
    return roh, json.loads(roh.decode("utf-8"))


@pytest.fixture
def leere_show():
    show_file.reset_show()
    yield
    show_file.reset_show()


def test_gespeicherte_show_traegt_den_vermerk_im_kopf(leere_show, tmp_path):
    ziel = tmp_path / "a.lshow"
    show_file.save_show(ziel)
    _roh, daten = _show_json(ziel)
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as fh:
        import re
        version = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', fh.read(), re.M).group(1)
    vermerk = daten["erstellt_mit"]
    assert vermerk["programm"] == "LightOS"
    assert vermerk["urheber"] == "ixamgames-droid"
    assert vermerk["quelle"] == "https://github.com/ixamgames-droid/lightos"
    assert vermerk["version"] == version
    # im Kopf: direkt hinter version und name
    assert list(daten)[:3] == ["version", "name", "erstellt_mit"]


def test_vermerk_ist_deterministisch_speichern_bleibt_bytegleich(leere_show, tmp_path):
    a, b = tmp_path / "a.lshow", tmp_path / "b.lshow"
    show_file.save_show(a)
    show_file.save_show(b)
    assert _show_json(a)[0] == _show_json(b)[0]
    # Laden -> Speichern: der Vermerk steht wieder genau so im Kopf (ob der
    # REST der Datei dabei bytegleich bleibt, pruefen die Persistenz-Tests).
    ok = show_file.load_show(a)
    assert ok is True or (isinstance(ok, tuple) and ok[0])
    c = tmp_path / "c.lshow"
    show_file.save_show(c)
    kopf_a, kopf_c = _show_json(a)[0], _show_json(c)[0]
    ende = kopf_a.index(b'"patch"')
    assert kopf_c[:ende] == kopf_a[:ende]
    assert _show_json(c)[1]["erstellt_mit"] == _show_json(a)[1]["erstellt_mit"]


def test_vermerk_enthaelt_nichts_persoenliches(leere_show, tmp_path, monkeypatch):
    """Kein Lizenznehmer, kein Rechner, keine Uhrzeit in der Show-Datei."""
    monkeypatch.setattr(lizenz, "pruefe", lambda *a, **k: lizenz.Lizenzstatus(
        lizenz.GUELTIG, name="Vorname Nachname", kennung="ABCDEFGHJKLM"))
    ziel = tmp_path / "a.lshow"
    show_file.save_show(ziel)
    roh, daten = _show_json(ziel)
    assert b"Vorname" not in roh and b"ABCDEFGHJKLM" not in roh
    assert set(daten["erstellt_mit"]) >= {"programm", "urheber", "quelle", "version"}
    assert str(dt.date.today().year) not in json.dumps(daten["erstellt_mit"])


def test_vermerk_beruehrt_den_aenderungsvergleich_nicht(leere_show):
    """Der Vermerk ist kein Show-Inhalt: er steht nicht in den Daten, aus denen
    Fingerabdruck und „ungespeicherte Aenderungen“ entstehen."""
    from src.core.app_state import get_state
    assert "erstellt_mit" not in show_file._show_daten(get_state(), [])
    assert "erstellt_mit" not in (show_file._block_abdruecke() or {})


def _alte_show(pfad, extra=None):
    """Eine Show, wie sie eine Version VOR dem Vermerk geschrieben hat."""
    from src.core.app_state import get_state
    daten = show_file._show_daten(get_state(), [])
    daten["name"] = "Alt ohne Vermerk"
    daten.update(extra or {})
    assert "erstellt_mit" not in daten or extra
    with zipfile.ZipFile(pfad, "w") as zf:
        zf.writestr("show.json", json.dumps(daten, indent=2, ensure_ascii=False))
    return daten


def test_alte_show_ohne_vermerk_laedt(leere_show, tmp_path):
    from src.core.app_state import get_state
    alt = tmp_path / "alt.lshow"
    _alte_show(alt)
    ok = show_file.load_show(alt)
    assert ok is True or (isinstance(ok, tuple) and ok[0]), ok
    assert get_state().show_name == "Alt ohne Vermerk"
    neu = tmp_path / "neu.lshow"
    show_file.save_show(neu)
    _roh, daten = _show_json(neu)
    assert daten["name"] == "Alt ohne Vermerk"
    assert daten["erstellt_mit"]["urheber"] == "ixamgames-droid"


@pytest.mark.parametrize("vermerk", [
    {"programm": "LightOS", "urheber": "jemand", "version": "0.1"},
    "kaputt", None, 7, [],
])
def test_show_mit_fremdem_oder_kaputtem_vermerk_laedt(leere_show, tmp_path, vermerk):
    """Das Feld wird beim Laden nicht ausgewertet — egal, was drinsteht."""
    from src.core.app_state import get_state
    alt = tmp_path / "alt.lshow"
    _alte_show(alt, {"erstellt_mit": vermerk})
    ok = show_file.load_show(alt)
    assert ok is True or (isinstance(ok, tuple) and ok[0]), ok
    assert get_state().show_name == "Alt ohne Vermerk"


# ── Diagnosepaket ────────────────────────────────────────────────────────────

GEHEIM = bytes(range(3, 35))


def test_diagnosepaket_traegt_vermerk_und_lizenzstatus_ohne_namen(tmp_path, monkeypatch):
    monkeypatch.setattr(lizenz, "OEFFENTLICHER_SCHLUESSEL",
                        ed25519.oeffentlicher_schluessel(GEHEIM))
    datei = tmp_path / "l.lic"
    datei.write_text(lizenz.als_text(lizenz.stelle_aus(
        GEHEIM, "Vorname Nachname", dt.date(2099, 1, 1), kennung="ABCDEFGHJKLM")),
        encoding="utf-8")
    monkeypatch.setenv(lizenz.ENV_PFAD, str(datei))
    ziel = diagnose_log.erstelle_diagnosepaket(str(tmp_path / "d.zip"), "9.8.7", ROOT)
    with zipfile.ZipFile(ziel) as zf:
        namen = zf.namelist()
        texte = {n: zf.read(n).decode("utf-8") for n in namen}
    for name in ("LIESMICH.txt", "systeminfo.txt"):
        assert "rstellt mit LightOS 9.8.7 von ixamgames-droid" in texte[name], name
        assert "https://github.com/ixamgames-droid/lightos" in texte[name]
    info = texte["systeminfo.txt"]
    assert "Lizenz: gueltig (bis 2099-01-01, Kennung ABCDEF…)" in info
    assert "Urheber: Copyright (c) 2026 ixamgames-droid" in info
    alles = "\n".join(texte.values())
    assert "Vorname" not in alles and "Nachname" not in alles
    assert "ABCDEFGHJKLM" not in alles
    assert not any(n.lower().endswith(".lic") for n in namen)


def test_diagnosepaket_ohne_lizenz(tmp_path, monkeypatch):
    monkeypatch.delenv(lizenz.ENV_PFAD, raising=False)
    monkeypatch.setattr(lizenz, "app_data_dir", lambda: str(tmp_path / "leer"))
    text = diagnose_log.systeminfo_text("1.2.3", ROOT)
    assert "Lizenz: fehlt" in text
    assert "rstellt mit LightOS 1.2.3 von ixamgames-droid" in text


def test_kopfblock_des_sitzungslogs_nennt_den_urheber():
    kopf = diagnose_log.kopfblock("1.2.3", ROOT)
    assert "Urheber: Copyright (c) 2026 ixamgames-droid" in kopf
    assert "github.com/ixamgames-droid/lightos" in kopf
