"""STAB-33: Nachbesserungen am Diagnosepaket, gefunden am ersten echten
Windows-Paket (x64, Setup-Build).

1. ``Architektur:`` war unter Windows leer.
2. ``Commit: unbekannt`` im Setup-Build — der Build bettet ``build_info.json`` ein.
3. ``Windows fatal exception: code 0x8001010d`` in crash.log ist kein Absturz
   (COM-Hinweis) und wird im Paket so gekennzeichnet; echte Abstuerze bleiben.
4. Qt-Warnung ``QFont::setPointSize: Point size <= 0 (-1)`` beim Start.
5. GPU-Renderer-String landet in ``systeminfo.txt``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import diagnose_log as d  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PACK = os.path.join(_REPO, "packaging", "windows")

_X64, _ARM64, _X86, _UNBEKANNT = 0x8664, 0xAA64, 0x014C, 0


def _lies(*teile: str) -> str:
    with open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _modul(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{name}_stab33", os.path.join(_PACK, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. Architektur ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("wow, nativ, machine, bits, erwartet", [
    # IsWow64Process2 meldet fuer einen NICHT-WOW64-Prozess "unbekannt" (0) —
    # auch fuer x64 auf ARM64; die Prozess-Architektur kommt dann aus machine.
    (_UNBEKANNT, _X64, "AMD64", 64, "x64 nativ"),
    (_UNBEKANNT, _ARM64, "ARM64", 64, "ARM64 nativ"),
    (_UNBEKANNT, _ARM64, "AMD64", 64, "x64-Prozess auf ARM64 (Emulation)"),
])
def test_architektur_64_bit(wow, nativ, machine, bits, erwartet):
    assert d.windows_architektur(wow, nativ, machine=machine, env={},
                                 bits=bits) == erwartet


def test_architektur_32_bit_nennt_32_bit_und_die_maschine():
    auf_x64 = d.windows_architektur(_X86, _X64, machine="x86", env={}, bits=32)
    assert auf_x64.startswith("32 Bit") and "x64" in auf_x64
    auf_arm = d.windows_architektur(_X86, _ARM64, machine="x86", env={}, bits=32)
    assert auf_arm.startswith("32 Bit") and "ARM64" in auf_arm
    assert "Emulation" in auf_arm
    rein = d.windows_architektur(_UNBEKANNT, _X86, machine="x86", env={}, bits=32)
    assert rein.startswith("32 Bit") and "nativ" in rein


def test_architektur_rueckfall_ohne_systemaufruf():
    """Scheitert IsWow64Process2 (None), entscheiden die Umgebungsvariablen."""
    assert d.windows_architektur(
        None, None, machine="AMD64",
        env={"PROCESSOR_ARCHITECTURE": "AMD64"}, bits=64).startswith("x64 nativ")
    # 32-Bit-Prozess unter WOW64: PROCESSOR_ARCHITEW6432 nennt die echte Maschine
    wow = d.windows_architektur(
        None, None, machine="",
        env={"PROCESSOR_ARCHITECTURE": "x86",
             "PROCESSOR_ARCHITEW6432": "AMD64"}, bits=32)
    assert wow.startswith("32 Bit") and "x64" in wow
    # x64-Python auf ARM64: nur PROCESSOR_IDENTIFIER verraet die Maschine
    emu = d.windows_architektur(
        None, None, machine="AMD64",
        env={"PROCESSOR_ARCHITECTURE": "AMD64",
             "PROCESSOR_IDENTIFIER": "ARMv8 (64-bit) Family 8 Model 1"}, bits=64)
    assert emu.startswith("x64-Prozess auf ARM64 (Emulation)")
    # der Rueckfall ist als solcher erkennbar
    assert "Rueckfall" in emu


def test_architektur_ist_nie_leer():
    for wow, nativ in ((None, None), (0, 0), (0x1234, 0x4321)):
        text = d.windows_architektur(wow, nativ, machine="", env={}, bits=64)
        assert text.strip(), (wow, nativ)
    assert "64 Bit" in d.windows_architektur(None, None, machine="", env={},
                                             bits=64)


def test_architektur_zeile_unter_windows_nie_leer(monkeypatch):
    """Die Zeile im Kopfblock: auch wenn der Systemaufruf nichts liefert."""
    monkeypatch.setattr(d, "_iswow64process2", lambda: None)
    monkeypatch.setattr(d.platform, "machine", lambda: "AMD64")
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")
    monkeypatch.delenv("PROCESSOR_ARCHITEW6432", raising=False)
    monkeypatch.delenv("PROCESSOR_IDENTIFIER", raising=False)
    assert d._windows_architektur().startswith("x64 nativ")
    monkeypatch.setattr(d, "_iswow64process2", lambda: (_UNBEKANNT, _ARM64))
    assert d._windows_architektur() == "x64-Prozess auf ARM64 (Emulation)"


def test_systemaufruf_uebergibt_das_handle_in_voller_breite():
    """Ursache der leeren Zeile: ohne ``argtypes`` reichte ctypes das Pseudo-
    Handle (-1) als 32-Bit-int durch — auf x64 ein ungueltiges Handle."""
    quelle = _lies("src", "core", "diagnose_log.py")
    assert "IsWow64Process2.argtypes" in quelle
    assert "GetCurrentProcess.restype" in quelle


# ── 2. Commit im Setup-Build ─────────────────────────────────────────────────
def test_build_info_schreiben_aus_github_umgebung(tmp_path):
    bi = _modul("build_info")
    sha = "0123456789abcdef0123456789abcdef01234567"
    pfad = bi.schreibe(str(tmp_path), env={
        "GITHUB_SHA": sha, "GITHUB_REF_NAME": "main", "GITHUB_RUN_ID": "42"},
        jetzt="2026-10-10T08:00:00Z")
    assert os.path.basename(pfad) == "build_info.json"
    with open(pfad, encoding="utf-8") as f:
        daten = json.load(f)
    assert daten["commit"] == sha
    assert daten["ref"] == "main"
    assert daten["datum"] == "2026-10-10T08:00:00Z"
    assert daten["lauf"] == "42"


def test_build_info_ohne_commit_ist_ein_fehler(tmp_path):
    """Ausserhalb von Git und ohne GITHUB_SHA: lieber scheitern als ein Setup
    bauen, dessen Diagnosepaket wieder 'unbekannt' meldet."""
    bi = _modul("build_info")
    with pytest.raises(RuntimeError):
        bi.schreibe(str(tmp_path), env={}, jetzt="2026-10-10T08:00:00Z")


def test_bundle_nimmt_build_info_mit(tmp_path):
    inhalt = _modul("bundle_inhalt")
    assert "build_info.json" in inhalt.GENERIERTE_DATEIEN
    (tmp_path / "build_info.json").write_text("{}", encoding="utf-8")
    ziele = {os.path.basename(q): z for q, z in inhalt.datas(str(tmp_path))}
    assert ziele.get("build_info.json") == "."
    # ohne die Datei (Quell-Checkout) bleibt die Liste einfach ohne sie
    os.remove(tmp_path / "build_info.json")
    assert not any(os.path.basename(q) == "build_info.json"
                   for q, _z in inhalt.datas(str(tmp_path)))


def test_workflow_schreibt_build_info_vor_dem_build():
    s = _lies(".github", "workflows", "windows-setup.yml")
    assert "packaging/windows/build_info.py" in s
    assert s.index("packaging/windows/build_info.py") < s.index("-m PyInstaller")


def test_build_info_json_wird_nicht_eingecheckt():
    assert "/build_info.json" in _lies(".gitignore").splitlines()


def test_commit_gefroren_kommt_aus_build_info(tmp_path, monkeypatch):
    (tmp_path / "build_info.json").write_text(json.dumps({
        "commit": "0123456789abcdef0123456789abcdef01234567", "ref": "main",
        "datum": "2026-10-10T08:00:00Z"}), encoding="utf-8")
    monkeypatch.setattr(d.sys, "frozen", True, raising=False)
    zeilen = dict(d.basis_infos("9.9.9", str(tmp_path)))
    assert zeilen["Commit"].startswith("0123456789ab")
    assert "main" in zeilen["Commit"]
    assert "2026-10-10" in zeilen["Commit"]
    assert "unbekannt" not in zeilen["Commit"]


def test_commit_gefroren_ohne_build_info_bleibt_unbekannt(tmp_path, monkeypatch):
    monkeypatch.setattr(d.sys, "frozen", True, raising=False)
    assert dict(d.basis_infos("9.9.9", str(tmp_path)))["Commit"] == "unbekannt"
    (tmp_path / "build_info.json").write_text("kein json", encoding="utf-8")
    assert dict(d.basis_infos("9.9.9", str(tmp_path)))["Commit"] == "unbekannt"


def test_commit_im_quellbetrieb_weiter_aus_git(tmp_path):
    """Eine liegen gebliebene build_info.json (lokaler Build) darf den echten
    Stand des Arbeitsverzeichnisses nicht ueberdecken."""
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/arbeit\n", encoding="utf-8")
    (git / "refs" / "heads" / "arbeit").write_text("f" * 40 + "\n",
                                                   encoding="utf-8")
    (tmp_path / "build_info.json").write_text(json.dumps({
        "commit": "0" * 40, "ref": "main"}), encoding="utf-8")
    assert dict(d.basis_infos("9.9.9", str(tmp_path)))["Commit"] == \
        "ffffffffffff (arbeit)"


def test_selbsttest_verlangt_build_info_nur_gefroren(tmp_path):
    from src.core import selbsttest
    assert selbsttest.pruefe_build_info(str(tmp_path), gefroren=False) == []
    fehler = selbsttest.pruefe_build_info(str(tmp_path), gefroren=True)
    assert len(fehler) == 1 and "build_info.json" in fehler[0]
    (tmp_path / "build_info.json").write_text(json.dumps({"commit": ""}),
                                              encoding="utf-8")
    assert selbsttest.pruefe_build_info(str(tmp_path), gefroren=True)
    (tmp_path / "build_info.json").write_text(json.dumps({"commit": "a" * 40}),
                                              encoding="utf-8")
    assert selbsttest.pruefe_build_info(str(tmp_path), gefroren=True) == []


# ── 3. COM-Hinweis ist kein Absturz ──────────────────────────────────────────
_COM = ("=== LightOS STARTED 2026-10-10T12:10:55 | v1.0.0 ===\n"
        "Windows fatal exception: code 0x8001010d\n"
        "\n"
        "Thread 0x000006a8 (most recent call first):\n"
        '  File "main.py", line 522 in _watch\n'
        "\n"
        "Current thread 0x0000064c (most recent call first):\n"
        '  File "main.py", line 905 in main\n'
        "[Qt/WARNING 2026-10-10T12:11:19] spaetere Zeile\n")


def test_com_hinweis_wird_gekennzeichnet():
    text, harmlos, andere = d.kennzeichne_harmlose_ausnahmen(_COM)
    assert harmlos == {"0x8001010d": 1}
    assert andere == 0
    zeilen = text.splitlines()
    i = zeilen.index("Windows fatal exception: code 0x8001010d")   # Original bleibt
    assert "kein Absturz: COM-Hinweis 0x8001010d" in zeilen[i + 1]
    assert "RPC_E_CANTCALLOUT_ININPUTSYNCCALL" in zeilen[i + 1]
    # nichts geht verloren: ohne die Kennzeichnung steht das Original da
    assert "\n".join(z for z in zeilen if "kein Absturz" not in z) + "\n" == _COM


def test_gross_und_kleinschreibung_des_codes_egal():
    _t, harmlos, _a = d.kennzeichne_harmlose_ausnahmen(
        "Windows fatal exception: code 0x8001010D\n")
    assert harmlos == {"0x8001010d": 1}


@pytest.mark.parametrize("zeile", [
    "Windows fatal exception: access violation",
    "Windows fatal exception: code 0xc0000005",
    "Windows fatal exception: code 0xc0000409",
    "Windows fatal exception: stack overflow",
    "Fatal Python error: Segmentation fault",
    "Fatal Python error: Aborted",
])
def test_echte_abstuerze_bleiben_unangetastet(zeile):
    roh = zeile + "\n\nCurrent thread 0x01 (most recent call first):\n"
    text, harmlos, andere = d.kennzeichne_harmlose_ausnahmen(roh)
    assert text == roh
    assert harmlos == {}
    assert andere == 1
    assert "kein Absturz" not in text


def test_paket_kennzeichnet_crash_log_und_liesmich(tmp_path, monkeypatch):
    daten = tmp_path / "daten"
    daten.mkdir()
    crash = daten / "crash.log"
    crash.write_text(_COM + "Windows fatal exception: access violation\n",
                     encoding="utf-8")
    monkeypatch.setenv("LIGHTOS_CRASH_LOG", str(crash))
    monkeypatch.setenv("LIGHTOS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(d, "app_data_dir", lambda: str(daten))
    ziel = d.erstelle_diagnosepaket(str(tmp_path / "p.zip"), "9.9.9",
                                    str(tmp_path))
    with zipfile.ZipFile(ziel) as zf:
        im_paket = zf.read("crash/crash.log").decode("utf-8")
        liesmich = zf.read("LIESMICH.txt").decode("utf-8")
    assert "Windows fatal exception: code 0x8001010d" in im_paket
    assert "kein Absturz: COM-Hinweis 0x8001010d" in im_paket
    assert "Windows fatal exception: access violation" in im_paket
    assert "kein Absturz: COM-Hinweis 0x8001010d" in liesmich
    # der echte Absturz wird im LIESMICH ausdruecklich NICHT entwarnt
    assert "1 weitere" in liesmich
    # die Datei auf der Platte bleibt, wie sie ist
    assert "kein Absturz" not in crash.read_text(encoding="utf-8")


def test_paket_ohne_com_hinweis_hat_keinen_abschnitt(tmp_path, monkeypatch):
    daten = tmp_path / "daten"
    daten.mkdir()
    crash = daten / "crash.log"
    crash.write_text("=== LightOS STARTED ===\n", encoding="utf-8")
    monkeypatch.setenv("LIGHTOS_CRASH_LOG", str(crash))
    monkeypatch.setenv("LIGHTOS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(d, "app_data_dir", lambda: str(daten))
    ziel = d.erstelle_diagnosepaket(str(tmp_path / "p.zip"), "9.9.9",
                                    str(tmp_path))
    with zipfile.ZipFile(ziel) as zf:
        assert "kein Absturz" not in zf.read("LIESMICH.txt").decode("utf-8")


# ── 4. QFont::setPointSize(-1) ───────────────────────────────────────────────
# Das Theme setzt Schriften in Pixeln (font().pointSize() == -1). Traegt ein
# QPushButton ein Menue, fragt Qt den Stil nach der Breite des Menue-Pfeils
# (PM_MenuButtonIndicator) — und Qts Windows-11-Stil rechnet die aus
# pointSize(): "QFont::setPointSize: Point size <= 0 (-1)". Den Windows-Stil gibt
# es unter Linux nicht; gemessen wird deshalb die FRAGE an den Basis-Stil.
def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _merker_stil(fragen: list):
    from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

    class Merker(QProxyStyle):
        def pixelMetric(self, metrik, option=None, widget=None):
            if (metrik == QStyle.PixelMetric.PM_MenuButtonIndicator
                    and widget is not None):
                fragen.append(widget.font().pointSize())
            return super().pixelMetric(metrik, option, widget)

    return Merker(QStyleFactory.create("Fusion"))


def _messen(knopf, fragen: list) -> None:
    knopf.ensurePolished()
    knopf.sizeHint()                # Groessenberechnung (beim Start)
    knopf.resize(260, 30)
    knopf.grab()                    # einmal wirklich zeichnen
    _app().processEvents()


def test_qpushbutton_mit_menue_loest_die_frage_aus():
    """Gegenprobe: die Messung schlaegt beim eingebauten Weg wirklich an."""
    from PySide6.QtWidgets import QMenu, QPushButton
    _app()
    fragen: list = []
    stil = _merker_stil(fragen)
    knopf = QPushButton("eingebaut ▾")
    knopf.setStyle(stil)
    knopf.setMenu(QMenu(knopf))
    knopf.setStyleSheet(_lies("assets", "themes", "dark.qss"))
    _messen(knopf, fragen)
    assert fragen and set(fragen) == {-1}
    knopf.deleteLater()


def test_gruppen_ansicht_fragt_nicht_nach_dem_menue_pfeil():
    """Die beiden Knoepfe „… einzeln → Raster ▾" der Gruppen-Ansicht waren die
    Quelle der Warnung beim Start."""
    from src.ui.views.fixture_group_view import FixtureGroupView
    _app()
    view = FixtureGroupView()
    try:
        view.setStyleSheet(_lies("assets", "themes", "dark.qss"))
        fragen: list = []
        stil = _merker_stil(fragen)
        knoepfe = list(view._btn_achse.values())
        assert len(knoepfe) == 2
        for k in knoepfe:
            k.setStyle(stil)
            k.ensurePolished()
            assert k.font().pointSize() == -1      # Pixel-Schrift aus dem Theme
            _messen(k, fragen)
            assert k.menu() is not None and k.menu().actions()
        assert fragen == []
    finally:
        view.close()
        view.deleteLater()
        _app().processEvents()


def test_menue_knopf_klappt_das_menue_beim_klick_auf():
    from PySide6.QtWidgets import QMenu, QPushButton
    from src.ui.widgets.menue_knopf import MenueKnopf
    _app()
    knopf = MenueKnopf("Auswahl ▾")
    menu = QMenu(knopf)
    gewaehlt = []
    menu.addAction("eins").triggered.connect(lambda: gewaehlt.append(1))
    knopf.setMenu(menu)
    try:
        assert knopf.menu() is menu
        assert QPushButton.menu(knopf) is None       # Qt kennt das Menue nicht
        knopf.show()
        _app().processEvents()
        assert not menu.isVisible()
        knopf.click()
        _app().processEvents()
        assert menu.isVisible()
        menu.actions()[0].trigger()
        assert gewaehlt == [1]
        menu.hide()
        knopf.setEnabled(False)
        knopf.showMenu()
        assert not menu.isVisible()
    finally:
        menu.hide()
        knopf.close()
        knopf.deleteLater()
        _app().processEvents()


def test_kein_qpushbutton_bekommt_ein_qt_menue():
    """Waechter fuer neue Stellen: ``setMenu`` nur an QToolButton/MenueKnopf."""
    import re
    wurzel = os.path.join(_REPO, "src")
    funde = []
    for ordner, _dirs, dateien in os.walk(wurzel):
        for name in dateien:
            if not name.endswith(".py"):
                continue
            pfad = os.path.join(ordner, name)
            with open(pfad, encoding="utf-8") as f:
                quelle = f.read()
            for m in re.finditer(r"([A-Za-z_][\w.]*)\.setMenu\(", quelle):
                var = m.group(1)
                if var in ("super()", "self") or var.endswith("QPushButton"):
                    continue
                zuweisungen = re.findall(
                    r"(?m)^\s*" + re.escape(var) + r"\s*=\s*([A-Za-z_]\w*)\(",
                    quelle[:m.start()])
                klasse = zuweisungen[-1] if zuweisungen else "?"
                if klasse not in ("QToolButton", "MenueKnopf"):
                    zeile = quelle.count("\n", 0, m.start()) + 1
                    funde.append(f"{os.path.relpath(pfad, _REPO)}:{zeile} "
                                 f"{var} = {klasse}(…)")
    assert funde == [], ("QPushButton.setMenu loest unter Windows die Qt-Warnung "
                         "'QFont::setPointSize: Point size <= 0 (-1)' aus — "
                         "MenueKnopf (src/ui/widgets/menue_knopf.py) nehmen")


# ── 5. GPU-Renderer ──────────────────────────────────────────────────────────
_GPU = ("[viz] GPU-Tier: high (grund=diskrete GPU, renderer=ANGLE (AMD, Radeon "
        "RX 580 Series (0x000067DF) Direct3D11 vs_5_0 ps_5_0, D3D11), "
        "maxTextures=16, pixelRatioCap=2, schattenDach=8, echteLichter=8, "
        "dynAufloesung=slow, antialias=true)")
_RENDERER = ("ANGLE (AMD, Radeon RX 580 Series (0x000067DF) Direct3D11 vs_5_0 "
             "ps_5_0, D3D11)")


def test_gpu_meldung_zerlegen():
    info = d.gpu_aus_viz_meldung(_GPU)
    assert info["stufe"] == "high"
    assert info["renderer"] == _RENDERER
    assert info["grund"] == "diskrete GPU"
    assert "maxTextures=16" in info["details"]
    # aeltere Qt-Versionen stellen der JS-Konsole "js: " voran
    assert d.gpu_aus_viz_meldung("js: " + _GPU)["renderer"] == _RENDERER
    assert d.gpu_aus_viz_meldung("QFont::setPointSize: Point size <= 0") is None
    assert d.gpu_aus_viz_meldung("[viz] GPU-Tier: kaputt") is None
    assert d.gpu_aus_viz_meldung(None) is None


def test_gpu_renderer_landet_in_systeminfo(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "_laufzeit", {})
    assert d.merke_viz_gpu("irgendeine andere Qt-Meldung") is False
    assert d.laufzeit_infos() == {}
    assert d.merke_viz_gpu(_GPU) is True
    text = d.systeminfo_text("9.9.9", str(tmp_path))
    assert f"Visualizer GPU-Renderer: {_RENDERER}" in text
    assert "maxTextures=16" in text


def test_qt_meldungen_gehen_an_die_gpu_erkennung():
    """Die Zeile kommt als Qt-Meldung an (JS ``console.warn``) — der Handler in
    main.py reicht sie an ``diagnose_log`` weiter. ``scene_src`` bleibt, wie es
    ist."""
    quelle = _lies("main.py")
    start = quelle.index("def _install_qt_message_handler")
    ende = quelle.index("qInstallMessageHandler(_handler)", start)
    assert "_dl.merke_viz_gpu(message)" in quelle[start:ende]
