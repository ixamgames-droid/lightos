"""LIZ-4: oben im Windows-Bundle liegt die neueste Microsoft-Laufzeit.

**Befund (19.10.2026, Bundle von #1101):** ``VCRUNTIME140.dll`` und
``VCRUNTIME140_1.dll`` lagen dreimal im Bundle — oben (``_internal\\``) in
14.42.34438 aus der Python-Installation, unter ``PySide6\\`` und
``shiboken6\\`` in 14.44.35211. Windows laedt je Name nur EINE Datei; beim
``--selbsttest`` war es die obere. Qt/PySide6 ist mit 14.44 gebaut und lief
gegen 14.42 — Microsoft verlangt eine Laufzeit, die mindestens so neu ist wie
das neueste Werkzeug, mit dem ein Teil gebaut wurde. Entscheidung des
Projektinhabers (20.10.2026): die neueste Fassung nach oben.

Was dieser Test zusammenhaelt:

* ``vc_laufzeit.angleichen`` (Bau) nimmt als obere Datei die neueste
  gleichnamige des Bundles und bricht ab, wenn oben danach etwas Aelteres
  laege oder eine Fassung nicht lesbar ist;
* ``LightOS.spec`` ruft es nach dem Qt-Filter und vor der Lizenzpruefung auf;
* ``selbsttest.pruefe_vc_laufzeit`` (gepackte exe) prueft am laufenden
  Prozess: die geladene Laufzeit kommt aus dem Programmordner und keine
  gleichnamige Datei im Bundle ist neuer.

Gebaut wird hier nichts; Fassungen und geladene Dateien werden vorgegeben.
Nur ``test_echte_dateifassung_unter_windows`` liest eine echte DLL.
"""
from __future__ import annotations

import io
import os
import sys

import pytest

from src.core import selbsttest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "packaging", "windows"))
import vc_laufzeit                                               # noqa: E402

ALT, NEU, AELTER = (14, 42, 34438), (14, 44, 35211), (14, 40, 33810)


def _lies(*teile) -> str:
    with io.open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _bundle():
    """TOC wie im echten Bau (Quellpfade sind nur Schluessel fuer die Fassung)."""
    binaries = [
        ("python312.dll", "py/python312.dll", "BINARY"),
        ("VCRUNTIME140.dll", "py/vcruntime140.dll", "BINARY"),
        ("VCRUNTIME140_1.dll", "py/vcruntime140_1.dll", "BINARY"),
        ("PySide6\\VCRUNTIME140.dll", "sp/PySide6/VCRUNTIME140.dll", "BINARY"),
        ("PySide6\\VCRUNTIME140_1.dll", "sp/PySide6/VCRUNTIME140_1.dll", "BINARY"),
        ("PySide6\\MSVCP140.dll", "sp/PySide6/MSVCP140.dll", "BINARY"),
        ("shiboken6\\VCRUNTIME140.dll", "sp/shiboken6/VCRUNTIME140.dll", "BINARY"),
        ("shiboken6\\VCRUNTIME140_1.dll", "sp/shiboken6/VCRUNTIME140_1.dll", "BINARY"),
        ("numpy.libs\\msvcp140-d64049c6e3865410a7dda6a7e9f0c575.dll",
         "sp/numpy.libs/msvcp140-d64049c6e3865410a7dda6a7e9f0c575.dll", "BINARY"),
    ]
    datas = [("licenses\\LGPL-3.0.txt", "repo/licenses/LGPL-3.0.txt", "DATA")]
    fassungen = {q: (NEU if q.startswith("sp/") else ALT) for _z, q, _t in binaries}
    fassungen["sp/numpy.libs/msvcp140-d64049c6e3865410a7dda6a7e9f0c575.dll"] = AELTER
    return binaries, datas, fassungen


def _quelle(toc, ziel):
    treffer = [e[1] for e in toc if e[0] == ziel]
    assert len(treffer) == 1, (ziel, treffer)
    return treffer[0]


# ── Bau: vc_laufzeit.angleichen ─────────────────────────────────────────────

