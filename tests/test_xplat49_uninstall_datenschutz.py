"""XPLAT-49: der Uninstaller loescht eigene Shows nicht ohne ausdruecklichen Auftrag.

Befund: ``uninstall.py --yes`` raeumte den ganzen App-Datenordner ab - dort
liegen seit UXT-11 standardmaessig die eigenen Shows (``<AppData>/LightOS/shows``).
``--keep-shows`` schuetzte nur ``shows/`` im Programmordner, die Rueckfrage
nannte die Shows nicht, und ``data/`` ging samt der versionierten
``data/controller_library`` weg.

Regeln, die hier festgehalten sind:
* ``--yes`` fasst den App-Datenordner NIE an; das geht nur mit ``--purge``.
* ``--purge`` ohne ``--yes`` stellt eine Sicherheitsfrage (Vorgabe: Nein),
  die die eigenen Shows nennt.
* ``--keep-shows`` spart bei ``--purge`` auch ``<AppData>/shows`` aus.
* ``--keep-appdata`` gewinnt gegen ``--purge``.
* ``data/controller_library`` bleibt immer stehen.
* ``--dry-run`` aendert nichts und nennt genau die Pfade, die der echte Lauf
  entfernt.

Alle Laeufe arbeiten auf einem Temp-Programmordner und einem Temp-App-Ordner;
der echte Datenordner und der echte Desktop werden nie beruehrt.
"""
from __future__ import annotations

import itertools
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SCHALTER = ("--yes", "--purge", "--keep-shows", "--keep-appdata", "--keep-venv")
KOMBINATIONEN = [
    tuple(s for s, an in zip(SCHALTER, bits) if an)
    for bits in itertools.product((False, True), repeat=len(SCHALTER))
]


def _schreibe(pfad: Path, text: str = "x") -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, encoding="utf-8")
    return pfad


