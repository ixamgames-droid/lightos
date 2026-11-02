"""STAB-40: liegengebliebene ``lightos_wegwerf_*``-Ordner werden weggeraeumt —
aber nur, was sicher niemandem mehr gehoert, und NIE der echte Datenordner.

**Warum.** Seit STAB-39 bekommt jeder Prozess ohne Freigabe (Probelauf aus
einer Agent-Shell, Probeskripte) einen Wegwerf-Ordner in ``%TEMP%``, den ein
``atexit``-rmtree am Ende loeschen soll. Unter Windows sind dann aber Show-DB,
Sperrdatei und Logs noch offen, und offene Dateien laesst Windows nicht
loeschen — gemessen am 01.11.2026 blieben je Probelauf ~2,2 MB liegen. Jetzt
raeumt jeder neue Wegwerf-Ordner die alten weg.

Geprueft wird gegen einen eigenen Temp-Ordner (``tempfile.tempdir``), nie
gegen den echten Temp-Bereich des Rechners.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import pytest

from src.core import paths

REPO = Path(__file__).resolve().parents[1]
ALT = 2 * 3600          # zwei Stunden — ueber dem Mindestalter von einer Stunde


def _altern(ordner: Path, alter: float) -> None:
    t = time.time() - alter
    for wurzel, dirs, dateien in os.walk(ordner):
        for name in dirs + dateien:
            os.utime(os.path.join(wurzel, name), (t, t))
    os.utime(ordner, (t, t))


def _ordner(temp: Path, name: str, alter: float = ALT) -> Path:
    o = temp / name
    for rel in ("LightOS/current_show.db", "LightOS/logs/lightos.log", "LightOS/crash.log"):
        p = o / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    _altern(o, alter)
    return o


def _echter_ordner_setzen(monkeypatch, basis: Path) -> None:
    """Lenkt ``regulaerer_app_data_dir()`` nach ``basis``/…/LightOS."""
    if sys.platform == "win32":
        monkeypatch.setenv("APPDATA", str(basis))
    elif sys.platform == "darwin":
        monkeypatch.setenv("HOME", str(basis))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(basis))


@pytest.fixture
def temp(tmp_path, monkeypatch):
    t = tmp_path / "temp"
    t.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(t))
    # der echte Datenordner liegt wie im Leben AUSSERHALB des Temp-Bereichs
    _echter_ordner_setzen(monkeypatch, tmp_path / "home")
    return t


def _aufraeumen(**kw):
    return [Path(p).name for p in paths.alte_wegwerf_ordner_aufraeumen(**kw)]


# ── was weg darf ─────────────────────────────────────────────────────────────

def test_alter_freier_ordner_wird_entfernt(temp):
    o = _ordner(temp, "lightos_wegwerf_alt")
    assert _aufraeumen() == ["lightos_wegwerf_alt"]
    assert not o.exists()
    assert list(temp.iterdir()) == [], list(temp.iterdir())


def test_toter_besitzer_haelt_den_ordner_nicht(temp):
    kind = subprocess.Popen([sys.executable, "-c", "pass"])
    kind.wait()
    o = _ordner(temp, "lightos_wegwerf_tot")
    (o / paths.WEGWERF_BESITZER).write_text(str(kind.pid), encoding="ascii")
    _altern(o, ALT)
    assert _aufraeumen() == ["lightos_wegwerf_tot"]


# ── was bleibt ───────────────────────────────────────────────────────────────

def test_junger_ordner_bleibt(temp):
    o = _ordner(temp, "lightos_wegwerf_jung", alter=60)
    assert _aufraeumen() == []
    assert o.exists()


def test_eine_frische_datei_haelt_den_ordner(temp):
    o = _ordner(temp, "lightos_wegwerf_herz")
    (o / "LightOS" / "last_alive.txt").write_text("jetzt", encoding="ascii")
    assert _aufraeumen() == []
    assert o.exists()


def test_der_eigene_ordner_bleibt(temp):
    o = _ordner(temp, "lightos_wegwerf_eigen")
    assert _aufraeumen(eigener=str(o)) == []
    assert o.exists()


def test_fremde_namen_bleiben(temp):
    anderer = _ordner(temp, "anderer_ordner")
    datei = temp / "lightos_wegwerf_datei"
    datei.write_bytes(b"x")
    _altern(temp, ALT)
    assert _aufraeumen() == []
    assert anderer.exists() and datei.exists()


def test_lebender_besitzer_haelt_den_ordner(temp):
    o = _ordner(temp, "lightos_wegwerf_lebt")
    (o / paths.WEGWERF_BESITZER).write_text(str(os.getpid()), encoding="ascii")
    _altern(o, ALT)
    assert _aufraeumen() == []
    assert o.exists()


def test_gehaltene_sperre_haelt_den_ordner(temp):
    from src.core.single_instance import acquire_instance_lock
    o = _ordner(temp, "lightos_wegwerf_gesperrt")
    h = acquire_instance_lock(str(o / "LightOS" / "lightos.instance.lock"))
    assert h is not None
    try:
        _altern(o, ALT)
        assert _aufraeumen() == []
        assert (o / "LightOS" / "current_show.db").exists()
    finally:
        h.close()
    assert _aufraeumen() == ["lightos_wegwerf_gesperrt"]


@pytest.mark.skipif(sys.platform != "win32", reason="offene Dateien sperren nur unter Windows")
def test_offene_datei_haelt_den_ordner_ganz(temp):
    o = _ordner(temp, "lightos_wegwerf_offen")
    f = open(o / "LightOS" / "current_show.db", "rb")
    try:
        assert _aufraeumen() == []
        # nichts halb geloescht: auch die NICHT offenen Dateien sind noch da
        assert (o / "LightOS" / "logs" / "lightos.log").exists()
        assert (o / "LightOS" / "crash.log").exists()
    finally:
        f.close()
    assert _aufraeumen() == ["lightos_wegwerf_offen"]


def test_link_wird_nicht_verfolgt(temp, tmp_path):
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    (ziel / "wichtig.txt").write_text("bleibt", encoding="utf-8")
    link = temp / "lightos_wegwerf_link"
    try:
        if sys.platform == "win32":
            import _winapi
            _winapi.CreateJunction(str(ziel), str(link))
        else:
            os.symlink(ziel, link, target_is_directory=True)
    except (OSError, AttributeError) as exc:
        pytest.skip(f"Link nicht anlegbar: {exc}")
    _altern(ziel, ALT)
    try:
        assert _aufraeumen() == []
        assert (ziel / "wichtig.txt").read_text(encoding="utf-8") == "bleibt"
    finally:
        if sys.platform == "win32":
            os.rmdir(link)          # nur den Verweis, nie das Ziel
        else:
            os.unlink(link)


# ── der echte Datenordner: nie ───────────────────────────────────────────────

def test_echter_datenordner_in_einem_kandidaten_wird_nie_getroffen(temp, monkeypatch):
    kandidat = temp / "lightos_wegwerf_echt"
    _echter_ordner_setzen(monkeypatch, kandidat)
    echt = Path(paths.regulaerer_app_data_dir())
    assert str(echt).startswith(str(kandidat)), echt
    echt.mkdir(parents=True)
    (echt / "current_show.db").write_bytes(b"echte Show")
    _altern(kandidat, ALT)
    assert _aufraeumen() == []
    assert (echt / "current_show.db").read_bytes() == b"echte Show"


def test_temp_im_echten_datenordner_wird_nie_angefasst(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _echter_ordner_setzen(monkeypatch, home)
    echt = Path(paths.regulaerer_app_data_dir())
    temp = echt / "tmp"
    temp.mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    o = _ordner(temp, "lightos_wegwerf_drin")
    assert _aufraeumen() == []
    assert o.exists()


# ── im Ablauf: der Probelauf-Start raeumt auf, ein Probeskript nicht ─────────

def _kind(tmp_path: Path, temp: Path, zeilen: str):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("LIGHTOS_")}
    env.update({"TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp),
                "HOME": str(home), "USERPROFILE": str(home),
                "APPDATA": str(home / "AppData" / "Roaming"),
                "XDG_DATA_HOME": str(home / ".local" / "share"),
                "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    env.pop("PYTHONPATH", None)
    code = (f"import json, sys\nsys.path.insert(0, {str(REPO)!r})\n"
            "from src.core import paths\n" + textwrap.dedent(zeilen))
    r = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr
    erg = json.loads([z for z in r.stdout.splitlines() if z.startswith("ERGEBNIS ")][-1][9:])
    return erg, r.stderr


def test_probelauf_start_raeumt_alte_wegwerf_ordner_weg(tmp_path):
    """Wie ``main.py`` im Probelauf: erst der eigene Wegwerf-Ordner, dann
    ``probelauf_aufraeumen()``."""
    temp = tmp_path / "temp"
    temp.mkdir()
    alt = _ordner(temp, "lightos_wegwerf_vonfrueher")
    jung = _ordner(temp, "lightos_wegwerf_laeuftnoch", alter=30)
    erg, err = _kind(tmp_path, temp, """
        eigen = paths.app_data_dir()
        weg = paths.probelauf_aufraeumen()
        print("ERGEBNIS " + json.dumps({"eigen": eigen, "weg": weg}))
    """)
    assert str(Path(erg["eigen"])).startswith(str(temp)), erg
    assert [Path(p).name for p in erg["weg"]] == ["lightos_wegwerf_vonfrueher"], erg
    assert not alt.exists(), "alter Wegwerf-Ordner blieb liegen"
    assert jung.exists(), "ein junger Ordner darf nicht weg"
    assert "STAB-40" in err and "1 alte" in err, err


def test_probeskript_ohne_probelauf_start_sieht_temp_nicht_durch(tmp_path):
    """Ein Skript, das nur ``app_data_dir()`` fragt, zahlt die Durchsicht
    eines vollen Temp-Ordners nicht (gemessen ~60 ms bei 14 647 Eintraegen)."""
    temp = tmp_path / "temp"
    temp.mkdir()
    alt = _ordner(temp, "lightos_wegwerf_vonfrueher")
    erg, err = _kind(tmp_path, temp, """
        print("ERGEBNIS " + json.dumps(paths.app_data_dir()))
    """)
    assert alt.exists()
    assert "STAB-40" not in err, err


def test_ohne_eigenen_wegwerf_ordner_tut_probelauf_aufraeumen_nichts(temp, monkeypatch):
    """Echte App / Vorgabe per LIGHTOS_DATEN_ORDNER: kein eigener Ordner,
    kein Aufraeumen."""
    o = _ordner(temp, "lightos_wegwerf_alt")
    monkeypatch.setattr(paths, "_WEGWERF_BASIS", None)
    assert paths.probelauf_aufraeumen() == []
    assert o.exists()


def test_main_raeumt_nach_der_sperre_auf():
    """``main()`` ruft ``probelauf_aufraeumen`` — nach der Einzelinstanz-Sperre
    (ein abgewiesener Zweitstart raeumt nichts)."""
    import ast
    baum = ast.parse((REPO / "main.py").read_text(encoding="utf-8"))
    haupt = next(n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    aufrufe = [(n.lineno, n.func.id) for n in ast.walk(haupt)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    zeilen = {name: nr for nr, name in sorted(aufrufe, reverse=True)}
    assert "probelauf_aufraeumen" in zeilen, "main() raeumt im Probelauf nicht auf"
    assert zeilen["acquire_instance_lock"] < zeilen["probelauf_aufraeumen"]
