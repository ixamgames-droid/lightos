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
        self.show_db = _schreibe(self.app / "current_show.db")
        _schreibe(self.app / "midi_mappings.json")
        _schreibe(self.app / "universes.json")
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