def test_oben_kommt_die_neueste_fassung_des_bundles():
    binaries, datas, fassungen = _bundle()
    b, d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassungen.get)
    assert bericht["fehler"] == []
    # Ziel bleibt oben, nur die Quelle wechselt auf die 14.44 eines Pakets.
    for name in ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll"):
        assert fassungen[_quelle(b, name)] == NEU, name
        assert _quelle(b, name).startswith("sp/"), name
    assert bericht["oben"] == {"VCRUNTIME140.dll": "14.44.35211",
                               "VCRUNTIME140_1.dll": "14.44.35211"}
    assert len(bericht["ersetzt"]) == 2
    assert "14.42.34438 -> 14.44.35211" in bericht["ersetzt"][0]
    # Gleich viele Eintraege, die Paket-Kopien bleiben, wo sie sind.
    assert len(b) == len(binaries) and d == datas
    assert _quelle(b, "PySide6\\VCRUNTIME140.dll") == "sp/PySide6/VCRUNTIME140.dll"
    assert _quelle(b, "python312.dll") == "py/python312.dll"


def test_gegenprobe_ist_oben_schon_die_neueste_bleibt_alles():
    binaries, datas, fassungen = _bundle()
    for q in list(fassungen):
        if q.startswith("py/"):
            fassungen[q] = (14, 50, 1)
    b, d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassungen.get)
    assert (b, d) == (binaries, datas)
    assert bericht["ersetzt"] == [] and bericht["fehler"] == []
    assert bericht["oben"]["VCRUNTIME140.dll"] == "14.50.1"


def test_nur_gleichnamige_dateien_zaehlen():
    """Die umbenannte private Kopie von numpy (``msvcp140-<hash>.dll``) und
    MSVCP140 der Pakete haben mit der oberen VCRUNTIME nichts zu tun."""
    binaries, datas, fassungen = _bundle()
    fassungen["sp/PySide6/MSVCP140.dll"] = (14, 99, 1)
    fassungen["sp/numpy.libs/msvcp140-d64049c6e3865410a7dda6a7e9f0c575.dll"] = (14, 99, 2)
    _b, _d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassungen.get)
    assert set(bericht["oben"].values()) == {"14.44.35211"}
    assert bericht["fehler"] == []


def test_grossschreibung_im_namen_zaehlt_nicht():
    binaries, datas, fassungen = _bundle()
    binaries = [("vcruntime140.dll", "py/vcruntime140.dll", "BINARY")
                if e[0] == "VCRUNTIME140.dll" else e for e in binaries]
    b, _d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassungen.get)
    assert fassungen[_quelle(b, "vcruntime140.dll")] == NEU
    assert bericht["fehler"] == []


def test_neueste_liegt_als_data_eintrag_vor():
    """PyInstaller fuehrt eine DLL gelegentlich als DATA — sie zaehlt mit."""
    binaries, datas, fassungen = _bundle()
    binaries = [e for e in binaries if not e[0].startswith(("PySide6", "shiboken6"))]
    datas = datas + [("PySide6\\VCRUNTIME140.dll", "sp/PySide6/VCRUNTIME140.dll", "DATA")]
    b, _d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassungen.get)
    assert _quelle(b, "VCRUNTIME140.dll") == "sp/PySide6/VCRUNTIME140.dll"
    assert "VCRUNTIME140_1.dll" in bericht["oben"] and bericht["fehler"] == []


def test_fassung_nicht_lesbar_bricht_den_bau_ab():
    binaries, datas, fassungen = _bundle()
    fassungen["sp/shiboken6/VCRUNTIME140.dll"] = None
    b, _d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassungen.get)
    assert any("shiboken6/VCRUNTIME140.dll" in f and "keine Dateiversion" in f
               for f in bericht["fehler"]), bericht["fehler"]
    # Ohne alle Fassungen wird oben nicht geraten.
    assert _quelle(b, "VCRUNTIME140.dll") == "py/vcruntime140.dll"


def test_unlesbare_datei_bricht_den_bau_ab():
    binaries, datas, fassungen = _bundle()

    def fassung(q):
        if q == "sp/PySide6/VCRUNTIME140_1.dll":
            raise PermissionError("gesperrt")
        return fassungen[q]
    _b, _d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassung)
    assert any("PySide6/VCRUNTIME140_1.dll: nicht lesbar" in f for f in bericht["fehler"])


