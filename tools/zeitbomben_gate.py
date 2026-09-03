"""Waechter gegen Zeitbomben — Tests, die von selbst rot werden (QA-63).

★ Der Anlass (QA-62, 22.08.2026). ``tests/test_crash_intake.py::RecencyTest``
trug feste Daten: ``2026-01-01`` als „alt", ``2026-07-20`` als „neu". Die
Kaelte-Schwelle im Produktionscode ist aber **30 Tage vor HEUTE**
(``collect_crash_report._cold_before``). Am 22.08. war damit auch das „neue"
Datum kalt — der Test wurde rot, **ohne dass jemand etwas geaendert hatte**, auf
``main`` und danach in jedem PR. Das Teuerste daran: der Fehler gehoerte zu
KEINEM Commit. Man sucht ihn in den eigenen Aenderungen, wo er nicht ist.

**Was dieser Waechter sucht — und was ausdruecklich nicht.** Gefaehrlich ist
nicht das feste Datum, sondern seine VERBINDUNG mit einer Schwelle, die an HEUTE
haengt. Gemessen am 22.08.2026 tragen 9 von 615 Testdateien feste Daten
ausserhalb von Docstrings (dazu diese Arbeit selbst: 10 von 616), und **alle
sind gesund** — sie vergleichen Zeitstempel miteinander, statt sie gegen eine
gleitende Grenze zu halten. Ein Gate, das sie beanstandet, waere nach zwei
Fehlalarmen abgeschaltet und damit schlechter als keines.

**Wie die Verbindung gemessen wird, statt sie zu erraten.** Statisch ist sie
nicht zuverlaessig zu sehen: die Schwelle liegt oft mehrere Aufrufe tief im
Produktionscode (``format_report`` -> ``_cold_before`` -> ``date.today``), und
kein Muster im Testtext verraet sie. Deshalb wird sie **gefahren**:

1. **Kandidaten** (statisch, billig): Testdateien mit einem festen Kalenderdatum
   ausserhalb von Docstrings. Das ist bewusst eine grosszuegige VORAUSWAHL, kein
   Urteil.
2. **Urteil** (dynamisch, echt): dieselben Dateien laufen noch einmal, mit einer
   um Jahre vorgerueckten Uhr (``tools/_zeitsprung/sitecustomize.py``). Wer dann
   rot wird, ist heute gruen und morgen rot — die Definition einer Zeitbombe.
   Wer schon ohne Sprung rot ist, ist ein gewoehnlicher Fehlschlag und wird
   NICHT gemeldet.

**Der Selbstschutz.** Ein Uhr-Vorspann, der still nicht greift, macht aus diesem
Gate einen Ja-Sager: alles gruen, keine Bomben. Darum verlangt jeder Lauf die
Zeile ``ZEITSPRUNG-WIRKSAM`` aus ``tools/_zeitsprung/zeitsprung_kanarie.py``,
gemessen IM Testprozess. Fehlt sie, ist das Ergebnis ein Fehler und kein „gruen".

Aufruf::

    venv/bin/python tools/zeitbomben_gate.py                 # Kandidaten pruefen
    venv/bin/python tools/zeitbomben_gate.py --nur-kandidaten
    venv/bin/python tools/zeitbomben_gate.py --tage 400      # anderer Sprung
    venv/bin/python tools/zeitbomben_gate.py --uhr alle      # auch time.time (laut)
    (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

Die GANZE Suite mit vorgerueckter Uhr — bewusst nicht als Schalter hier, weil
615 Dateien in EINEM pytest-Prozess auf Linux reproduzierbar an akkumulierendem
Qt-Zustand sterben (XPLAT-11). Das Gate-Skript kann das schon::

    PYTHONPATH=tools/_zeitsprung LIGHTOS_ZEITSPRUNG_TAGE=3653 \\
        ./tools/verify_loop.sh

⚠️ Ueber ``verify_loop.sh``, NICHT ueber ``verify_segmented.sh``: nur das erste
nimmt die rechnerweite PROC-02-Sperre. Direkt gestartet laeuft der Streifzug
neben einer fremden vollen Suite — gemessen 2026-08-22: 21 rote Segmente, von
denen 18 einzeln nachgefahren kerngesund waren.
"""
from __future__ import annotations

