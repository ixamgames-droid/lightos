"""LIZ-1: Lizenzpruefung (Kern ohne Qt).

Alle Tests arbeiten mit einem EIGENEN, hier erzeugten Schluesselpaar — der
oeffentliche Schluessel des Programms wird per Monkeypatch ersetzt. Der echte
Signierschluessel und echte Lizenzdateien kommen in der Suite nicht vor.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from src.core import ed25519, lizenz

GEHEIM = bytes(range(32))                      # Test-Schluessel, kein Geheimnis
HEUTE = dt.date(2026, 10, 12)


@pytest.fixture(autouse=True)
def _testschluessel(monkeypatch, tmp_path):
    monkeypatch.setattr(lizenz, "OEFFENTLICHER_SCHLUESSEL",
                        ed25519.oeffentlicher_schluessel(GEHEIM))
    monkeypatch.delenv(lizenz.ENV_PFAD, raising=False)
    daten = tmp_path / "daten" / "LightOS"
    monkeypatch.setattr(lizenz, "app_data_dir", lambda: str(daten))
    return daten


def _schreibe(pfad, daten) -> str:
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as fh:
        fh.write(daten if isinstance(daten, str) else lizenz.als_text(daten))
    return str(pfad)


def _lizenz(bis=dt.date(2027, 1, 31), name="Testerin", **kw):
    return lizenz.stelle_aus(GEHEIM, name, bis, **kw)


# ── Zustaende ────────────────────────────────────────────────────────────────

def test_gueltig_mit_name_und_datum(tmp_path):
    p = _schreibe(tmp_path / "a.lic", _lizenz())
    s = lizenz.pruefe_datei(p, HEUTE)
    assert s.zustand == lizenz.GUELTIG and s.ist_gueltig
    assert s.name == "Testerin" and s.gueltig_bis == dt.date(2027, 1, 31)
    assert "Testerin" in s.text() and "31.01.2027" in s.text()


def test_unbefristet(tmp_path):
    s = lizenz.pruefe_datei(_schreibe(tmp_path / "a.lic", _lizenz(bis=None)), HEUTE)
    assert s.ist_gueltig and s.unbefristet and s.tage_bis_ablauf(HEUTE) is None
    assert "unbefristet" in s.text()
    assert not s.laeuft_bald_ab(HEUTE)


def test_letzter_tag_zaehlt_noch_danach_abgelaufen(tmp_path):
    p = _schreibe(tmp_path / "a.lic", _lizenz(bis=dt.date(2026, 10, 12)))
    assert lizenz.pruefe_datei(p, dt.date(2026, 10, 12)).ist_gueltig
    s = lizenz.pruefe_datei(p, dt.date(2026, 10, 13))
    assert s.zustand == lizenz.ABGELAUFEN
    assert s.gueltig_bis == dt.date(2026, 10, 12) and s.name == "Testerin"
    assert "12.10.2026" in s.text() and "abgelaufen" in s.text()


def test_fehlt(tmp_path):
    s = lizenz.pruefe_datei(tmp_path / "gibtesnicht.lic", HEUTE)
    assert s.zustand == lizenz.FEHLT and not s.ist_gueltig and s.name == ""


def test_veraenderter_name_ist_ungueltig(tmp_path):
    d = _lizenz()
    d["name"] = "Jemand anderes"
    s = lizenz.pruefe_datei(_schreibe(tmp_path / "a.lic", d), HEUTE)
    assert s.zustand == lizenz.UNGUELTIG and s.name == ""


def test_verlaengertes_datum_ist_ungueltig(tmp_path):
    d = _lizenz(bis=dt.date(2026, 1, 1))
    d["gueltig_bis"] = "2099-01-01"
    s = lizenz.pruefe_datei(_schreibe(tmp_path / "a.lic", d), HEUTE)
    assert s.zustand == lizenz.UNGUELTIG


def test_zusatzfeld_bricht_die_signatur(tmp_path):
    d = _lizenz()
    d["extra"] = 1
    assert lizenz.pruefe_datei(_schreibe(tmp_path / "a.lic", d),
                               HEUTE).zustand == lizenz.UNGUELTIG


def test_fremder_schluessel_ist_ungueltig(tmp_path):
    fremd = lizenz.stelle_aus(bytes([7]) * 32, "Fremd", None)
    s = lizenz.pruefe_datei(_schreibe(tmp_path / "a.lic", fremd), HEUTE)
    assert s.zustand == lizenz.UNGUELTIG and "Signatur" in s.grund


@pytest.mark.parametrize("inhalt", [
    "", "kein json", "[1, 2, 3]", "42", "null", '{"format": 1}',
    '{"format": 1, "name": "x", "kennung": "y"}',
    '{"format": 1, "name": "x", "kennung": "y", "signatur": "???"}',
    '{"format": 1, "name": "x", "kennung": "y", "signatur": "AAAA", '
    '"gueltig_bis": "morgen"}',
    '{"format": 1, "name": 5, "kennung": [], "signatur": {}}',
])
def test_beschaedigte_datei_ist_ungueltig_ohne_ausnahme(tmp_path, inhalt):
    s = lizenz.pruefe_datei(_schreibe(tmp_path / "a.lic", inhalt), HEUTE)
    assert s.zustand == lizenz.UNGUELTIG and s.grund


def test_binaermuell_und_zu_grosse_datei(tmp_path):
    p = tmp_path / "a.lic"
    p.write_bytes(b"\xff\xfe\x00\x81" * 50)
    assert lizenz.pruefe_datei(p, HEUTE).zustand == lizenz.UNGUELTIG
    p.write_bytes(b"x" * 200_000)
    assert lizenz.pruefe_datei(p, HEUTE).zustand == lizenz.UNGUELTIG


@pytest.mark.parametrize("fmt", [2, 0, "1", None, True, 1.5])
def test_falsches_format(tmp_path, fmt):
    d = _lizenz()
    d["format"] = fmt
    s = lizenz.pruefe_datei(_schreibe(tmp_path / "a.lic", d), HEUTE)
    assert s.zustand == lizenz.UNGUELTIG
    assert "Lizenzformat" in s.grund or "Signatur" in s.grund


def test_pruefe_daten_mit_unsinn_wirft_nie():
    for unsinn in (None, 3, "x", [], {"format": 1, "name": "a", "kennung": "b",
                                       "signatur": 9}):
        assert lizenz.pruefe_daten(unsinn, HEUTE).zustand == lizenz.UNGUELTIG


def test_datei_mit_bom_und_ordner_als_pfad(tmp_path):
    p = tmp_path / "a.lic"
    p.write_bytes(b"\xef\xbb\xbf" + lizenz.als_text(_lizenz()).encode("utf-8"))
    assert lizenz.pruefe_datei(p, HEUTE).ist_gueltig
    assert lizenz.pruefe_datei(tmp_path, HEUTE).zustand == lizenz.FEHLT


# ── Suchorte ─────────────────────────────────────────────────────────────────

def test_suchorte_datenordner_und_umgebungsvariable(_testschluessel, tmp_path):
    std = os.path.join(str(_testschluessel), "lightos-lizenz.lic")
    assert lizenz.standard_pfad() == std
    assert lizenz.suchorte({}) == [std]
    assert lizenz.suchorte({"LIGHTOS_LIZENZ": "/x/y.lic"}) == ["/x/y.lic", std]


def test_pruefe_findet_die_datei_im_datenordner(_testschluessel):
    assert lizenz.pruefe(HEUTE, {}).zustand == lizenz.FEHLT
    _schreibe(lizenz.standard_pfad(), _lizenz())
    assert lizenz.pruefe(HEUTE, {}).ist_gueltig


def test_umgebungsvariable_hat_vorrang_gueltige_gewinnt(tmp_path):
    abgelaufen = _schreibe(tmp_path / "alt.lic", _lizenz(bis=dt.date(2020, 1, 1)))
    env = {"LIGHTOS_LIZENZ": abgelaufen}
    assert lizenz.pruefe(HEUTE, env).zustand == lizenz.ABGELAUFEN
    _schreibe(lizenz.standard_pfad(), _lizenz(name="Im Datenordner"))
    s = lizenz.pruefe(HEUTE, env)
    assert s.ist_gueltig and s.name == "Im Datenordner"


def test_abgelaufen_schlaegt_ungueltig_schlaegt_fehlt(tmp_path):
    kaputt = _schreibe(tmp_path / "kaputt.lic", "{")
    assert lizenz.pruefe(HEUTE, {"LIGHTOS_LIZENZ": kaputt}).zustand == lizenz.UNGUELTIG
    _schreibe(lizenz.standard_pfad(), _lizenz(bis=dt.date(2020, 1, 1)))
    assert lizenz.pruefe(HEUTE, {"LIGHTOS_LIZENZ": kaputt}).zustand == lizenz.ABGELAUFEN


def test_pruefe_haengt_an_der_pfadschicht(monkeypatch, tmp_path):
    """Ohne Monkeypatch folgt der Suchort ``paths.app_data_dir()`` — also dem
    von der conftest umgelenkten Test-Datenordner, nie dem echten."""
    monkeypatch.undo()
    from src.core.paths import app_data_dir
    assert lizenz.standard_pfad() == os.path.join(app_data_dir(), lizenz.DATEINAME)


# ── Installieren ─────────────────────────────────────────────────────────────

def test_installiere_kopiert_gueltige_datei(tmp_path):
    quelle = _schreibe(tmp_path / "irgendwo" / "meine.lic", _lizenz())
    status, fehler = lizenz.installiere(quelle, HEUTE)
    assert fehler == "" and status.ist_gueltig
    assert status.pfad == lizenz.standard_pfad()
    assert os.path.isfile(lizenz.standard_pfad())
    assert lizenz.pruefe(HEUTE, {}).ist_gueltig


@pytest.mark.parametrize("art", ["kaputt", "abgelaufen", "fehlt"])
def test_installiere_kopiert_nichts_ungueltiges(tmp_path, art):
    alt = _schreibe(lizenz.standard_pfad(), _lizenz(name="Bestand"))
    vorher = open(alt, encoding="utf-8").read()
    if art == "kaputt":
        quelle = _schreibe(tmp_path / "x.lic", "{}")
    elif art == "abgelaufen":
        quelle = _schreibe(tmp_path / "x.lic", _lizenz(bis=dt.date(2020, 1, 1)))
    else:
        quelle = str(tmp_path / "nichtda.lic")
    status, fehler = lizenz.installiere(quelle, HEUTE)
    assert not status.ist_gueltig and fehler
    assert open(alt, encoding="utf-8").read() == vorher


def test_installiere_dieselbe_datei_ist_kein_fehler():
    ziel = _schreibe(lizenz.standard_pfad(), _lizenz())
    status, fehler = lizenz.installiere(ziel, HEUTE)
    assert status.ist_gueltig and fehler == ""


# ── Startlogik (reine Funktionen) ────────────────────────────────────────────

GUT = lizenz.Lizenzstatus(lizenz.GUELTIG, name="T", kennung="ABCDEFGHJKLM")
OHNE = lizenz.Lizenzstatus(lizenz.FEHLT)


def test_abfrage_nur_ohne_gueltige_lizenz():
    assert lizenz.abfrage_noetig(GUT, env={}, module={}) is False
    for zustand in (lizenz.FEHLT, lizenz.ABGELAUFEN, lizenz.UNGUELTIG):
        assert lizenz.abfrage_noetig(lizenz.Lizenzstatus(zustand),
                                     env={}, module={}) is True


def test_keine_abfrage_bei_selbsttest_und_diagnose():
    assert lizenz.abfrage_noetig(OHNE, selbsttest=True, env={}, module={}) is False
    assert lizenz.abfrage_noetig(OHNE, diagnose=True, env={}, module={}) is False


def test_testlauf_schalter_wirkt_nur_unter_pytest():
    schalter = {"LIGHTOS_LIZENZ_TESTLAUF": "1"}
    # Schalter allein (ausserhalb von pytest): wirkungslos -> es wird gefragt
    assert lizenz.testlauf(schalter, {}) is False
    assert lizenz.abfrage_noetig(OHNE, env=schalter, module={}) is True
    # pytest im Prozess
    assert lizenz.abfrage_noetig(OHNE, env=schalter, module={"pytest": 1}) is False
    # von einem Test gestarteter Kindprozess
    kind = dict(schalter, PYTEST_CURRENT_TEST="tests/x.py::t (call)")
    assert lizenz.abfrage_noetig(OHNE, env=kind, module={}) is False
    # pytest ohne den Schalter: es wird gefragt
    assert lizenz.abfrage_noetig(OHNE, env={"PYTEST_CURRENT_TEST": "x"},
                                 module={"pytest": 1}) is True
    assert lizenz.testlauf({"LIGHTOS_LIZENZ_TESTLAUF": "0",
                            "PYTEST_CURRENT_TEST": "x"}, {"pytest": 1}) is False


def test_die_suite_selbst_laeuft_mit_dem_schalter():
    """tests/conftest.py setzt den Schalter — sonst bliebe jeder Test, der
    ``main.main()`` durchlaeuft, am Dialog haengen."""
    assert lizenz.testlauf() is True


def test_startzeile_nennt_urheber_aber_nicht_den_namen():
    s = lizenz.Lizenzstatus(lizenz.GUELTIG, name="Vorname Nachname",
                            kennung="ABCDEFGHJKLM", gueltig_bis=dt.date(2027, 1, 31))
    zeile = lizenz.start_zeile(s)
    assert "ixamgames-droid" in zeile and "github.com/ixamgames-droid/lightos" in zeile
    assert "Vorname" not in zeile and "Nachname" not in zeile
    assert "ABCDEF…" in zeile and "ABCDEFGHJKLM" not in zeile
    assert "2027-01-31" in zeile
    assert "fehlt" in lizenz.start_zeile(OHNE)
    abgel = lizenz.Lizenzstatus(lizenz.ABGELAUFEN, name="Vorname Nachname",
                                kennung="ABCDEFGHJKLM", gueltig_bis=dt.date(2026, 1, 1))
    assert "Vorname" not in lizenz.start_zeile(abgel)


def test_ablaufhinweis_ab_14_tagen():
    def status(bis):
        return lizenz.Lizenzstatus(lizenz.GUELTIG, name="T", kennung="K", gueltig_bis=bis)
    assert lizenz.ablauf_hinweis(status(HEUTE + dt.timedelta(days=15)), HEUTE) == ""
    text = lizenz.ablauf_hinweis(status(HEUTE + dt.timedelta(days=14)), HEUTE)
    assert "läuft am 26.10.2026 ab" in text
    assert lizenz.ablauf_hinweis(status(HEUTE), HEUTE)
    assert lizenz.ablauf_hinweis(status(None), HEUTE) == ""
    assert lizenz.ablauf_hinweis(OHNE, HEUTE) == ""


# ── Ausstellen ───────────────────────────────────────────────────────────────

def test_ausgestellte_lizenz_hat_alle_felder():
    d = _lizenz(hinweis="Probe")
    assert set(d) == {"format", "kennung", "name", "gueltig_bis",
                      "ausgestellt_am", "hinweis", "signatur"}
    assert d["format"] == 1 and d["hinweis"] == "Probe"
    assert len(d["kennung"]) == 12 and d["kennung"] != _lizenz()["kennung"]
    assert json.loads(lizenz.als_text(d)) == d
    with pytest.raises(ValueError):
        lizenz.stelle_aus(GEHEIM, "  ", None)


def test_kanonisch_haengt_nicht_an_der_feldreihenfolge():
    d = _lizenz()
    umgedreht = dict(reversed(list(d.items())))
    assert lizenz.kanonisch(d) == lizenz.kanonisch(umgedreht)
    assert lizenz.pruefe_daten(umgedreht, HEUTE).ist_gueltig


def test_lizenztext_ist_die_mitgelieferte_datei():
    text = lizenz.lizenztext()
    assert "ixamgames-droid" in text and "Alle Rechte vorbehalten" in text


def test_modul_kommt_ohne_qt_aus():
    import subprocess
    import sys
    code = ("import sys; import src.core.lizenz; "
            "print(any(m.startswith('PySide6') for m in sys.modules))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.stdout.strip() == "False", r.stderr