def test_ohne_obere_laufzeit_wird_nichts_hinzugefuegt():
    """Oben fehlt sie nur in Testbundles — ``python312.dll`` braucht sie immer."""
    binaries, datas, fassungen = _bundle()
    binaries = [e for e in binaries if "/" in e[0].replace("\\", "/")
                or not e[0].lower().startswith("vcruntime")]
    b, _d, bericht = vc_laufzeit.angleichen(binaries, datas, fassung=fassungen.get)
    assert b == binaries and bericht["oben"] == {} and bericht["fehler"] == []


def test_dateifassung_liest_die_versionsressource(tmp_path):
    """Gleiche Leseart wie die Lizenzpruefung (VS_FIXEDFILEINFO hinter
    ``VS_VERSION_INFO``) — ohne pefile, laeuft auch unter Linux."""
    kopf = "VS_VERSION_INFO\0".encode("utf-16-le") + b"\0" * 4
    ms, ls = (14 << 16) | 44, (35211 << 16) | 0
    fest = (b"\xbd\x04\xef\xfe" + (0x10000).to_bytes(4, "little")
            + ms.to_bytes(4, "little") + ls.to_bytes(4, "little"))
    dll = tmp_path / "VCRUNTIME140.dll"
    dll.write_bytes(b"MZ" + b"\0" * 64 + kopf + fest + b"\0" * 32)
    assert vc_laufzeit.dateifassung(str(dll)) == (14, 44, 35211)
    leer = tmp_path / "leer.dll"
    leer.write_bytes(b"MZ" + b"\0" * 200)
    assert vc_laufzeit.dateifassung(str(leer)) is None


def test_die_spec_gleicht_die_laufzeit_vor_der_lizenzpruefung_an():
    spec = _lies("packaging", "windows", "LightOS.spec")
    filtern = spec.index("qt_umfang.auswahl(a.binaries, a.datas)")
    angleichen = spec.index("vc_laufzeit.angleichen(a.binaries, a.datas)")
    pruefen = spec.index("fremdkomponenten.pruefe_und_schreibe(")
    packen = spec.index("pyz = PYZ(a.pure)")
    # Nach dem Qt-Filter (der die UCRT entfernt) und VOR der Lizenzpruefung —
    # die ordnet die obere Datei dann ihrer neuen Herkunft zu.
    assert filtern < angleichen < pruefen < packen
    assert 'if _vc["fehler"]:' in spec
    block = spec[angleichen:pruefen]
    assert "raise SystemExit(" in block, "Befunde brechen den Bau ab"


def test_oben_listen_im_bau_und_im_selbsttest_stimmen_ueberein():
    assert vc_laufzeit.OBEN == selbsttest.VC_LAUFZEIT_OBEN
    assert all(n == n.lower() for n in vc_laufzeit.OBEN)


# ── Selbsttest der gepackten exe: selbsttest.pruefe_vc_laufzeit ─────────────

def _programmordner(tmp_path, oben=NEU, pyside=NEU, shiboken=NEU):
    """Ein Programmordner mit drei Kopien je Name; die Fassung steht als Text
    in der Datei (``_fassung`` liest sie zurueck)."""
    wurzel = tmp_path / "_internal"
    for ordner, f in (("", oben), ("PySide6", pyside), ("shiboken6", shiboken)):
        (wurzel / ordner).mkdir(parents=True, exist_ok=True)
        for name in ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll"):
            (wurzel / ordner / name).write_text(".".join(map(str, f)), encoding="utf-8")
    return wurzel


def _fassung(pfad):
    with open(pfad, encoding="utf-8") as f:
        return tuple(int(t) for t in f.read().split("."))


def _oben_geladen(wurzel):
    return lambda name: str(wurzel / name.upper().replace(".DLL", ".dll"))


def test_selbsttest_quellbetrieb_und_andere_systeme_still(tmp_path):
    wurzel = _programmordner(tmp_path)
    assert selbsttest.pruefe_vc_laufzeit(str(wurzel), gefroren=False) == ([], None)
    assert selbsttest.pruefe_vc_laufzeit(str(wurzel), gefroren=True,
                                         plattform="linux") == ([], None)