import argparse
import ast
import datetime
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import NamedTuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_zeitsprung")
KANARIE_PLUGIN = "zeitsprung_kanarie"
MARKE_OK = "ZEITSPRUNG-WIRKSAM"
MARKE_FEHLT = "ZEITSPRUNG-UNWIRKSAM"

#: Wie weit die Uhr vorgestellt wird. Zehn Jahre statt „ein paar Monate":
#: die 30-Tage-Schwelle aus QA-62 ist die kleinste im Haus, aber nichts
#: garantiert, dass die naechste nicht „ein Jahr" heisst. Gemessen bleiben alle
#: heutigen Kandidaten auch bei +3653 Tagen gruen — der grosse Sprung kostet
#: also keine Treffsicherheit.
SPRUNG_TAGE = 3653

#: Welche Uhren der Vorspann verschiebt — s. ``tools/_zeitsprung/sitecustomize.py``.
#: ``datum`` verschiebt nur ``datetime``/``date``; ``alle`` zusaetzlich
#: ``time.time``. Gemessen 2026-08-22 ueber die ganze Suite: ``alle`` bringt
#: NULL zusaetzliche Funde und DREI sichere Fehlalarme (Dateialter gegen die
#: echte ``st_mtime``). Das Gate faehrt deshalb ``datum``.
SPRUNG_UHR = "datum"

#: Kalenderdatum in ISO-Form. Kein ``\b`` am Ende: ``2026-05-27T00:00:00`` hat
#: zwischen „7" und „T" keine Wortgrenze, und genau so steht das Datum in
#: ``tests/test_show_format_upgrade.py`` — die erste Fassung uebersah die Datei.
ISO_DATUM = re.compile(
    r"(?<!\d)(?:19|20)\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?!\d)")

#: Deutsche Schreibweise ``17.07.2026``. Kommt im Repo genau einmal vor
#: (``tests/test_audit_bilder_stand.py:72``, gemessen 2026-08-22) — die Datei
#: ist ueber ihre ISO-Daten ohnehin Kandidat, die Form kostet also heute nichts
#: und schliesst trotzdem eine Luecke, die morgen etwas kosten koennte.
DE_DATUM = re.compile(r"(?<!\d)[0-3]\d\.[01]\d\.(?:19|20)\d\d(?!\d)")

DATUM = re.compile(f"{ISO_DATUM.pattern}|{DE_DATUM.pattern}")

#: ★ Der Waechter nimmt sich selbst aus — und das ist eine Luecke mit Namen,
#: keine Bequemlichkeit. ``tests/test_zeitbomben_gate.py`` FAEHRT diesen
#: Waechter. Liefe es in einem Waechter-Lauf mit, startete es darin einen
#: zweiten Waechter-Lauf, der es wieder mitfuehrt — unbegrenzt tief. Genau
#: diese Selbstverstrickung hat schon ein anderes Gate im Haus erwischt
#: (``tests/test_session_claim.py``: „das Gate fand sich selbst").
#: Es traegt feste Daten, aber ausschliesslich als EINGABE fuer den Scanner
#: (``feste_daten('X = "2026-07-20"')``); an keiner gleitenden Schwelle haengt
#: eines davon. Dass die Ausnahme wirklich noetig ist und nicht stillschweigend
#: mehr ausnimmt, haelt ``test_der_waechter_nimmt_genau_sich_selbst_aus`` fest.
SELBST = ("test_zeitbomben_gate.py",)


class Fund(NamedTuple):
    zeile: int
    text: str


class Ergebnis(NamedTuple):
    rc: int
    ausgabe: str
    sprung_wirksam: bool


class Bericht(NamedTuple):
    kandidaten: list          # [(relpfad, [Fund, ...])]
    bomben: list              # [(relpfad, ausgabe)]
    schon_rot: list           # [(relpfad, ausgabe)]  — heute schon rot
    tage: int
    ausgabe: str

    @property
    def gruen(self) -> bool:
        return not self.bomben


# ─────────────────────────── 1. Kandidaten (statisch) ───────────────────────