def _show_db(pfad: Path, patch: int = 1) -> Path:
    """Eine Show-DB wie von der App angelegt; ``patch`` = Zahl der Geraete."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    if pfad.exists():
        pfad.unlink()
    con = sqlite3.connect(pfad)
    con.execute("create table patched_fixtures (id integer primary key, name text)")
    con.execute("create table fixture_groups (id integer primary key, name text)")
    con.executemany("insert into patched_fixtures (name) values (?)",
                    [(f"Geraet {i}",) for i in range(patch)])
    con.commit()
    con.close()
    return pfad


def _dateien(*wurzeln: Path) -> set[str]:
    gefunden: set[str] = set()
    for wurzel in wurzeln:
        if wurzel.exists():
            gefunden |= {str(p) for p in wurzel.rglob("*") if p.is_file()}
    return gefunden


class Umgebung:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "programm"
        self.app = tmp / "appdaten" / "LightOS"
        self.desktop = tmp / "desktop"
        self.verknuepfung = _schreibe(self.desktop / "LightOS.lnk")
        _schreibe(self.repo / "venv" / "bin" / "python")
        _schreibe(self.repo / "data" / "current_show.db")
        _schreibe(self.repo / "data" / "universes.json")
        _schreibe(self.repo / "data" / "_backup" / "alt.db")
        self.vorlage = _schreibe(
            self.repo / "data" / "controller_library" / "apc_mini.json")
        self.repo_show = _schreibe(self.repo / "shows" / "alt.lshow")
        _schreibe(self.repo / "src" / "core" / "__pycache__" / "a.pyc")
        _schreibe(self.repo / "src" / "core" / "a.py")
        _schreibe(self.repo / "install_manifest.json", json.dumps(
            {"version": "t", "arch": "x64", "shortcut": str(self.verknuepfung)}))
        self.eigene_show = _schreibe(self.app / "shows" / "meine.lshow")
        # Der App-Ordner traegt ECHTE Staende: nur die zaehlen als uebernommen.
        self.show_db = _show_db(self.app / "current_show.db")
        _schreibe(self.app / "midi_mappings.json", '[{"cc": 1}]')
        _schreibe(self.app / "universes.json", '[{"id": 1}]')
        # ... und zwar DIESELBEN wie data/: ein anderer Stand ohne Eintrag im
        # Umzugs-Marker gaelte als noch nicht entschieden (s. TestAndererStand).
        shutil.copyfile(self.show_db, self.repo / "data" / "current_show.db")
        _schreibe(self.repo / "data" / "universes.json", '[{"id": 1}]')
        _schreibe(self.app / "fixtures.db")
        _schreibe(self.app / "snaps" / "s1.json")
        _schreibe(self.app / "stages" / "b1.json")
        _schreibe(self.app / "logs" / "crash.log")

    def dateien(self) -> set[str]:
        return _dateien(self.tmp)


@pytest.fixture
def umg(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    import uninstall as U
    u = Umgebung(tmp_path)
    monkeypatch.setattr(U, "ROOT", u.repo)
    monkeypatch.setattr(U, "APPDATA_DIR", u.app)
    monkeypatch.setattr(U, "VENV_DIR", u.repo / "venv")
    monkeypatch.setattr(U, "MANIFEST_PATH", u.repo / "install_manifest.json")
    # Der Ersatzpfad fuer die Verknuepfung fragt sonst den echten Desktop ab.
    monkeypatch.setenv("HOME", str(tmp_path / "heim"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "heim"))
    u.U = U
    return u


def _lauf(umg, monkeypatch, capsys, *schalter, antwort=None):
    """Startet main(); ``antwort`` = None heisst: jede Rueckfrage ist ein Fehler."""
    fragen: list[tuple[str, bool]] = []

    def frage(prompt, default=True):
        fragen.append((prompt, default))
        if antwort is None:
            raise AssertionError(f"unerwartete Rueckfrage: {prompt}")
        return antwort(prompt) if callable(antwort) else antwort

    monkeypatch.setattr(umg.U, "confirm", frage)
    monkeypatch.setattr(sys, "argv", ["uninstall.py", *schalter])
    umg.U.main()
    return capsys.readouterr().out, fragen


def _angekuendigt(ausgabe: str) -> set[Path]:
    return {Path(z.split("WUERDE LOESCHEN: ", 1)[1].strip())
            for z in ausgabe.splitlines() if "WUERDE LOESCHEN: " in z}


def _unter(datei: str, pfade: set[Path]) -> bool:
    d = Path(datei)
    return any(d == p or p in d.parents for p in pfade)


class TestOhneRueckfrage:
    """--yes: kein einziger Tastendruck, also auch keine stille Datenvernichtung."""

    def test_yes_laesst_den_app_datenordner_stehen(self, umg, monkeypatch, capsys):
        vorher = _dateien(umg.app)
        out, fragen = _lauf(umg, monkeypatch, capsys, "--yes")
        assert fragen == []
        assert _dateien(umg.app) == vorher
        assert umg.eigene_show.exists()
        assert "--purge" in out, "der Lauf muss sagen, wie man die Daten doch loescht"

    def test_yes_laesst_shows_im_programmordner_stehen(self, umg, monkeypatch, capsys):
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert umg.repo_show.exists()

    def test_yes_entfernt_die_installation(self, umg, monkeypatch, capsys):
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not (umg.repo / "venv").exists()
        assert not (umg.repo / "install_manifest.json").exists()
        assert not umg.verknuepfung.exists()
        assert not (umg.repo / "src" / "core" / "__pycache__").exists()
        assert (umg.repo / "src" / "core" / "a.py").exists()

    def test_data_verliert_nur_nutzerdateien(self, umg, monkeypatch, capsys):
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert umg.vorlage.exists(), "data/controller_library ist versioniert"
        assert _dateien(umg.repo / "data") == {str(umg.vorlage)}

    def test_purge_yes_loescht_den_app_datenordner(self, umg, monkeypatch, capsys):
        out, fragen = _lauf(umg, monkeypatch, capsys, "--purge", "--yes")
        assert fragen == []
        assert not umg.app.exists()
        assert "eigene Shows" in out

    def test_purge_keep_shows_spart_die_eigenen_shows_aus(self, umg, monkeypatch, capsys):
        out, _ = _lauf(umg, monkeypatch, capsys, "--purge", "--yes", "--keep-shows")
        assert _dateien(umg.app) == {str(umg.eigene_show)}
        assert umg.repo_show.exists()
        assert str(umg.app / "shows") in out, "der Ort der behaltenen Shows wird genannt"

    def test_keep_appdata_gewinnt_gegen_purge(self, umg, monkeypatch, capsys):
        vorher = _dateien(umg.app)
        _lauf(umg, monkeypatch, capsys, "--purge", "--yes", "--keep-appdata")
        assert _dateien(umg.app) == vorher


class TestRueckfragen:
    def test_ohne_purge_wird_nach_dem_app_ordner_nicht_gefragt(self, umg, monkeypatch, capsys):
        vorher = _dateien(umg.app)
        out, fragen = _lauf(umg, monkeypatch, capsys, antwort=True)
        assert not [f for f in fragen if str(umg.app) in f[0]]
        assert _dateien(umg.app) == vorher
        assert "--purge" in out

    def test_purge_fragt_nach_und_nennt_was_dort_liegt(self, umg, monkeypatch, capsys):
        out, fragen = _lauf(umg, monkeypatch, capsys, "--purge", "--keep-venv",
                            antwort=False)
        app = [f for f in fragen if str(umg.app) in f[0]]
        assert len(app) == 1, fragen
        text, vorgabe = app[0]
        assert vorgabe is False, "App-Ordner darf nicht per Enter weg sein"
        for wort in ("eigene Shows", "Show-DB", "MIDI-Mappings", "Bibliothek",
                     "Snaps", "Buehnen", "Logs"):
            assert wort in text + out, wort
        assert "eigene Shows" in text
        assert umg.eigene_show.exists() and umg.show_db.exists()

    def test_purge_mit_ja_loescht(self, umg, monkeypatch, capsys):
        _lauf(umg, monkeypatch, capsys, "--purge", antwort=True)
        assert not umg.app.exists()

    def test_purge_keep_shows_sagt_in_der_frage_dass_shows_bleiben(self, umg, monkeypatch, capsys):
        _, fragen = _lauf(umg, monkeypatch, capsys, "--purge", "--keep-shows",
                          antwort=True)
        app = [f for f in fragen if str(umg.app) in f[0]]
        assert len(app) == 1
        assert "bleiben" in app[0][0]
        assert umg.eigene_show.exists()
        assert not umg.show_db.exists()

    def test_shows_frage_im_programmordner_bleibt_vorgabe_nein(self, umg, monkeypatch, capsys):
        _, fragen = _lauf(umg, monkeypatch, capsys, antwort=False)
        shows = [f for f in fragen if f[0].startswith("shows/")]
        assert len(shows) == 1 and shows[0][1] is False
        assert "eigene" in shows[0][0].lower()

    def test_data_frage_verspricht_die_vorlagen_zu_behalten(self, umg, monkeypatch, capsys):
        _, fragen = _lauf(umg, monkeypatch, capsys, antwort=False)
        data = [f for f in fragen if f[0].startswith("data/")]
        assert len(data) == 1
        assert "controller_library" in data[0][0] and "bleib" in data[0][0]


class TestSchreibweise:
    """Windows/macOS: ``Shows`` und ``shows`` sind derselbe Ordner."""

    def test_keep_shows_schuetzt_auch_gross_geschriebenes_shows(
            self, umg, monkeypatch, capsys):
        (umg.app / "shows").rename(umg.app / "Shows")
        show = umg.app / "Shows" / "meine.lshow"
        out, _ = _lauf(umg, monkeypatch, capsys, "--purge", "--yes",
                       "--keep-shows", "--dry-run")
        assert not [p for p in _angekuendigt(out) if p.name == "Shows"], out
        _lauf(umg, monkeypatch, capsys, "--purge", "--yes", "--keep-shows")
        assert _dateien(umg.app) == {str(show)}

    def test_vorlagen_ordner_bleibt_auch_anders_geschrieben(
            self, umg, monkeypatch, capsys):
        (umg.repo / "data" / "controller_library").rename(
            umg.repo / "data" / "Controller_Library")
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "Controller_Library" / "apc_mini.json").exists()


class TestNochNichtUebernommen:
    """data/ ist nur dann "alter Stand", wenn der App-Ordner die Kopie schon hat.

    Der Datenumzug XPLAT-44 kopiert erst beim ersten Start nach dem Update.
    Lief LightOS seitdem nie, liegt die Show-DB NUR in data/.
    """

    def _ohne_kopie(self, umg):
        umg.show_db.unlink()
        _schreibe(umg.repo / "data" / "current_show.db-wal")
        return (umg.repo / "data" / "current_show.db",
                umg.repo / "data" / "current_show.db-wal")

    def test_yes_laesst_die_einzige_show_db_stehen(self, umg, monkeypatch, capsys):
        db, wal = self._ohne_kopie(umg)
        out, fragen = _lauf(umg, monkeypatch, capsys, "--yes")
        assert fragen == []
        assert db.exists() and wal.exists(), "einziger Stand der Show-DB geloescht"
        assert "current_show.db" in out and "BEHALTEN" in out
        # was schon uebernommen ist, geht weiterhin weg
        assert not (umg.repo / "data" / "universes.json").exists()
        assert not (umg.repo / "data" / "_backup").exists()

    def test_auch_interaktiv_und_mit_purge(self, umg, monkeypatch, capsys):
        db, wal = self._ohne_kopie(umg)
        _lauf(umg, monkeypatch, capsys, "--purge", antwort=True)
        assert db.exists() and wal.exists()

    def test_leere_kopie_zaehlt_nicht_als_uebernommen(self, umg, monkeypatch, capsys):
        umg.show_db.write_bytes(b"")
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "current_show.db").exists()

    def test_trockenlauf_nennt_die_geschuetzte_datei_nicht(
            self, umg, monkeypatch, capsys):
        db, wal = self._ohne_kopie(umg)
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes", "--dry-run")
        assert not {db, wal} & _angekuendigt(out)

    def test_uebernommene_dateien_werden_wie_bisher_entfernt(
            self, umg, monkeypatch, capsys):
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not (umg.repo / "data" / "current_show.db").exists()


class TestLeeresZielIstKeineKopie:
    """Codex-Befund (P1): ein frisch angelegtes, inhaltlich leeres Ziel ist
    groesser als 0 Byte, aber kein Nutzerstand - der Umzug (``datenumzug``)
    wuerde es noch ersetzen. Der Uninstaller muss genauso urteilen, sonst
    loescht ``--yes`` den einzigen echten Stand in ``data/``."""

    @pytest.mark.parametrize("leer", ["[]", "{}", "null", " \n", "[]\n"])
    def test_leeres_json_im_app_ordner_schuetzt_den_alten_stand(
            self, umg, monkeypatch, capsys, leer):
        (umg.app / "universes.json").write_text(leer, encoding="utf-8")
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "universes.json").exists()
        assert "universes.json" in out and "BEHALTEN" in out

    def test_frisch_angelegte_leere_show_db_schuetzt_den_alten_stand(
            self, umg, monkeypatch, capsys):
        _show_db(umg.show_db, patch=0)
        assert umg.show_db.stat().st_size > 0
        wal = _schreibe(umg.repo / "data" / "current_show.db-wal")
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "current_show.db").exists()
        assert wal.exists()
        assert "current_show.db" in out and "BEHALTEN" in out

    def test_trockenlauf_nennt_den_geschuetzten_stand_nicht(
            self, umg, monkeypatch, capsys):
        (umg.app / "universes.json").write_text("[]", encoding="utf-8")
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes", "--dry-run")
        assert umg.repo / "data" / "universes.json" not in _angekuendigt(out)

    def test_unlesbares_ziel_ist_keine_kopie(self, umg, monkeypatch, capsys):
        umg.show_db.write_bytes(b"kein sqlite")
        (umg.app / "universes.json").write_text("{kaputt", encoding="utf-8")
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "current_show.db").exists()
        assert (umg.repo / "data" / "universes.json").exists()

    def test_urteil_deckt_sich_mit_dem_umzug(self, umg, monkeypatch, capsys):
        """Was der Uninstaller stehen laesst, uebernimmt der naechste Start."""
        from src.core import datenumzug
        monkeypatch.delenv(datenumzug.ENV_AUS, raising=False)
        monkeypatch.delenv("LIGHTOS_UNIVERSES_JSON", raising=False)
        (umg.app / "universes.json").write_text("[]", encoding="utf-8")
        _schreibe(umg.repo / "data" / "universes.json", '[{"id": 7}]')
        _lauf(umg, monkeypatch, capsys, "--yes")
        erg = datenumzug.uebernehme_alte_daten(
            ziel_dir=str(umg.app), quellen=[str(umg.repo / "data")],
            dateien=["universes.json"], log=lambda _t: None)
        assert [n for n, _ in erg.kopiert] == ["universes.json"], vars(erg)
        assert json.loads((umg.app / "universes.json").read_text("utf-8")) == [{"id": 7}]

    def _marker(self, umg, **felder):
        from src.core import datenumzug
        _schreibe(umg.app / datenumzug.MARKER_NAME, json.dumps(felder))
        return datenumzug._schluessel(str(umg.repo / "data"))

    def test_marker_erledigt_bewusst_geleertes_ziel_gilt_als_uebernommen(
            self, umg, monkeypatch, capsys):
        from src.core import datenumzug
        quelle = datenumzug._schluessel(str(umg.repo / "data"))
        self._marker(umg, quellen_erledigt=[quelle], kopiert=["universes.json"])
        (umg.app / "universes.json").write_text("[]", encoding="utf-8")
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not (umg.repo / "data" / "universes.json").exists()

    def test_marker_teil_erledigt_gilt_je_datei(self, umg, monkeypatch, capsys):
        from src.core import datenumzug
        quelle = datenumzug._schluessel(str(umg.repo / "data"))
        self._marker(umg, teil_erledigt={quelle: ["universes.json"]})
        (umg.app / "universes.json").unlink()
        _show_db(umg.show_db, patch=0)
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not (umg.repo / "data" / "universes.json").exists()
        assert (umg.repo / "data" / "current_show.db").exists()

    def test_marker_eines_anderen_quellordners_zaehlt_nicht(
            self, umg, monkeypatch, capsys):
        self._marker(umg, quellen_erledigt=[str(umg.tmp / "woanders" / "data")],
                     kopiert=["universes.json"])
        (umg.app / "universes.json").write_text("[]", encoding="utf-8")
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "universes.json").exists()

    def test_pruefung_veraendert_den_app_ordner_nicht(self, umg, monkeypatch, capsys):
        _show_db(umg.show_db, patch=0)
        vorher = {p: Path(p).read_bytes() for p in _dateien(umg.app)}
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert {p: Path(p).read_bytes() for p in _dateien(umg.app)} == vorher


class TestAndererStand:
    """Review: liegt im App-Ordner ein ANDERER Nutzerstand, ueber den der Umzug
    fuer diesen Programmordner nie entschieden hat (zweite Installation, die
    den App-Ordner schon gefuellt hat; LightOS lief hier seit dem Update nie),
    dann ist ``data/`` der einzige Ort dieses Stands. Der naechste Start wuerde
    den Konflikt zeigen und die Uebernahme anbieten - ``--yes`` darf dem nicht
    zuvorkommen."""

    def _anderer_stand(self, umg):
        _show_db(umg.repo / "data" / "current_show.db", patch=3)
        _schreibe(umg.repo / "data" / "universes.json", '[{"id": 2}]')

    def test_anderer_stand_ohne_marker_bleibt(self, umg, monkeypatch, capsys):
        self._anderer_stand(umg)
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "current_show.db").exists()
        assert (umg.repo / "data" / "universes.json").exists()
        assert "BEHALTEN" in out

    def test_trockenlauf_nennt_ihn_nicht(self, umg, monkeypatch, capsys):
        self._anderer_stand(umg)
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes", "--dry-run")
        assert not {umg.repo / "data" / "current_show.db",
                    umg.repo / "data" / "universes.json"} & _angekuendigt(out)

    def test_quittierter_konflikt_gilt_als_entschieden(self, umg, monkeypatch, capsys):
        from src.core import datenumzug
        self._anderer_stand(umg)
        quelle = datenumzug._schluessel(str(umg.repo / "data"))
        _schreibe(umg.app / datenumzug.MARKER_NAME, json.dumps(
            {"teil_erledigt": {quelle: ["universes.json"]}}))
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not (umg.repo / "data" / "universes.json").exists()
        assert (umg.repo / "data" / "current_show.db").exists()

    def test_erledigter_quellordner_gilt_als_entschieden(self, umg, monkeypatch, capsys):
        from src.core import datenumzug
        self._anderer_stand(umg)
        quelle = datenumzug._schluessel(str(umg.repo / "data"))
        _schreibe(umg.app / datenumzug.MARKER_NAME, json.dumps(
            {"quellen_erledigt": [quelle]}))
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not (umg.repo / "data" / "current_show.db").exists()
        assert not (umg.repo / "data" / "universes.json").exists()

    def test_marker_eines_anderen_programmordners_entscheidet_nichts(
            self, umg, monkeypatch, capsys):
        from src.core import datenumzug
        self._anderer_stand(umg)
        _schreibe(umg.app / datenumzug.MARKER_NAME, json.dumps(
            {"quellen_erledigt": [str(umg.tmp / "zweiter-checkout" / "data")]}))
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert (umg.repo / "data" / "current_show.db").exists()

    def test_urteil_deckt_sich_mit_dem_umzug(self, umg, monkeypatch, capsys):
        """Was stehen bleibt, meldet der naechste Start als Konflikt."""
        from src.core import datenumzug
        monkeypatch.delenv(datenumzug.ENV_AUS, raising=False)
        monkeypatch.delenv("LIGHTOS_UNIVERSES_JSON", raising=False)
        self._anderer_stand(umg)
        _lauf(umg, monkeypatch, capsys, "--yes")
        erg = datenumzug.uebernehme_alte_daten(
            ziel_dir=str(umg.app), quellen=[str(umg.repo / "data")],
            dateien=["universes.json"], log=lambda _t: None)
        assert [n for n, _ in erg.konflikte] == ["universes.json"], vars(erg)


class TestFremdeVerknuepfung:
    """Befund vom Zweit-PC: ohne Manifest merkte ``--yes`` ``LightOS.lnk`` vom
    Desktop vor, egal wohin sie zeigt - bei zwei Checkouts die der ANDEREN
    Installation. Geloescht wird nur, was das Manifest nennt oder was in den
    eigenen Programmordner zeigt. Die Aufloesung des Ziels ist austauschbar."""

    def _ohne_manifest(self, umg, monkeypatch, ziele):
        (umg.repo / "install_manifest.json").unlink()
        lnk = _schreibe(umg.tmp / "heim" / "Desktop" / "LightOS.lnk")
        gefragt: list[Path] = []

        def aufloesen(pfad):
            gefragt.append(Path(pfad))
            return ziele

        monkeypatch.setattr(umg.U, "verknuepfung_ziele", aufloesen)
        return lnk, gefragt

    def test_verknuepfung_einer_anderen_installation_bleibt(
            self, umg, monkeypatch, capsys):
        anderes = umg.tmp / "zweiter-checkout"
        lnk, gefragt = self._ohne_manifest(umg, monkeypatch, (
            str(anderes / "venv" / "Scripts" / "pythonw.exe"), str(anderes)))
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes")
        assert gefragt == [lnk]
        assert lnk.exists(), "Verknuepfung der anderen Installation geloescht"
        assert "BEHALTEN" in out and "andere Installation" in out

    def test_auch_der_trockenlauf_nennt_sie_nicht(self, umg, monkeypatch, capsys):
        lnk, _ = self._ohne_manifest(umg, monkeypatch, (str(umg.tmp / "zweiter"),))
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes", "--dry-run")
        assert lnk not in _angekuendigt(out)

    def test_eigene_verknuepfung_ohne_manifest_wird_entfernt(
            self, umg, monkeypatch, capsys):
        lnk, _ = self._ohne_manifest(umg, monkeypatch, (
            str(umg.repo / "venv" / "Scripts" / "pythonw.exe"), str(umg.repo)))
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not lnk.exists()

    def test_nachbarordner_mit_gleichem_anfang_ist_nicht_der_eigene(
            self, umg, monkeypatch, capsys):
        nachbar = umg.repo.parent / (umg.repo.name + "-alt")
        lnk, _ = self._ohne_manifest(umg, monkeypatch, (str(nachbar / "venv"),))
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert lnk.exists()

    def test_nicht_aufloesbares_ziel_bleibt(self, umg, monkeypatch, capsys):
        lnk, _ = self._ohne_manifest(umg, monkeypatch, ())
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes")
        assert lnk.exists()
        assert "BEHALTEN" in out

    def test_ohne_pywin32_und_ausserhalb_von_windows_wird_nichts_geraten(
            self, umg, monkeypatch, capsys):
        """Die echte Aufloesung liefert hier nichts - also bleibt die Datei."""
        (umg.repo / "install_manifest.json").unlink()
        lnk = _schreibe(umg.tmp / "heim" / "Desktop" / "LightOS.lnk")
        if sys.platform == "win32":
            pytest.skip("unter Windows loest PowerShell die Test-Datei nicht auf")
        assert umg.U.verknuepfung_ziele(lnk) == ()
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert lnk.exists()

    def test_manifest_nennt_die_verknuepfung_ziel_nicht_ermittelbar(
            self, umg, monkeypatch, capsys):
        monkeypatch.setattr(umg.U, "verknuepfung_ziele", lambda _pfad: ())
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not umg.verknuepfung.exists()

    def test_manifest_nennt_sie_und_sie_zeigt_in_den_eigenen_ordner(
            self, umg, monkeypatch, capsys):
        monkeypatch.setattr(umg.U, "verknuepfung_ziele",
                            lambda _pfad: (str(umg.repo / "venv" / "pythonw.exe"),
                                           str(umg.repo)))
        _lauf(umg, monkeypatch, capsys, "--yes")
        assert not umg.verknuepfung.exists()

    def test_manifest_nennt_sie_aber_zweite_installation_hat_sie_ueberschrieben(
            self, umg, monkeypatch, capsys):
        """Zwei Installationen MIT Manifest teilen sich ``LightOS.lnk``: die
        zweite ueberschreibt die Datei, das Manifest der ersten nennt sie weiter."""
        anderes = umg.tmp / "zweiter-checkout"
        monkeypatch.setattr(umg.U, "verknuepfung_ziele",
                            lambda _pfad: (str(anderes / "venv" / "pythonw.exe"),
                                           str(anderes)))
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes")
        assert umg.verknuepfung.exists(), "Verknuepfung der anderen Installation geloescht"
        assert "BEHALTEN" in out and "andere Installation" in out
        out, _ = _lauf(umg, monkeypatch, capsys, "--yes", "--dry-run")
        assert umg.verknuepfung not in _angekuendigt(out)

    def test_nein_zur_verknuepfung_laesst_sie_stehen(self, umg, monkeypatch, capsys):
        _lauf(umg, monkeypatch, capsys, "--keep-venv",
              antwort=lambda frage: "Verknuepfung" not in frage)
        assert umg.verknuepfung.exists()


@pytest.mark.parametrize("schalter", KOMBINATIONEN, ids=lambda s: " ".join(s) or "-")
@pytest.mark.parametrize("antwort", [True, False], ids=["ja", "nein"])
class TestAlleKombinationen:
    def test_dry_run_aendert_nichts_und_sagt_genau_was_wegfaellt(
            self, umg, monkeypatch, capsys, schalter, antwort):
        vorher = umg.dateien()
        out, _ = _lauf(umg, monkeypatch, capsys, *schalter, "--dry-run",
                       antwort=antwort)
        assert umg.dateien() == vorher, "--dry-run hat etwas geloescht"
        angekuendigt = _angekuendigt(out)

        _lauf(umg, monkeypatch, capsys, *schalter, antwort=antwort)
        weg = vorher - umg.dateien()
        nicht_angekuendigt = {d for d in weg if not _unter(d, angekuendigt)}
        assert not nicht_angekuendigt, "geloescht, aber im Trockenlauf nicht genannt"
        geblieben = {d for d in umg.dateien() if _unter(d, angekuendigt)}
        assert not geblieben, "im Trockenlauf genannt, aber nicht geloescht"

    def test_schutzregeln(self, umg, monkeypatch, capsys, schalter, antwort):
        app_vorher = _dateien(umg.app)
        _lauf(umg, monkeypatch, capsys, *schalter, antwort=antwort)
        yes = "--yes" in schalter
        zugestimmt = yes or antwort
        purge = "--purge" in schalter and "--keep-appdata" not in schalter

        assert umg.vorlage.exists()
        if not (purge and zugestimmt):
            assert _dateien(umg.app) == app_vorher
        elif "--keep-shows" in schalter:
            assert _dateien(umg.app) == {str(umg.eigene_show)}
        else:
            assert not umg.app.exists()
        if yes or "--keep-shows" in schalter or not antwort:
            assert umg.repo_show.exists()
        if "--keep-venv" in schalter:
            assert (umg.repo / "venv" / "bin" / "python").exists()


class TestDoku:
    def test_docstring_nennt_nur_optionen_die_es_gibt(self):
        sys.path.insert(0, str(ROOT))
        import uninstall as U
        doc = U.__doc__ or ""
        assert "--shows " not in doc and "--shows)" not in doc
        assert "--purge" in doc
        assert "alles ohne Rueckfrage entfernen" not in doc

    def test_install_md_hat_die_tabelle_welche_option_was_loescht(self):
        text = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        assert "Alles sofort entfernen" not in text
        assert "--keep-appdata  # Snapshots, Stages behalten" not in text
        zeilen = [z for z in text.splitlines() if z.startswith("| `")]
        for option in ("--yes", "--purge", "--purge --keep-shows",
                       "--keep-shows", "--keep-appdata", "--dry-run"):
            assert any(z.startswith(f"| `{option}`") for z in zeilen), option
        assert "eigene Shows" in text
        assert "data/controller_library" in text