def test_selbsttest_neueste_oben_geladen_ist_ruhig(tmp_path):
    wurzel = _programmordner(tmp_path)
    fehler, zeile = selbsttest.pruefe_vc_laufzeit(
        str(wurzel), gefroren=True, plattform="win32",
        geladen=_oben_geladen(wurzel), fassung=_fassung)
    assert fehler == []
    assert zeile == ("Microsoft-Laufzeit: vcruntime140.dll 14.44.35211 (Programmordner), "
                     "vcruntime140_1.dll 14.44.35211 (Programmordner)")


def test_selbsttest_der_befund_vom_19_10_ist_ein_fehler(tmp_path):
    """Gegenprobe: oben 14.42, in PySide6/shiboken6 14.44 — so sah das Bundle
    vor LIZ-4 aus."""
    wurzel = _programmordner(tmp_path, oben=ALT)
    fehler, _zeile = selbsttest.pruefe_vc_laufzeit(
        str(wurzel), gefroren=True, plattform="win32",
        geladen=_oben_geladen(wurzel), fassung=_fassung)
    assert len(fehler) == 4, fehler        # je Name zwei neuere Kopien
    assert all("geladen ist" in f and "14.42.34438" in f and "14.44.35211" in f
               for f in fehler)
    assert any(os.path.join("PySide6", "VCRUNTIME140.dll") in f for f in fehler)


def test_selbsttest_laufzeit_von_ausserhalb_ist_ein_fehler(tmp_path):
    """Auf einem PC ohne VC++-Redistributable gaebe es die Datei draussen nicht."""
    wurzel = _programmordner(tmp_path)
    system = tmp_path / "System32"
    system.mkdir()
    (system / "vcruntime140.dll").write_text("14.51.36247", encoding="utf-8")

    def geladen(name):
        return str(system / name) if name == "vcruntime140.dll" else str(wurzel / name)
    fehler, zeile = selbsttest.pruefe_vc_laufzeit(
        str(wurzel), gefroren=True, plattform="win32", geladen=geladen, fassung=_fassung)
    assert len(fehler) == 1 and "nicht aus dem Programmordner" in fehler[0], fehler
    assert f"(aus {system})" in zeile


def test_selbsttest_nicht_geladen_steht_nur_im_bericht(tmp_path):
    wurzel = _programmordner(tmp_path)
    fehler, zeile = selbsttest.pruefe_vc_laufzeit(
        str(wurzel), gefroren=True, plattform="win32",
        geladen=lambda name: None, fassung=_fassung)
    assert fehler == [] and zeile.count("nicht geladen") == 2


def test_selbsttest_ohne_lesbare_fassung_ist_ein_fehler(tmp_path):
    wurzel = _programmordner(tmp_path)
    fehler, _zeile = selbsttest.pruefe_vc_laufzeit(
        str(wurzel), gefroren=True, plattform="win32",
        geladen=_oben_geladen(wurzel), fassung=lambda p: None)
    assert len(fehler) == 2 and all("keine lesbare Dateiversion" in f for f in fehler)


def test_selbsttest_bericht_ruft_die_pruefung_auf(monkeypatch):
    monkeypatch.setattr(selbsttest, "pruefe_vc_laufzeit",
                        lambda: (["Laufzeit: Probe"], "Microsoft-Laufzeit: Probe"))
    code, zeilen = selbsttest.bericht()
    assert "Microsoft-Laufzeit: Probe" in zeilen
    assert "FEHLER Laufzeit: Probe" in zeilen and code == 1


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-API")
def test_echte_dateifassung_unter_windows():
    """Die Laufzeit, die dieses Python geladen hat, ist eine 14er-Fassung und
    beide Leser (Bau: Versionsressource, Selbsttest: Windows-API) sind sich
    einig."""
    pfad = selbsttest.geladene_datei("vcruntime140.dll")
    assert pfad and os.path.isfile(pfad)
    api = selbsttest.datei_fassung(pfad)
    assert api is not None and api[0] == 14
    assert vc_laufzeit.dateifassung(pfad) == api[:3]
    assert selbsttest.geladene_datei("gibt-es-nicht-liz4.dll") is None