def _docstring_knoten(baum: ast.AST) -> set:
    """IDs aller Konstanten, die als Docstring dienen.

    ★ Warum Docstrings ausgenommen sind — das ist der Unterschied zwischen
    einem brauchbaren und einem unbenutzbaren Gate, und er ist gemessen: mit
    Docstrings tragen **143 von 615** Testdateien ein Datum, ohne nur **9**.
    Ein Datum in einem Docstring ist Prosa („Der Chase-Builder wurde am
    2026-06-30 entfernt") und kann an keinem Vergleich teilnehmen.
    """
    ids = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.Module, ast.ClassDef,
                               ast.FunctionDef, ast.AsyncFunctionDef)):
            koerper = getattr(knoten, "body", None)
            if (koerper and isinstance(koerper[0], ast.Expr)
                    and isinstance(koerper[0].value, ast.Constant)
                    and isinstance(koerper[0].value.value, str)):
                ids.add(id(koerper[0].value))
    return ids


def feste_daten(quelle: str, name: str = "<quelle>") -> list[Fund]:
    """Feste Kalenderdaten in Python-Quelltext, Docstrings ausgenommen.

    Zwei Formen, weil beide im Repo vorkommen:

    * Zeichenketten mit Datum — ISO (``"2026-07-20T19:18:49+02:00"``) und
      deutsche Form (``"17.07.2026"``),
    * ``datetime(2026, 8, 6, ...)`` / ``date(2026, 8, 6)`` mit festen Zahlen —
      so steht es in ``tests/test_session_claim.py`` und
      ``tests/test_crash_logging.py``. Wer nur die erste Form kennt, sieht in
      einer Datei mit ausschliesslich Konstruktor-Aufrufen gar nichts.

    Kommentare sind bewusst NICHT erfasst: sie stehen nicht im AST, koennen an
    keinem Vergleich teilnehmen und wuerden dieselbe Flut ausloesen wie
    Docstrings.
    """
    baum = ast.parse(quelle, name)
    docs = _docstring_knoten(baum)
    funde: list[Fund] = []
    for knoten in ast.walk(baum):
        if (isinstance(knoten, ast.Constant) and isinstance(knoten.value, str)
                and id(knoten) not in docs):
            treffer = DATUM.search(knoten.value)
            if treffer:
                funde.append(Fund(knoten.lineno, treffer.group(0)))
        elif isinstance(knoten, ast.Call):
            name_auf = (knoten.func.attr if isinstance(knoten.func, ast.Attribute)
                        else getattr(knoten.func, "id", ""))
            if name_auf in ("date", "datetime"):
                args = [a for a in knoten.args if isinstance(a, ast.Constant)]
                if (len(args) >= 3 and isinstance(args[0].value, int)
                        and 1900 <= args[0].value <= 2999):
                    funde.append(Fund(
                        knoten.lineno,
                        f"{name_auf}({args[0].value}, {args[1].value}, "
                        f"{args[2].value})"))
    return sorted(set(funde))


def testdateien(wurzel: str) -> list[str]:
    """Alle ``test_*.py`` unter ``wurzel`` — dieselbe Auswahl wie
    ``tools/verify_segmented.sh`` (``find tests -name 'test_*.py'``)."""
    treffer = []
    for ordner, unter, dateien in os.walk(wurzel):
        unter[:] = [u for u in unter if u != "__pycache__"]
        for datei in dateien:
            if datei.startswith("test_") and datei.endswith(".py"):
                treffer.append(os.path.join(ordner, datei))
    return sorted(treffer)


def _funde(pfad: str) -> list[Fund]:
    try:
        with open(pfad, encoding="utf-8") as fh:
            return feste_daten(fh.read(), pfad)
    except (OSError, SyntaxError):
        return []              # kaputte Datei ist Sache des Syntax-Gates


def kandidaten(wurzel: str) -> list:
    """[(pfad, [Fund, ...])] fuer jede Testdatei mit festem Datum."""
    return [(pfad, funde) for pfad in testdateien(wurzel)
            if (funde := _funde(pfad))]


def zu_fahren(kand) -> list[str]:
    """Aus der Vorauswahl die Dateien, die tatsaechlich gefahren werden.

    Entfernt genau die Dateien aus ``SELBST`` — s. dort, warum.
    """
    return [pfad for pfad, _ in kand
            if os.path.basename(pfad) not in SELBST]


# ─────────────────────────── 2. Urteil (dynamisch) ──────────────────────────

AKTIV_VAR = "LIGHTOS_ZEITSPRUNG_AKTIV"


