"""DEMO-8: Demo-Shows fuer das Setup BAUEN (nicht einchecken).

Viele Anleitungen setzen Demo-Shows voraus, die nur ueber einen Generator
(``tools/build_*.py``) entstehen. Das Windows-Setup enthaelt aber weder
``tools/`` noch Shows. Dieses Skript erzeugt eine feste Auswahl beim Bauen und
legt sie in einen Ordner ``demo_shows/`` — den nimmt
``packaging/windows/bundle_inhalt.py`` ins Bundle, und die App bietet sie unter
Datei -> „Demo-Show öffnen" an (``src/core/demo_shows.py``).

    python packaging/demo_shows.py                 # -> <repo>/demo_shows/
    python packaging/demo_shows.py --ziel ORDNER
    python packaging/demo_shows.py --nur showcase_club,laser_gobo_test
    python packaging/demo_shows.py --liste

Was hier sichergestellt wird:

* **Sandbox.** Jeder Generator laeuft als eigener Prozess mit einem Wegwerf-
  Datenordner (``sandbox_umgebung``): App-Datenordner, Geraete-Bibliothek,
  Show-DB, Einstellungen, Absturzprotokoll und Heimatordner zeigen in einen
  frischen Temp-Ordner. Das ist mehr als ``tools/_gen_env.py`` (das nur
  Show-DB und VC-Bilder umlenkt): mehrere Generatoren speichern ihre Buehne
  ueber ``save_stage`` in den App-Datenordner (TOOL-13) — hier landet das im
  Wegwerf-Ordner, nie beim Nutzer.
* **Buehne reist mit.** Seit VIZ-94 legt die App eine fehlende Buehnen-Datei
  aus dem ``scene_graph`` der Show an. ``buehnen_befund`` prueft je Show, dass
  alle Buehnen-Elemente der im Sandkasten gespeicherten Buehne im Szenengraph
  stehen — die ``.lshow`` ist also ohne Buehnen-Datei vollstaendig.
* **Keine Spuren des Baurechners.** ``spuren_befund`` sucht in ``show.json``
  nach dem Sandkasten-, Heimat- und Repo-Pfad.
* **Lint.** ``tools/lint_show.py --strict`` ueber alle erzeugten Shows (ein
  Prozess, ebenfalls im Sandkasten). Abschaltbar mit ``--ohne-lint``.

Ergebnis ist neben den ``.lshow`` ein Verzeichnis ``demos.json`` (Datei, Titel,
Kurzbeschreibung) — die App liest Titel und Tooltip daraus und braucht dieses
Skript zur Laufzeit nicht.

Importiert nichts aus ``src`` (die Pfade der App-Module frieren beim Import
ein; alles Bauende geschieht in Kindprozessen).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")

#: Ordnername — im Repo (Quellbetrieb, git-ignoriert) wie im Bundle.
ORDNER = "demo_shows"
#: Verzeichnis der Demos im Ordner.
INDEX = "demos.json"
INDEX_VERSION = 1


@dataclass(frozen=True)
class Demo:
    schluessel: str        # stabiler Kurzname (fuer --nur)
    datei: str             # Dateiname im demo_shows-Ordner
    titel: str             # Menue-Eintrag
    beschreibung: str      # Tooltip / Statuszeile
    generator: str         # Datei unter tools/
    #: Wie der Generator sein Ziel bekommt: "arg" = ``--out PFAD``,
    #: "env" = Umgebungsvariable ``LIGHTOS_GEN_OUT``.
    ziel_per: str = "arg"
    #: Zusaetzliche Umgebungsvariablen fuer genau diesen Generator.
    umgebung: tuple[tuple[str, str], ...] = ()


#: Die Auswahl. Reihenfolge = Reihenfolge im Menue.
DEMOS: tuple[Demo, ...] = (
    Demo("showcase_club", "Showcase_Club_Nacht.lshow", "Showcase: Club-Nacht",
         "Club-Rig mit Cue-Liste Intro bis Outro, taktgebundenem Drop-Puls und "
         "Virtual Console (GO/BACK, Flash, Speed-Dials).",
         "build_showcase_club.py"),
    Demo("showcase_theater", "Showcase_Theater_Event.lshow", "Showcase: Theater / Event",
         "Ruhige Cue-Liste mit Follow-Cues und Wartezeiten, Spots auf "
         "Ziel-Positionen, Paletten.",
         "build_showcase_theater.py"),
    Demo("buehnen_show", "Buehnen_Show_2026.lshow", "Große Bühnen-Show",
         "20 × 11 m Bühne mit drei Traversen-Ebenen und 80 Geräten: Wellen, "
         "Lauflicht von innen nach außen, Strobe, Laser, Kamerafahrten.",
         "build_buehnen_show_2026.py"),
    Demo("mega_arena", "Mega_Arena_2026.lshow", "Mega Arena 2026",
         "32 Geräte auf vier Traversen-Ebenen, sechs Bänke in der Virtual "
         "Console (Farbe, Dimmer, Bewegung, Strobe, Laser + Nebel, Tempo); alle "
         "Effekte folgen dem Tempo-Bus.",
         "build_mega_arena_2026.py", ziel_per="env",
         # Die Titelliste der Show nennt nur Platzhalter: kein Musikordner des
         # Baurechners darf in die ausgelieferte Datei geraten.
         umgebung=(("LIGHTOS_MEGA_MUSIC_DIR", "Musik"),)),
    Demo("laser_gobo_test", "Laser_Gobo_Test_2026.lshow", "Laser- und Gobo-Test",
         "18 Geräte auf zwei Universen: Laser, Gobo-Moving-Heads, PARs und "
         "Nebel an einem Rig ausprobieren.",
         "build_laser_gobo_test.py"),
)


class DemoBauFehler(RuntimeError):
    """Eine Demo-Show liess sich nicht bauen oder besteht eine Pruefung nicht."""


# ── Sandbox ──────────────────────────────────────────────────────────────────

#: Schalter (Wert "1"): keine Ausgabe, kein Audio, kein Kindprozess fuer
#: Enttec, keine Uebernahme echter data/-Dateien, keine Rueckfragen.
_SCHALTER = (
    "LIGHTOS_NO_OUTPUT_THREAD",
    "LIGHTOS_NO_AUDIO_AUTOSTART",
    "LIGHTOS_SERIAL_INPROC",
    "LIGHTOS_NO_RECOVERY_PROMPT",
    "LIGHTOS_NO_DATENUMZUG",
    "LIGHTOS_NO_SESSION_LOG",
)

#: Was eine geerbte Umgebung in eine echte Richtung lenken koennte — raus.
_ENTFERNEN = (
    "LIGHTOS_OUTPUT_IFACE",
    "LIGHTOS_REMOTE_TOKEN",
    "LIGHTOS_WEBENGINE_FLAGS",
    "LIGHTOS_BIBLIOTHEK_DIR",
    "LIGHTOS_GEN_OUT",
    "LIGHTOS_VC_ASSETS_DIR",
    "LIGHTOS_SESSION_LOG",
    "LIGHTOS_LOG_DIR",
    # Kein echter Bildschirm: die Generatoren zeichnen offscreen.
    "DISPLAY",
    "WAYLAND_DISPLAY",
)


def sandbox_umgebung(basis: str, vorlage: dict | None = None) -> dict:
    """Umgebung fuer einen Generator-Kindprozess: ALLE Datenorte unter ``basis``.

    Hart gesetzt (kein ``setdefault``) — eine geerbte Umgebung, in der etwa
    ``LIGHTOS_SHOW_DB`` auf eine echte Show-DB zeigt, darf hier nicht gewinnen.
    Legt die Ordner an. Die Liste folgt ``tools/anleitungsbilder/sandbox.py``.
    """
    basis = os.path.realpath(basis)
    daten = os.path.join(basis, "xdg", "data")
    pfade = {
        "HOME": os.path.join(basis, "home"),
        "USERPROFILE": os.path.join(basis, "home"),       # Windows: expanduser
        "APPDATA": os.path.join(basis, "appdata"),
        "LOCALAPPDATA": os.path.join(basis, "localappdata"),
        "XDG_DATA_HOME": daten,
        "XDG_CONFIG_HOME": os.path.join(basis, "xdg", "config"),
        "XDG_CACHE_HOME": os.path.join(basis, "xdg", "cache"),
        "XDG_STATE_HOME": os.path.join(basis, "xdg", "state"),
        "TMP": os.path.join(basis, "tmp"),
        "TEMP": os.path.join(basis, "tmp"),
        "TMPDIR": os.path.join(basis, "tmp"),
    }
    env = dict(os.environ if vorlage is None else vorlage)
    for name in _ENTFERNEN:
        env.pop(name, None)
    for name, pfad in pfade.items():
        os.makedirs(pfad, exist_ok=True)
        env[name] = pfad
    # Einzeln gepinnte Dateien. Die Geraete-Bibliothek liegt dort, wo die App
    # sie ohnehin suchte (App-Datenordner des Sandkastens) — fuer alle
    # Generatoren dieselbe, sie wird nur beim ersten angelegt.
    app = app_datenordner(env)
    os.makedirs(app, exist_ok=True)
    arbeit = os.path.join(basis, "arbeit")
    os.makedirs(arbeit, exist_ok=True)
    env.update({
        "LIGHTOS_FIXTURE_DB": os.path.join(app, "fixtures.db"),
        "LIGHTOS_PREFS_DIR": app,
        "LIGHTOS_CRASH_LOG": os.path.join(arbeit, "crash.log"),
        "LIGHTOS_SACN_CID": os.path.join(arbeit, "sacn_cid"),
        "LIGHTOS_UNIVERSES_JSON": os.path.join(arbeit, "universes.json"),
        # Show-DB je Lauf: ``_gen_env`` haengt Skriptname + PID an — im
        # umgelenkten TEMP. Hier nur die Vorgabe eines evtl. geerbten Werts weg.
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.pop("LIGHTOS_SHOW_DB", None)
    for name in _SCHALTER:
        env[name] = "1"
    return env


def app_datenordner(env: dict) -> str:
    """Der LightOS-Datenordner, den ein Kindprozess mit ``env`` benutzt —
    dieselbe Regel wie ``src.core.paths.app_data_dir`` (hier nachgebildet, weil
    dieses Skript ``src`` nicht importiert)."""
    if sys.platform == "win32":
        return os.path.join(env["APPDATA"], "LightOS")
    if sys.platform == "darwin":
        return os.path.join(env["HOME"], "Library", "Application Support", "LightOS")
    return os.path.join(env["XDG_DATA_HOME"], "LightOS")


# ── Pruefungen an der fertigen Datei ─────────────────────────────────────────

def lies_show(pfad: str) -> dict:
    with zipfile.ZipFile(pfad) as z:
        return json.loads(z.read("show.json").decode("utf-8"))


def buehnen_knoten(show: dict) -> list[dict]:
    """Buehnen-Elemente im ``scene_graph`` der Show — dieselbe Regel wie
    ``show_file._buehne_aus_szenengraph`` (VIZ-94): Nicht-Fixture-Knoten mit
    Geometrie."""
    sg = show.get("scene_graph")
    knoten = sg.get("nodes") if isinstance(sg, dict) else None
    if isinstance(knoten, dict):
        knoten = list(knoten.values())
    aus = []
    for n in knoten or []:
        if not isinstance(n, dict) or n.get("kind") in (None, "fixture"):
            continue
        groesse = n.get("size_m")
        if groesse and len(groesse) == 3:
            aus.append(n)
    return aus


def buehnen_befund(show: dict, stages_ordner: str | None) -> list[str]:
    """Reist die Buehne der Show in der Datei mit? Liste der Maengel.

    ``stages_ordner``: der ``stages``-Ordner des Sandkastens, in den der
    Generator seine Buehne gespeichert hat. Jedes Element dieser Datei muss
    als Knoten im Szenengraph stehen — sonst fehlte es auf einem Rechner ohne
    die Datei.
    """
    name = str((show.get("visualizer") or {}).get("active_stage") or "")
    knoten = {str(n.get("id")) for n in buehnen_knoten(show)}
    datei = _buehnen_datei(stages_ordner, name)
    if datei is None:
        # Keine eigene Buehnen-Datei (eingebautes Preset): nichts mitzunehmen.
        return []
    try:
        with open(datei, encoding="utf-8") as f:
            elemente = json.load(f).get("elements") or []
    except (OSError, ValueError) as e:
        return [f"Bühnen-Datei {os.path.basename(datei)} unlesbar: {e}"]
    if not elemente:
        return []
    fehlend = [str(e.get("id")) for e in elemente
               if isinstance(e, dict) and str(e.get("id")) not in knoten]
    if fehlend:
        return [f"Bühne „{name}“: {len(fehlend)} von {len(elemente)} Elementen "
                f"fehlen im scene_graph der Show ({', '.join(fehlend[:5])})"]
    return []


def _buehnen_datei(stages_ordner: str | None, name: str) -> str | None:
    if not stages_ordner or not name or not os.path.isdir(stages_ordner):
        return None
    for eintrag in sorted(os.listdir(stages_ordner)):
        pfad = os.path.join(stages_ordner, eintrag)
        if not eintrag.endswith(".json"):
            continue
        try:
            with open(pfad, encoding="utf-8") as f:
                if str(json.load(f).get("name")) == name:
                    return pfad
        except (OSError, ValueError, AttributeError):
            continue
    return None


def spuren_befund(pfad: str, verboten: tuple[str, ...]) -> list[str]:
    """Pfade des Baurechners in der Show-Datei (alle Text-Eintraege)."""
    nadeln = []
    for v in verboten:
        if v and len(v) > 3:
            nadeln += [v, v.replace("\\", "/"), v.replace("\\", "\\\\")]
    aus = []
    with zipfile.ZipFile(pfad) as z:
        for eintrag in z.namelist():
            if not eintrag.endswith((".json", ".txt")):
                continue
            text = z.read(eintrag).decode("utf-8", errors="replace")
            for n in dict.fromkeys(nadeln):
                if n in text:
                    aus.append(f"{eintrag} enthält den Pfad des Baurechners: {n}")
    return aus


# ── Bauen ────────────────────────────────────────────────────────────────────

def _lauf(befehl: list[str], env: dict, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(befehl, cwd=REPO, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return 124, f"Zeitüberschreitung nach {timeout} s\n{e.stdout or ''}"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def baue_eine(demo: Demo, ziel: str, basis: str, *, python: str | None = None,
              timeout: int = 900) -> float:
    """Baut ``demo`` nach ``ziel/<datei>``; liefert die Dauer in Sekunden."""
    env = sandbox_umgebung(basis)
    env.update(dict(demo.umgebung))
    aus = os.path.join(ziel, demo.datei)
    if os.path.exists(aus):
        os.remove(aus)
    befehl = [python or sys.executable, os.path.join(TOOLS, demo.generator)]
    if demo.ziel_per == "env":
        env["LIGHTOS_GEN_OUT"] = aus
    else:
        befehl += ["--out", aus]
    start = time.monotonic()
    code, ausgabe = _lauf(befehl, env, timeout)
    dauer = time.monotonic() - start
    if code != 0 or not os.path.isfile(aus):
        raise DemoBauFehler(f"{demo.generator}: Exit-Code {code}\n{ausgabe[-3000:]}")
    try:
        show = lies_show(aus)
    except Exception as e:
        raise DemoBauFehler(f"{demo.datei}: keine lesbare Show ({e})") from e
    maengel = buehnen_befund(show, os.path.join(app_datenordner(env), "stages"))
    maengel += spuren_befund(aus, (basis, os.path.expanduser("~"), REPO))
    if maengel:
        raise DemoBauFehler(f"{demo.datei}: " + "; ".join(maengel))
    return dauer


def lint(pfade: list[str], basis: str, *, python: str | None = None,
         timeout: int = 900) -> float:
    """``tools/lint_show.py --strict`` ueber alle Shows; Dauer in Sekunden."""
    env = sandbox_umgebung(basis)
    start = time.monotonic()
    code, ausgabe = _lauf([python or sys.executable, os.path.join(TOOLS, "lint_show.py"),
                           "--strict", *pfade], env, timeout)
    if code != 0:
        raise DemoBauFehler("Show-Lint (--strict) nicht sauber:\n" + ausgabe[-4000:])
    return time.monotonic() - start


def schreibe_index(ziel: str, demos) -> str:
    """``demos.json`` — das, was die App fuer das Menue braucht."""
    pfad = os.path.join(ziel, INDEX)
    daten = {"version": INDEX_VERSION,
             "demos": [{"schluessel": d.schluessel, "datei": d.datei, "titel": d.titel,
                        "beschreibung": d.beschreibung} for d in demos]}
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return pfad


def waehle(nur: str | None) -> tuple[Demo, ...]:
    if not nur:
        return DEMOS
    namen = [n.strip() for n in nur.split(",") if n.strip()]
    bekannt = {d.schluessel: d for d in DEMOS}
    unbekannt = [n for n in namen if n not in bekannt]
    if unbekannt:
        raise DemoBauFehler("unbekannte Demo: " + ", ".join(unbekannt)
                            + " (bekannt: " + ", ".join(bekannt) + ")")
    return tuple(d for d in DEMOS if d.schluessel in namen)


def baue(ziel: str, *, nur: str | None = None, mit_lint: bool = True,
         python: str | None = None, melde=print) -> dict:
    """Baut die Auswahl nach ``ziel`` und schreibt ``demos.json``.

    Liefert ``{"dauer": {schluessel: s, "lint": s, "gesamt": s}, "dateien": […]}``.
    Wirft :class:`DemoBauFehler`; dann bleibt KEIN ``demos.json`` im Ziel (ein
    halb gefuellter Ordner darf nicht als fertig gelten).
    """
    demos = waehle(nur)
    ziel = os.path.abspath(ziel)
    os.makedirs(ziel, exist_ok=True)
    index = os.path.join(ziel, INDEX)
    if os.path.exists(index):
        os.remove(index)
    dauer: dict[str, float] = {}
    start = time.monotonic()
    basis = tempfile.mkdtemp(prefix="lightos_demo_shows_")
    try:
        for demo in demos:
            melde(f"[demo_shows] baue {demo.titel} ({demo.generator}) …")
            dauer[demo.schluessel] = baue_eine(demo, ziel, basis, python=python)
            melde(f"[demo_shows]   {demo.datei}: {dauer[demo.schluessel]:.1f} s")
        pfade = [os.path.join(ziel, d.datei) for d in demos]
        if mit_lint:
            dauer["lint"] = lint(pfade, basis, python=python)
            melde(f"[demo_shows] Lint --strict sauber: {dauer['lint']:.1f} s")
        schreibe_index(ziel, demos)
    finally:
        shutil.rmtree(basis, ignore_errors=True)
    dauer["gesamt"] = time.monotonic() - start
    melde(f"[demo_shows] {len(demos)} Demo-Shows in {ziel} — {dauer['gesamt']:.1f} s")
    return {"dauer": dauer, "dateien": [d.datei for d in demos] + [INDEX]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Demo-Shows fuer das Setup bauen (DEMO-8).")
    ap.add_argument("--ziel", default=os.path.join(REPO, ORDNER),
                    help=f"Zielordner (Standard: <repo>/{ORDNER})")
    ap.add_argument("--nur", help="Komma-Liste von Schluesseln (siehe --liste)")
    ap.add_argument("--ohne-lint", action="store_true",
                    help="tools/lint_show.py --strict ueberspringen")
    ap.add_argument("--liste", action="store_true", help="Auswahl zeigen und beenden")
    args = ap.parse_args(argv)
    if args.liste:
        for d in DEMOS:
            print(f"{d.schluessel:18} {d.datei:32} {d.generator}")
        return 0
    try:
        baue(args.ziel, nur=args.nur, mit_lint=not args.ohne_lint)
    except DemoBauFehler as e:
        print(f"[demo_shows] FEHLER: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