def echt_heute() -> datetime.date:
    """Der WIRKLICHE Kalendertag — auch wenn dieser Prozess selbst schon unter
    vorgerueckter Uhr laeuft.

    ★ Warum das noetig ist: der Waechter wird verschachtelt gefahren. Beim
    dokumentierten Streifzug ueber die ganze Suite
    (``LIGHTOS_ZEITSPRUNG_TAGE=3653 ./tools/verify_segmented.sh``) laeuft auch
    ``tests/test_zeitbomben_gate.py`` mit vorgerueckter Uhr — und rechnete den
    Sollwert fuer sein Kind aus seiner EIGENEN, schon verschobenen Uhr. Der
    Kanarienvogel des Kindes saehe dann +3653 Tage, erwartete aber +7306 und
    schluege Alarm. Der Waechter waere im eigenen Streifzug rot, ohne dass eine
    einzige Zeitbombe existiert.

    Gelesen wird ``LIGHTOS_ZEITSPRUNG_AKTIV`` — die setzt der Vorspann selbst,
    NACHDEM er gelaufen ist. ``LIGHTOS_ZEITSPRUNG_TAGE`` allein wuerde die
    Verschiebung auch dann behaupten, wenn sie jemand ohne Vorspann setzt.
    """
    roh = os.environ.get(AKTIV_VAR, "").strip()
    try:
        tage = int(roh)
    except ValueError:
        return datetime.date.today()
    return datetime.date.today() - datetime.timedelta(days=tage)


def sprung_umgebung(tage: int, basis: dict | None = None,
                    shim: str = SHIM, uhr: str = SPRUNG_UHR) -> dict:
    """Umgebung fuer einen Kindprozess mit vorgerueckter Uhr.

    ``tage=0`` liefert bewusst eine Umgebung OHNE Sprung — das ist der
    Vergleichslauf, mit dem „war schon vorher rot" von „wird erst spaeter rot"
    unterschieden wird.
    """
    env = dict(os.environ if basis is None else basis)
    # ★ Ein GEERBTER Vorspann wird herausgenommen, bevor der gewuenschte
    # vorangestellt wird. Gemessen 2026-08-22: laeuft der Waechter selbst unter
    # dem dokumentierten Streifzug (``PYTHONPATH=tools/_zeitsprung
    # LIGHTOS_ZEITSPRUNG_TAGE=… ./tools/verify_segmented.sh``), dann steht der
    # echte Vorspann schon im geerbten ``PYTHONPATH`` — und ein Kind, dem der
    # Waechter absichtlich einen KAPUTTEN Vorspann mitgibt, fand ueber den
    # geerbten Pfad doch den echten. Drei Kanarienvogel-Tests wurden dadurch
    # rot, ohne dass etwas kaputt war. Wer den Vorspann bestimmt, bestimmt ihn
    # ganz.
    _echt = os.path.abspath(SHIM)
    pfade = [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep)
             if p and os.path.abspath(p) not in (_echt, os.path.abspath(shim))]
    env["PYTHONPATH"] = os.pathsep.join([shim] + pfade)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Der Beleg des EIGENEN Vorspanns gehoert nicht ins Kind — das Kind setzt
    # ihn selbst, wenn sein Vorspann laeuft.
    env.pop(AKTIV_VAR, None)
    if tage:
        env["LIGHTOS_ZEITSPRUNG_TAGE"] = str(tage)
        env["LIGHTOS_ZEITSPRUNG_UHR"] = uhr
        env["LIGHTOS_ZEITSPRUNG_ERWARTET"] = (
            echt_heute() + datetime.timedelta(days=tage)).isoformat()
    else:
        for schluessel in ("LIGHTOS_ZEITSPRUNG_TAGE", "LIGHTOS_ZEITSPRUNG_UHR",
                           "LIGHTOS_ZEITSPRUNG_ERWARTET"):
            env.pop(schluessel, None)
    return env


def lauf(dateien, tage: int, shim: str = SHIM, zeitlimit: int = 480,
         uhr: str = SPRUNG_UHR) -> Ergebnis:
    """pytest im Kindprozess ueber ``dateien``, Uhr um ``tage`` vorgerueckt.

    Der Kindprozess bekommt eigene Datenpfade (``LIGHTOS_SHOW_DB``): mehrere
    Tests im Haus starten pytest als Kind, und ``tests/conftest.py`` behandelt
    einen GEERBTEN Pfad ausdruecklich als fremdes Eigentum (Lehre aus QA-53 —
    ein Kind loeschte dem Elternprozess die Show-Datenbank unter den Fuessen weg).

    ``zeitlimit`` liegt bewusst UNTER dem 600-s-Deckel des Gate-Tests
    (``pytestmark``): haengt ein Kind, soll der Deckel hier fallen und das Kind
    mitnehmen — nicht der aeussere, der den Kindprozess verwaist zurueckliesse.
    Groesster gemessener Lauf: ~25 s fuer alle Kandidaten.
    """
    with tempfile.TemporaryDirectory(prefix="zeitbomben_") as tmp:
        env = sprung_umgebung(tage, shim=shim, uhr=uhr)
        env["LIGHTOS_SHOW_DB"] = os.path.join(tmp, "show.db")
        befehl = [sys.executable, "-m", "pytest", "-q", "--tb=short",
                  "-p", "no:cacheprovider"]
        if tage:
            befehl += ["-p", KANARIE_PLUGIN]
        befehl += [os.path.relpath(d, REPO) if d.startswith(REPO) else d
                   for d in dateien]
        fertig = subprocess.run(befehl, cwd=REPO, env=env, text=True, encoding="utf-8",
                                capture_output=True, timeout=zeitlimit)
    ausgabe = (fertig.stdout or "") + (fertig.stderr or "")
    wirksam = (not tage) or (MARKE_OK in ausgabe)
    return Ergebnis(fertig.returncode, ausgabe, wirksam)


class SprungUnwirksam(RuntimeError):
    """Der Uhr-Vorspann hat nicht gegriffen — das Ergebnis beweist nichts."""


def pruefe(wurzel: str, tage: int = SPRUNG_TAGE, shim: str = SHIM,
           dateien=None, uhr: str = SPRUNG_UHR) -> Bericht:
    """Der ganze Waechter: Kandidaten suchen, Sprung fahren, Urteil faellen."""
    kand = kandidaten(wurzel) if dateien is None else [
        (d, _funde(d)) for d in dateien]
    fahren = zu_fahren(kand)
    if not fahren:
        return Bericht(kand, [], [], tage, "keine Kandidaten")

    gesamt = lauf(fahren, tage, shim=shim, uhr=uhr)
    if not gesamt.sprung_wirksam:
        raise SprungUnwirksam(
            f"Die Zeile '{MARKE_OK}' fehlt in der Ausgabe — der Uhr-Vorspann "
            f"hat nicht gegriffen. Ein gruener Lauf beweist hier NICHTS.\n"
            f"{gesamt.ausgabe[-3000:]}")
    if gesamt.rc == 0:
        return Bericht(kand, [], [], tage, gesamt.ausgabe)

    # Erst wenn etwas rot ist, kostet es Zeit: Datei fuer Datei, und jede rote
    # noch einmal OHNE Sprung. Nur was mit Sprung rot und ohne Sprung gruen ist,
    # ist eine Zeitbombe — alles andere ist ein gewoehnlicher Fehlschlag und
    # gehoert nicht diesem Gate.
    # ★ Hier steht bewusst KEINE zweite Kanarienvogel-Pruefung, obwohl eine
    # naheliegt. Sie waere nicht pruefbar: der Sammellauf oben hat den Beleg
    # schon erbracht, und die Einzellaeufe erben Umgebung und Vorspann
    # unveraendert. Als Mutante gefahren (2026-08-22) blieb sie gruen —
    # nach der Hausregel gehoert solcher Code entfernt statt behauptet.
    #
    # ★ Nebeneffekt, der hier Absicht ist: ein einmaliges FLACKERN kommt nicht
    # bis zum Urteil. Der Sammellauf oben und der Einzellauf hier sind zwei
    # unabhaengige Laeufe derselben Datei; wer nur im ersten rot war, faellt in
    # `continue`. Gemeldet wird nur, was ZWEIMAL mit Sprung rot war und danach
    # ohne Sprung gruen. Das ist wichtig, weil unter den Kandidaten ein
    # Qt/Threading-Test steht (`test_grand_master_thread_marshal`) und ein
    # Fehlalarm dieses Gate abschalten wuerde.
    bomben, schon_rot = [], []
    for pfad in fahren:
        mit = lauf([pfad], tage, shim=shim, uhr=uhr)
        if mit.rc == 0:
            continue
        ohne = lauf([pfad], 0, shim=shim, uhr=uhr)
        if ohne.rc == 0:
            bomben.append((pfad, mit.ausgabe))
        else:
            schon_rot.append((pfad, ohne.ausgabe))
    return Bericht(kand, bomben, schon_rot, tage, gesamt.ausgabe)


# ─────────────────────────── 3. Proben (Selbsttest) ─────────────────────────

_PROBE_KOPF = '''"""Wegwerf-Probe des Zeitbomben-Waechters — %(art)s.

Erzeugt von tools/zeitbomben_gate.py. Das Datum unten ist ein ECHTES festes
Kalenderdatum, frisch auf den Lauftag bezogen: heute gruen, spaeter je nach
Bauart rot oder gruen.
"""
import os
import sys

REPO = %(repo)r
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)

import collect_crash_report as cci  # noqa: E402

STEMPEL = "%(datum)sT10:00:00"
SRC = r"C:\\repo\\lightos-main\\src\\ui\\views\\live_view.py"


def _bericht():
    log = ("=== Python Exception " + STEMPEL + " ===\\n"
           "Traceback (most recent call last):\\n"
           '  File "' + SRC + '", line 2, in b\\n'
           "NewError: neu\\n")
    return cci.format_report(cci.parse_log(log), seen=set())
'''

_PROBE_BOMBE = '''

def test_ein_frischer_fehler_gilt_nicht_als_kalt():
    """DIE ZEITBOMBE: festes Datum gegen eine Schwelle, die an HEUTE haengt.

    `_cold_before()` ist 30 Tage vor heute. Der Stempel oben ist beim Bauen
    3 Tage alt — also warm. In 30 Tagen ist er kalt, und dieser Test wird rot,
    ohne dass jemand etwas geaendert hat. Genau der Fehlschlag aus QA-62.
    """
    zeile = next(z for z in _bericht().splitlines() if STEMPEL in z)
    assert "\\u2744" not in zeile, (
        f"Stempel {STEMPEL} gilt als kalt (Schwelle {cci._cold_before()})")
'''

_PROBE_HARMLOS = '''

def test_der_fehler_steht_mit_stempel_und_signatur_im_bericht():
    """DIE POSITIVKONTROLLE: dasselbe feste Datum, dasselbe Produktionsmodul,
    derselbe Aufruf — nur ohne Kopplung an eine gleitende Schwelle.

    Beanstandet der Waechter DIESE Datei, beanstandet er auch die neun gesunden
    Dateien im Repo und wird nach dem zweiten Fehlalarm abgeschaltet.
    """
    bericht = _bericht()
    assert STEMPEL in bericht
    assert "NewError@live_view.py:2" in bericht
'''

_PROBE_SCHON_ROT = '''

def test_diese_probe_ist_schon_heute_rot():
    """Ein gewoehnlicher Fehlschlag — KEINE Zeitbombe. Der Waechter darf ihn
    nicht als eine melden, sonst schiebt er fremde Fehler in seine Spalte."""
    assert STEMPEL == "das ist absichtlich falsch"
'''

_PROBEN = {"bombe": _PROBE_BOMBE, "harmlos": _PROBE_HARMLOS,
           "schon_rot": _PROBE_SCHON_ROT}


def probe_schreiben(ordner: str, art: str, tage_alt: int = 3,
                    repo: str = REPO) -> str:
    """Eine Wegwerf-Testdatei mit frisch gepraegtem festem Datum.

    ★ Warum das Datum erzeugt und nicht eingecheckt wird: eine eingecheckte
    Zeitbombe mit festem Datum waere selbst eine — sie waere ein paar Wochen
    nach dem Merge auch OHNE Sprung rot, und der Test „heute gruen, spaeter rot"
    wuerde dann seinerseits ohne Codeaenderung falsch. Der Waechter praegt sein
    Beweisstueck deshalb bei jedem Lauf neu.
    """
    datum = (echt_heute() - datetime.timedelta(days=tage_alt)).isoformat()
    quelle = (_PROBE_KOPF % {"art": art, "repo": repo, "datum": datum}
              + _PROBEN[art])
    pfad = os.path.join(ordner, f"test_probe_{art}.py")
    with open(pfad, "w", encoding="utf-8") as fh:
        fh.write(quelle)
    return pfad


# ─────────────────────────────────── CLI ────────────────────────────────────

def _anzeigepfad(pfad: str) -> str:
    """Repo-relativer Pfad mit ``/`` — auf jedem Betriebssystem gleich.

    QA-69: hier stand blankes ``os.path.relpath``. Das liefert auf Windows
    ``tests\\test_x.py``, waehrend derselbe Bericht zwei Zeilen weiter
    ``tests/test_crash_intake.py::RecencyTest`` als Vorbild nennt — die Ausgabe
    widersprach sich also in ihrer eigenen Schreibweise, und der Test darauf war
    auf Windows rot, ohne dass am Gate etwas falsch war.

    Ein Anzeigepfad ist kein Dateisystem-Zugriff: er wird gelesen, kopiert und
    in Testvergleiche gesteckt. Deshalb hat er genau eine Schreibweise.
    """
    return pathlib.PurePath(os.path.relpath(pfad, REPO)).as_posix()


def bericht_text(bericht: Bericht) -> str:
    """Der Befund als Text — getrennt von ``main``, damit er pruefbar ist,
    ohne einen ganzen Waechter-Lauf zu fahren."""
    zeilen = [f"Uhr um {bericht.tage} Tage vorgerueckt "
              f"({echt_heute() + datetime.timedelta(days=bericht.tage)})."]
    for pfad, _ in bericht.schon_rot:
        zeilen.append(f"  … {_anzeigepfad(pfad)} ist schon HEUTE rot "
                      f"— nicht Sache dieses Gates")
    if not bericht.bomben:
        zeilen.append("GRUEN — keine Zeitbombe.")
        return "\n".join(zeilen)
    for pfad, ausgabe in bericht.bomben:
        zeilen.append("")
        zeilen.append(f"★ ZEITBOMBE: {_anzeigepfad(pfad)}")
        zeilen.append("   heute gruen, mit vorgerueckter Uhr rot — sie wird "
                      "ohne Codeaenderung rot.")
        zeilen.append("   Reparatur: das feste Datum am Lauftag ausrechnen "
                      "(Vorbild: tests/test_crash_intake.py::RecencyTest).")
        zeilen.extend(ausgabe.splitlines()[-20:])
    return "\n".join(zeilen)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tage", type=int, default=SPRUNG_TAGE,
                   help=f"Sprungweite in Tagen (Vorgabe {SPRUNG_TAGE})")
    p.add_argument("--nur-kandidaten", action="store_true",
                   help="nur die statische Vorauswahl zeigen, nichts fahren")
    p.add_argument("--uhr", choices=("datum", "alle"), default=SPRUNG_UHR,
                   help="welche Uhren verschoben werden; 'alle' zieht time.time "
                        "mit und erzeugt gemessen drei Fehlalarme (Dateialter)")
    a = p.parse_args(argv)

    tests = os.path.join(REPO, "tests")
    kand = kandidaten(tests)
    alle = testdateien(tests)
    print(f"Kandidaten: {len(kand)} von {len(alle)} Testdateien "
          f"tragen ein festes Datum ausserhalb von Docstrings")
    for pfad, funde in kand:
        kurz = ", ".join(f"{f.zeile}:{f.text}" for f in funde[:4])
        marke = "  [ausgenommen]" if os.path.basename(pfad) in SELBST else ""
        print(f"  {_anzeigepfad(pfad)}  ({len(funde)}) {kurz}{marke}")
    if a.nur_kandidaten:
        return 0

    try:
        bericht = pruefe(tests, tage=a.tage, uhr=a.uhr)
    except SprungUnwirksam as e:
        print(f"\nFEHLER: {e}")
        return 2
    print()
    print(bericht_text(bericht))
    return 0 if bericht.gruen else 1


if __name__ == "__main__":
    # XPLAT-20: Windows-Konsolen und -Pipes laufen ohne PYTHONUTF8 auf cp1252.
    # Die Statuszeichen dieses Werkzeugs (✓ ⚠ ★ ⏳) haben dort keine Abbildung,
    # der Bericht stirbt also mitten in der Ausgabe an einem UnicodeEncodeError.
    # Bewusst HIER und nicht auf Modulebene: beim Import (Tests laden die
    # Werkzeuge per exec_module) bleibt der Datenstrom des Aufrufers unberuehrt.
    for _strom in (sys.stdout, sys.stderr):
        if hasattr(_strom, "reconfigure"):
            _strom.reconfigure(encoding="utf-8")
    raise SystemExit(main())
