"""QA-61 — kein Test darf ein Geraet nennen, das es nur auf EINEM Rechner gibt.

**Der Anlass (FM-24, 22.08.2026).** Ein Test patchte ``"Speider"`` mit 14
Kanaelen — ein per QLC+ importiertes Profil **mit Tippfehler im Namen**, das nur
in Robins Bibliothek liegt. Auf diesem Rechner gruen, in der CI rot: die Suche
lieferte ``None``, und ``int(None)`` warf.

**Warum das keine Einzelfallkorrektur bleiben darf.** Der Kommentar an den
``_pid``-Helfern warnt vor der Suche ueber den **Anzeigenamen** (QA-23,
*„existiert je nach Rechner nur lokal"*). Genau dasselbe gilt aber fuer den
**Kurznamen** — die Umstellung von Anzeige- auf Kurzname schuetzt kein Stueck.
Gemessen am 22.08.2026 auf diesem Rechner: der Quelltext-Seed liefert **48
Kurznamen**, die abgelegte Bibliothek haelt **1790 Profile**, davon **1741 mit
einem Kurznamen, den kein Builtin traegt**. Ein Kurzname aus einem Test trifft
also mit weit hoeherer Wahrscheinlichkeit etwas nur Lokales als etwas
Mitgeliefertes — und ``'Speider'`` liegt dort tatsaechlich, mit
``source='qlcplus'`` und dem Tippfehler in Anzeige- UND Kurzname.

**Was hier geprueft wird.** Die in ``tests/*.py`` genannten Geraetenamen werden
gegen eine **frisch aus dem Quelltext geseedete Bibliothek** aufgeloest — nicht
gegen ``~/.local/share/LightOS/fixtures.db``. Genau die frische Bibliothek hat
die CI: ``_seed()`` + ``ensure_builtins()`` aus ``fixture_db.py``, sonst nichts.
Aufgeloest wird mit **derselben Abfrage**, die die Tests selbst fahren
(``where(FixtureProfile.short_name == …)``) bzw. mit der echten
``search_fixtures()`` — nicht mit einer nachgebauten Namensliste.

**Wie die Namen gefunden werden.** Ueber den Syntaxbaum, an der *Rolle* des
Literals, nicht an einer Textform:

1. ``…​.short_name == "X"`` und ``…​.short_name.in_(…)`` sind **Senken**.
2. Eine lokale Funktion, deren **Parameter** in einer Senke landet, ist selbst
   eine Senke an dieser Parameterstelle — transitiv (``_patch`` → ``_mode`` →
   ``short_name ==``). Damit ist ``_patch(1, "X", 22)`` erfasst, ohne dass der
   Waechter den Namen ``_patch`` kennen muesste.
3. Die **Produktions-Eingaenge** ``ShowBuilder.patch`` / ``ShowBuilder.profile_id``
   sind Senken an ihrem ``short_name``-Parameter — die Parameterstelle wird aus
   der **echten Signatur** gelesen (``inspect``), eine Umbenennung wird hier laut
   und nicht still.
4. ``search_fixtures("…")`` ist die **Anzeigenamen**-Senke aus QA-23.

Was der Waechter NICHT sieht, steht in
``test_die_bekannten_luecken_sind_gefahren`` — als Liste, damit sie
jemandem auffaellt, statt unbemerkt zu bleiben.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import unittest
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TESTS = os.path.dirname(os.path.abspath(__file__))

# ── Produktions-Eingaenge, die einen Kurznamen entgegennehmen ────────────────
# (Modul, Klasse oder None, Funktion). Die Parameterstelle wird NICHT hier
# notiert, sondern aus der echten Signatur gelesen — sonst waere dieser Block
# eine zweite Wahrheit, die beim naechsten Umbenennen still falsch wird.
_EINGAENGE = (
    ("src.core.show.showbuilder.builder", "ShowBuilder", "patch"),
    ("src.core.show.showbuilder.builder", "ShowBuilder", "profile_id"),
)
_KURZNAME_PARAM = "short_name"

# Namen, die absichtlich in KEINER Bibliothek stehen. Jeder Eintrag braucht eine
# Begruendung; `test_keine_ausnahme_ist_ueberfluessig` wirft ihn wieder raus,
# sobald er nicht mehr gebraucht wird — eine tote Ausnahme ist ein blinder Fleck.
_AUSNAHMEN: dict[tuple[str, str], str] = {
    ("test_showbuilder.py", "NICHTEXISTENT_XYZ_999"):
        "Negativtest: ShowBuilder.patch MUSS bei einem unbekannten Profil "
        "BuildError werfen statt eine inerte Fixture zu patchen.",
    # ★ Diese Datei legt ihre Geraete SELBST an — ueber den echten
    # Editor-Dialog, per `QTest.keyClicks` in das Kurznamen-Feld. Der Wert
    # reist als Parameter durch; das ist Luecke 1+2 der Liste unten.
    # Ohne diese Eintraege beanstandet der Waechter ELF gesunde Fundstellen
    # (gemessen 24.08.2026). Ein Gate, das gesunden Code anschlaegt, wird
    # abgeschaltet und ist dann schlechter als keines (QA-54).
    **{("test_fm23_geometrie_ueber_die_bedienelemente.py", n):
       "Vom Test selbst ueber den Editor-Dialog eingetippt (Praefix TIPP)."
       for n in ("TIPP48", "TIPP00", "TIPP0C", "TIPP2M", "TIPP256", "TIPP300")},
    ("test_qa61_nur_lokale_geraete.py", "Speider"):
        "Der Waechter selbst: die Negativkontrolle unten fragt die frische "
        "Bibliothek nach genau dem Namen aus FM-24 und erwartet ein Nein. "
        "Er steht hier als Eintrag statt als ausgenommene Datei, damit der "
        "Rest DIESER Datei weiter mitgeprueft wird.",
}


class Fund(NamedTuple):
    datei: str
    zeile: int
    name: str


# ── Die Wege, auf denen ein Test ein Geraet nennen kann ──────────────────────
#
# Jede Zeile ist EINE Erkennungsart des Waechters, und jede wird unten in BEIDE
# Richtungen gemessen: mit einem nur lokalen Namen muss sie anschlagen, mit
# einem Builtin darf sie es nicht. Ohne diese Tabelle blieben mehrere Zweige
# unbemessen — die bestehenden Tests nennen naemlich ausschliesslich Builtins,
# eine kaputte Erkennung faellt dort gar nicht auf.
#
# ``LOKAL`` ist der Originalfall aus FM-24: ein QLC+-Import aus Robins
# Bibliothek (``U-King-Speider.qxf``), mit Tippfehler im Namen.
_LOKAL = "Speider"
_BUILTIN = "SPIDER14"
_LOKAL_ANZEIGE = "U King Speider 14ch"
_BUILTIN_ANZEIGE = "HYDRABEAM 4000 RGBW"

_KOPF = (
    "from sqlalchemy import select\n"
    "from src.core.database import fixture_db\n"
    "from src.core.database.models import FixtureProfile\n"
    "from src.core.show.showbuilder.builder import ShowBuilder\n"
    "\n"
)

_PID = (
    "def _pid(short):\n"
    "    return select(FixtureProfile.id).where(\n"
    "        FixtureProfile.short_name == short)\n"
)

# (Bezeichnung, nur-lokaler Name, Builtin-Name, Vorlage mit @ als Platzhalter)
_WEGE = (
    ("direkter Vergleich", _LOKAL, _BUILTIN,
     'def test_x(s):\n'
     '    s.execute(select(FixtureProfile.id).where(\n'
     '        FixtureProfile.short_name == "@"))\n'),

    ("Helfer, ein Sprung", _LOKAL, _BUILTIN,
     _PID +
     'def test_x():\n'
     '    _pid("@")\n'),

    ("Helfer, Schluesselwort-Argument", _LOKAL, _BUILTIN,
     _PID +
     'def test_x():\n'
     '    _pid(short="@")\n'),

    ("Methoden-Helfer, zwei Spruenge", _LOKAL, _BUILTIN,
     'class T:\n'
     '    def _mode(self, kurz, modus):\n'
     '        return select(FixtureProfile.id).where(\n'
     '            FixtureProfile.short_name == kurz), modus\n'
     '    def _patch(self, fid, kurz, kanaele):\n'
     '        return self._mode(kurz, "14-Kanal"), fid, kanaele\n'
     '    def test_x(self):\n'
     '        self._patch(1, "@", 14)\n'),

    ("ShowBuilder.patch", _LOKAL, _BUILTIN,
     'def test_x():\n'
     '    b = ShowBuilder(reset=True)\n'
     '    b.patch("@", count=1, channel_count=14)\n'),

    ("ShowBuilder.profile_id ueber einen Helfer", _LOKAL, _BUILTIN,
     'def _profil_id(kurzname):\n'
     '    return ShowBuilder(reset=False).profile_id(kurzname)\n'
     'def test_x():\n'
     '    _profil_id("@")\n'),

    ("in_() ueber ein Woerterbuch", _LOKAL, _BUILTIN,
     'def test_x(s):\n'
     '    erwartet = {"@": "moving_head"}\n'
     '    return s.execute(select(FixtureProfile.id).where(\n'
     '        FixtureProfile.short_name.in_(erwartet))), erwartet\n'),

    ("Schleife ueber Tupelpaare", _LOKAL, _BUILTIN,
     _PID +
     'def test_x():\n'
     '    for kurz, modus in (("@", "14-Kanal"),):\n'
     '        _pid(kurz), modus\n'),

    ("Klassenattribut-Liste", _LOKAL, _BUILTIN,
     _PID +
     'class T:\n'
     '    _SHORTS = ("@",)\n'
     '    def test_x(self):\n'
     '        for kurz in self._SHORTS:\n'
     '            _pid(kurz)\n'),

    ("search_fixtures (Anzeigename, QA-23)", _LOKAL_ANZEIGE, _BUILTIN_ANZEIGE,
     'def test_x():\n'
     '    return fixture_db.search_fixtures("@")\n'),
)

# ── Und die Wege, die der Waechter NICHT sieht ───────────────────────────────
#
# ★ Eine benannte Luecke ist besser als eine unbemerkte — aber eine BEHAUPTETE
# Luecke ist nur eine Notiz. Jede hier ist gefahren: die Probe nennt
# ``"Speider"``, und der Waechter meldet nichts. Wird eine Zeile rot, ist die
# Luecke zu und die Liste im Docstring von
# ``test_die_bekannten_luecken_sind_gefahren`` gehoert nachgezogen.
# (Bezeichnung, Quelle der Probe, weitere Dateien im selben Verzeichnis)
_LUECKEN: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("zusammengesetzter Name",
     _PID +
     'def test_x():\n'
     '    _pid("Spe" + "ider")\n', {}),

    ("f-String",
     _PID +
     'def test_x():\n'
     '    teil = "ider"\n'
     '    _pid(f"Spe{teil}")\n', {}),

    ("Helfer aus einer FREMDEN Testdatei",
     'from _qa61_hilfe import pid\n'
     'def test_x():\n'
     '    pid("Speider")\n',
     {"_qa61_hilfe.py":
      "from sqlalchemy import select\n"
      "from src.core.database.models import FixtureProfile\n"
      "def pid(short):\n"
      "    return select(FixtureProfile.id).where(\n"
      "        FixtureProfile.short_name == short)\n"}),

    ("Anzeigename ohne search_fixtures",
     'def test_x(s):\n'
     '    return s.execute(select(FixtureProfile.id).where(\n'
     '        FixtureProfile.name == "Speider"))\n', {}),
)


# ── Der Syntaxbaum-Teil ──────────────────────────────────────────────────────

def _params(fd: ast.AST) -> list[str]:
    a = fd.args
    return [p.arg for p in (a.posonlyargs + a.args)]


def _empfaenger(call: ast.Call) -> ast.AST | None:
    """Der Ausdruck links vom Punkt — ``b`` in ``b.patch(...)``."""
    return call.func.value if isinstance(call.func, ast.Attribute) else None


def _aufrufname(call: ast.Call) -> tuple[str | None, bool]:
    """(Name der gerufenen Funktion, wird sie als Methode gerufen?)

    Die Unterscheidung haengt an der **Aufrufform**, nicht am Empfaengernamen:
    ``b.patch(...)`` und ``self._patch(...)`` verschieben beide die Argumente um
    eins gegen die Signatur, ``patch(...)`` nicht. (Ein Modulaufruf
    ``mod.func(...)`` verschiebt nichts — er hat kein ``self`` an Stelle 0, und
    genau daran wird unten entschieden.)
    """
    f = call.func
    if isinstance(f, ast.Name):
        return f.id, False
    if isinstance(f, ast.Attribute):
        return f.attr, True
    return None, False


class _Baum:
    """Ein eingelesener Test — Funktionen, Namensbindungen, Senken."""

    def __init__(self, quelle: str, extern: dict[str, tuple[str | None, list[str]]]):
        self.baum = ast.parse(quelle)
        self.extern = extern

        self.funcs: dict[str, list[ast.AST]] = {}
        for k in ast.walk(self.baum):
            if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs.setdefault(k.name, []).append(k)

        # Knoten -> umschliessende Funktion
        self.umschliesst: dict[int, ast.AST | None] = {}

        def rek(n, fd):
            for kind in ast.iter_child_nodes(n):
                self.umschliesst[id(kind)] = fd
                rek(kind, kind if isinstance(
                    kind, (ast.FunctionDef, ast.AsyncFunctionDef)) else fd)
        rek(self.baum, None)

        # Name -> (Knoten mit den Literalen, Position im Tupel-Ziel oder None)
        self.bindung: dict[str, tuple[ast.AST, int | None]] = {}
        for k in ast.walk(self.baum):
            if isinstance(k, ast.Assign):
                for ziel in k.targets:
                    if isinstance(ziel, ast.Name):
                        self.bindung.setdefault(ziel.id, (k.value, None))
            elif isinstance(k, (ast.For, ast.AsyncFor)):
                if isinstance(k.target, ast.Name):
                    self.bindung.setdefault(k.target.id, (k.iter, None))
                elif isinstance(k.target, ast.Tuple):
                    for i, el in enumerate(k.target.elts):
                        if isinstance(el, ast.Name):
                            self.bindung.setdefault(el.id, (k.iter, i))

        # Namen, die in DIESER Datei eine Instanz eines Produktions-Eingangs
        # halten: `b = ShowBuilder()` -> {"ShowBuilder": {"b"}}. Ohne diese
        # Zuordnung faenge `patch` auch `mock.patch("src.…")` ein — gemessen
        # 21 solche Fundstellen in 7 Dateien, alles falsche Alarme.
        self.instanzen: dict[str, set[str]] = {}
        for k in ast.walk(self.baum):
            if not isinstance(k, ast.Assign) or not isinstance(k.value, ast.Call):
                continue
            f = k.value.func
            klasse = f.id if isinstance(f, ast.Name) else (
                f.attr if isinstance(f, ast.Attribute) else None)
            if klasse is None:
                continue
            for ziel in k.targets:
                if isinstance(ziel, ast.Name):
                    self.instanzen.setdefault(klasse, set()).add(ziel.id)
                elif isinstance(ziel, ast.Attribute):
                    self.instanzen.setdefault(klasse, set()).add(ziel.attr)

    def _ist_instanz_von(self, knoten: ast.AST | None, klasse: str) -> bool:
        """Haelt dieser Ausdruck (plausibel) eine ``klasse``-Instanz?"""
        if knoten is None:
            return False
        namen = self.instanzen.get(klasse, set())
        if isinstance(knoten, ast.Name):
            return knoten.id == klasse or knoten.id in namen
        if isinstance(knoten, ast.Attribute):
            return knoten.attr == klasse or knoten.attr in namen
        if isinstance(knoten, ast.Call):          # ShowBuilder(...).profile_id(...)
            f = knoten.func
            return ((isinstance(f, ast.Name) and f.id == klasse)
                    or (isinstance(f, ast.Attribute) and f.attr == klasse))
        return False

    # ── Literale hinter einem Ausdruck ──────────────────────────────────────
    def literale(self, knoten: ast.AST, pos: int | None = None,
                 tiefe: int = 0) -> set[str]:
        """Die Zeichenketten, die dieser Ausdruck an einer Senke einsetzen kann.

        ``pos`` ist die Stelle im entpackten Tupel: bei
        ``for kurz, modus in (("MH8", "8-Kanal"), …)`` traegt ``kurz`` die
        Position 0. Ohne diese Stelle wuerden die Modusnamen mitgelesen und der
        Waechter beanstandete gesunde Dateien.
        """
        if tiefe > 6:
            return set()
        if isinstance(knoten, ast.Constant):
            return {knoten.value} if (pos is None
                                      and isinstance(knoten.value, str)) else set()
        if isinstance(knoten, (ast.List, ast.Tuple, ast.Set)):
            out: set[str] = set()
            for el in knoten.elts:
                if pos is None:
                    # NICHT rekursiv in verschachtelte Behaelter: sonst kaeme aus
                    # (("MH8", "8-Kanal"), …) auch der Modusname mit.
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        out.add(el.value)
                elif isinstance(el, (ast.List, ast.Tuple)) and len(el.elts) > pos:
                    out |= self.literale(el.elts[pos], None, tiefe + 1)
            return out
        if isinstance(knoten, ast.Dict):
            out = set()
            for schluessel in knoten.keys:
                if isinstance(schluessel, ast.Constant) and isinstance(schluessel.value, str):
                    out.add(schluessel.value)
            return out
        if isinstance(knoten, ast.Name):
            gebunden = self.bindung.get(knoten.id)
            if gebunden is not None:
                knoten2, pos2 = gebunden
                return self.literale(knoten2, pos if pos is not None else pos2,
                                     tiefe + 1)
            return set()
        if isinstance(knoten, ast.Attribute):
            # self._SHORTS / cls._SHORTS -> die Klassenzuweisung.
            gebunden = self.bindung.get(knoten.attr)
            if gebunden is not None:
                knoten2, pos2 = gebunden
                return self.literale(knoten2, pos if pos is not None else pos2,
                                     tiefe + 1)
        return set()

    # ── Senken ──────────────────────────────────────────────────────────────
    def _funktion_um(self, knoten: ast.AST, name: str) -> ast.AST | None:
        """Die naechste umschliessende Funktion, die ``name`` als Parameter hat."""
        fd = self.umschliesst.get(id(knoten))
        while fd is not None and name not in _params(fd):
            fd = self.umschliesst.get(id(fd))
        return fd

    def _signaturen(self, aufruf: ast.Call, name: str) -> list[list[str]]:
        """Alle Parameterlisten, die zu diesem Aufruf passen koennen."""
        passend = [_params(fd) for fd in self.funcs.get(name, [])]
        if name in self.extern:
            klasse, ps = self.extern[name]
            # Nur wenn der Empfaenger auch eine solche Instanz sein kann —
            # sonst zaehlte `mock.patch(...)` als ShowBuilder-Patch.
            if klasse is None or self._ist_instanz_von(_empfaenger(aufruf), klasse):
                passend.append(ps)
        return passend

    def _merken(self, aufruf, ausdruck, senken, treffer) -> None:
        """Was an einer Senke steht: ein Parameter macht seine Funktion zur
        Senke, ein aufloesbares Literal ist ein Fund. **Beides**, nicht
        entweder/oder — ein Parametername kann anderswo in derselben Datei auch
        eine Schleifenvariable sein (``def _load(short)`` neben
        ``for short in self._SHORTS``, gemessen in
        ``test_catalog_round2_profiles.py``). Wer sich hier fuer einen der
        beiden Wege entscheidet, verliert den anderen still.
        """
        if isinstance(ausdruck, ast.Name):
            fd = self._funktion_um(aufruf, ausdruck.id)
            if fd is not None:
                senken.add((fd.name, ausdruck.id))
        for lit in self.literale(ausdruck):
            treffer.append((aufruf.lineno, lit))

    def kurznamen(self) -> tuple[list[tuple[int, str]], set[str]]:
        """(Fundstellen ``(zeile, name)``, im Test SELBST angelegte Kurznamen)."""
        treffer: list[tuple[int, str]] = []
        senken: set[tuple[str, str]] = set()

        # 1. `.short_name == X` und `.short_name.in_(X)`
        for k in ast.walk(self.baum):
            if isinstance(k, ast.Compare):
                seiten = [k.left] + list(k.comparators)
                if not any(isinstance(s, ast.Attribute) and s.attr == "short_name"
                           for s in seiten):
                    continue
                for s in seiten:
                    if isinstance(s, ast.Attribute) and s.attr == "short_name":
                        continue
                    self._merken(k, s, senken, treffer)
            elif isinstance(k, ast.Call):
                f = k.func
                if (isinstance(f, ast.Attribute) and f.attr in ("in_", "notin_")
                        and isinstance(f.value, ast.Attribute)
                        and f.value.attr == "short_name"):
                    for arg in k.args:
                        self._merken(k, arg, senken, treffer)

        # 2. Externe Eingaenge (ShowBuilder.patch/…) sind von Anfang an Senken.
        for name, (_klasse, ps) in self.extern.items():
            if _KURZNAME_PARAM in ps:
                senken.add((name, _KURZNAME_PARAM))

        # 3. Fixpunkt: wer seinen Parameter an eine Senke weiterreicht, ist eine.
        while True:
            neu = set()
            for _name, arg, knoten in self._senkenargumente(senken):
                if isinstance(arg, ast.Name):
                    fd = self._funktion_um(knoten, arg.id)
                    if fd is not None:
                        neu.add((fd.name, arg.id))
            if neu <= senken:
                break
            senken |= neu

        # 4. Literale an Senkenstellen einsammeln.
        for _name, arg, knoten in self._senkenargumente(senken):
            for lit in self.literale(arg):
                treffer.append((knoten.lineno, lit))

        # 5. Kurznamen, die der Test selbst anlegt — die muessen nicht in der
        #    Bibliothek stehen, er bringt sie ja mit.
        eigen: set[str] = set()
        for k in ast.walk(self.baum):
            if (isinstance(k, ast.keyword) and k.arg == "short_name"
                    and isinstance(k.value, ast.Constant)
                    and isinstance(k.value.value, str)):
                eigen.add(k.value.value)
            elif isinstance(k, ast.Dict):
                for schluessel, wert in zip(k.keys, k.values):
                    if (isinstance(schluessel, ast.Constant)
                            and schluessel.value == "short_name"
                            and isinstance(wert, ast.Constant)
                            and isinstance(wert.value, str)):
                        eigen.add(wert.value)
        return sorted(set(treffer)), eigen

    def _senkenargumente(self, senken):
        """(Funktionsname, Argumentknoten, Aufrufknoten) fuer jede Senkenstelle."""
        for k in ast.walk(self.baum):
            if not isinstance(k, ast.Call):
                continue
            name, methode = _aufrufname(k)
            if name is None:
                continue
            for ps in self._signaturen(k, name):
                versatz = 1 if (methode and ps and ps[0] in ("self", "cls")) else 0
                for i, arg in enumerate(k.args):
                    j = i + versatz
                    if j < len(ps) and (name, ps[j]) in senken:
                        yield name, arg, k
                for kw in k.keywords:
                    if kw.arg and (name, kw.arg) in senken:
                        yield name, kw.value, k

    def suchbegriffe(self) -> list[tuple[int, str]]:
        """Literale an ``search_fixtures(...)`` — der Anzeigenamen-Weg (QA-23)."""
        out = []
        for k in ast.walk(self.baum):
            if not isinstance(k, ast.Call):
                continue
            name, _ = _aufrufname(k)
            if name != "search_fixtures":
                continue
            for arg in k.args:
                for lit in self.literale(arg):
                    out.append((k.lineno, lit))
        return sorted(set(out))


def externe_signaturen() -> dict[str, tuple[str | None, list[str]]]:
    """``{Funktionsname: (Klasse, Parameterliste)}`` — aus der ECHTEN Signatur."""
    out: dict[str, tuple[str | None, list[str]]] = {}
    for modulname, klasse, funktion in _EINGAENGE:
        modul = importlib.import_module(modulname)
        ziel = getattr(modul, klasse) if klasse else modul
        ps = list(inspect.signature(getattr(ziel, funktion)).parameters)
        if _KURZNAME_PARAM not in ps:
            raise AssertionError(
                f"{modulname}.{klasse}.{funktion} hat keinen Parameter "
                f"{_KURZNAME_PARAM!r} mehr ({ps}) — der Waechter wuerde diesen "
                "Weg ab jetzt still uebersehen. Eintrag in _EINGAENGE anpassen.")
        out[funktion] = (klasse, ps)
    return out


def _lies(pfad: str) -> str:
    with open(pfad, encoding="utf-8") as fh:
        return fh.read()


def genannte_geraete(verzeichnis: str,
                     extern: dict[str, tuple[str | None, list[str]]]
                     ) -> tuple[list[Fund], list[Fund]]:
    """(Kurznamen, Suchbegriffe) aller ``*.py`` in ``verzeichnis``."""
    kurz: list[Fund] = []
    such: list[Fund] = []
    for name in sorted(os.listdir(verzeichnis)):
        if not name.endswith(".py"):
            continue
        baum = _Baum(_lies(os.path.join(verzeichnis, name)), extern)
        treffer, eigen = baum.kurznamen()
        for zeile, lit in treffer:
            if lit in eigen:
                continue        # der Test legt dieses Profil selbst an
            kurz.append(Fund(name, zeile, lit))
        for zeile, lit in baum.suchbegriffe():
            such.append(Fund(name, zeile, lit))
    return kurz, such


# ── Der Test ─────────────────────────────────────────────────────────────────

class NurLokaleGeraeteTest(unittest.TestCase):
    """Der Waechter, seine Positiv- und seine Negativkontrolle."""

    @classmethod
    def setUpClass(cls):
        # Die Bibliothek, die die CI hat: frisch aus dem Quelltext geseedet.
        cls.eng = frische_library(cls)
        # ``frische_library`` faehrt nur ``_seed()``; im Betrieb ruft
        # ``engine()`` zusaetzlich ``ensure_builtins()``. Beides zusammen ist
        # der Stand, den ein frischer Rechner sieht.
        #
        # ⚠️ Diese Zeile ist heute WIRKUNGSLOS und das ist gemessen: auf einer
        # frisch geseedeten Bibliothek liefern ``_seed()`` und
        # ``_seed()+ensure_builtins()`` dieselben 48 Kurznamen (22.08.2026) —
        # ``ensure_builtins`` ruestet nur nach, was fehlt. Sie zu entfernen
        # bleibt entsprechend gruen (aequivalente Mutante). Sie steht hier
        # trotzdem, weil ``ensure_builtins`` der Ort ist, an dem neue Builtins
        # ueblicherweise zuerst auftauchen — ohne sie wuerde der Waechter ein so
        # eingefuehrtes Geraet faelschlich beanstanden.
        from src.core.database.fixture_db import ensure_builtins
        ensure_builtins()
        cls.extern = externe_signaturen()

    # ── Aufloesen gegen die frische Bibliothek — die ECHTEN Abfragen ────────
    def kennt_kurznamen(self, kurz: str) -> bool:
        """Dieselbe Abfrage, die die Tests selbst fahren."""
        from src.core.database.models import FixtureProfile
        with Session(self.eng) as s:
            return s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == kurz)).first() is not None

    def kennt_suchbegriff(self, begriff: str) -> bool:
        """Die echte ``search_fixtures()`` auf der frischen Bibliothek."""
        from src.core.database import fixture_db as FDB
        return bool(FDB.search_fixtures(begriff))

    def _unbekannt(self, verzeichnis: str) -> list[Fund]:
        kurz, such = genannte_geraete(verzeichnis, self.extern)
        schlecht = [f for f in kurz
                    if (f.datei, f.name) not in _AUSNAHMEN
                    and not self.kennt_kurznamen(f.name)]
        schlecht += [f for f in such
                     if (f.datei, f.name) not in _AUSNAHMEN
                     and not self.kennt_suchbegriff(f.name)]
        return schlecht

    # ── 1. Der Waechter selbst ──────────────────────────────────────────────
    def test_kein_test_nennt_ein_nur_lokales_geraet(self):
        schlecht = self._unbekannt(_TESTS)
        self.assertEqual(
            [], schlecht,
            "diese Tests nennen ein Geraet, das eine FRISCH geseedete "
            "Bibliothek nicht kennt — lokal gruen, in der CI rot (FM-24, "
            f"`int(None)`): {schlecht}. Loesung: ein Builtin aus "
            "src/core/database/fixture_db.py nehmen, oder das Profil im Test "
            "selbst anlegen (`short_name=...`). Gegenprobe: "
            "`LIGHTOS_FIXTURE_DB=/tmp/frisch.db ./venv/bin/python -m pytest ...`")

    # ── 2. Positivkontrolle: der Waechter beanstandet Gesundes NICHT ────────
    def test_die_suche_findet_die_bestehenden_tests_wirklich(self):
        """Ohne diese Zusicherung waere der Waechter stumm gruen, sobald das
        Verzeichnis, das Muster oder die Senkenerkennung nicht mehr greift —
        genau das ist die Betriebsart, in der ein Gate am gefaehrlichsten ist.

        Gemessen am 22.08.2026 auf `tests/` dieses Zweigs: **401 Fundstellen in
        67 Dateien, 38 verschiedene Kurznamen**, dazu 2 Suchbegriffe. Die
        Schwellen liegen darunter, damit das Loeschen einzelner Testdateien
        nicht sofort rot macht — aber weit ueber „findet fast nichts mehr".
        """
        kurz, such = genannte_geraete(_TESTS, self.extern)
        dateien = {f.datei for f in kurz}
        self.assertGreaterEqual(
            len(kurz), 300, f"kaum Kurznamen erkannt: {len(kurz)}")
        self.assertGreaterEqual(
            len(dateien), 55, f"kaum Dateien erkannt: {sorted(dateien)}")
        self.assertGreaterEqual(
            len({f.name for f in kurz}), 30,
            f"kaum verschiedene Namen: {sorted({f.name for f in kurz})}")
        # Je ein Vertreter der drei Kurznamen-Wege — faellt einer aus, ist die
        # Gesamtzahl oben noch lange nicht auffaellig klein.
        self.assertIn("test_claypaky_mythos_profile.py", dateien,     # direkt
                      "der direkte Vergleich `.short_name == \"…\"` wird nicht gesehen")
        self.assertIn("test_fm17_head_dimmer_map.py", dateien,        # Wrapper
                      "der Weg ueber einen Helfer (_patch -> _mode) wird nicht gesehen")
        self.assertIn("test_tool_smokedim.py", dateien,               # ShowBuilder
                      "ShowBuilder.patch(\"…\") wird nicht gesehen")
        self.assertGreaterEqual(len(such), 2, f"Suchbegriffe: {such}")

    def test_jeder_weg_laesst_ein_builtin_durch(self):
        """★ Positivkontrolle je Erkennungsart. Ein Waechter, der gesunde
        Dateien beanstandet, wird abgeschaltet — dann ist er schlechter als
        keiner."""
        for bezeichnung, _lokal, builtin, vorlage in _WEGE:
            with self.subTest(weg=bezeichnung):
                quelle = _KOPF + vorlage.replace("@", builtin)
                self.assertEqual(
                    [], self._unbekannt(self._verzeichnis(quelle)),
                    f"{bezeichnung}: Builtin {builtin!r} faelschlich beanstandet")

    def test_ein_selbst_angelegtes_profil_wird_nicht_beanstandet(self):
        """Ein Test darf sein eigenes Profil erfinden — es kommt ja mit."""
        quelle = (
            'from src.core.database.models import FixtureProfile\n'
            'def bau(s):\n'
            '    s.add(FixtureProfile(name="Eigenbau", short_name="EIGEN1"))\n'
            'def hole(s):\n'
            '    return s.query(FixtureProfile).filter(\n'
            '        FixtureProfile.short_name == "EIGEN1").first()\n'
        )
        self.assertEqual([], self._unbekannt(self._verzeichnis(quelle)))

    # ── 3. Negativkontrolle: der Waechter wird rot ──────────────────────────
    def test_jeder_weg_macht_bei_einem_nur_lokalen_geraet_rot(self):
        """★ Der Originalfall aus FM-24 — ``"Speider"``, mit Tippfehler —
        auf JEDEM Weg, den der Waechter zu sehen behauptet.

        Das Profil liegt in Robins Bibliothek (QLC+-Import
        ``U-King-Speider.qxf``) und in keiner frisch geseedeten. Faellt eine
        Erkennungsart aus, wird genau ihre Zeile hier rot — und nicht bloss eine
        Gesamtzahl irgendwo.
        """
        for bezeichnung, lokal, _builtin, vorlage in _WEGE:
            with self.subTest(weg=bezeichnung):
                quelle = _KOPF + vorlage.replace("@", lokal)
                schlecht = self._unbekannt(self._verzeichnis(quelle))
                self.assertEqual(
                    {lokal}, {f.name for f in schlecht},
                    f"{bezeichnung}: {lokal!r} nicht gefunden — dieser Weg "
                    f"kaeme unbemerkt durch. Funde: {schlecht}")

    # ── 4. Die Bibliothek, gegen die geprueft wird ──────────────────────────
    def test_geprueft_wird_gegen_die_frische_bibliothek(self):
        """Nicht gegen ``~/.local/share/LightOS/fixtures.db``.

        Gemessen am 22.08.2026 auf diesem Rechner (lesend, per sqlite3
        ``mode=ro``): die abgelegte Bibliothek haelt **1790 Profile**, davon 49
        mit ``source='builtin'`` — **1741 tragen einen Kurznamen, den kein
        Builtin traegt**. Der Quelltext-Seed liefert **49** (Stand 02.09.2026;
        die 1790/1741 sind die Messung vom 22.08.2026 und wandern mit). Faellt die frische
        Library weg und der Waechter fragt die abgelegte Datei, winkt er genau
        den Fall durch, den er fangen soll: ``'Speider'`` steht dort
        (``source='qlcplus'``, Anzeige- UND Kurzname).

        Beide Aufloeser werden hier gepinnt — der Kurzname-Weg UND der
        ``search_fixtures``-Weg. Ohne die zweite Haelfte koennte der
        Anzeigenamen-Weg unbemerkt die lokale Bibliothek befragen.
        """
        from src.core.database.models import FixtureProfile
        with Session(self.eng) as s:
            alle = [r[0] for r in s.execute(select(FixtureProfile.short_name))]
        # Die Zahl ist ein STOLPERDRAHT, kein Selbstzweck: sie faellt um, sobald
        # jemand ein Builtin hinzufuegt oder entfernt, und zwingt zu der Frage,
        # ob der Waechter noch die frische Bibliothek misst. 48 -> 49 am
        # 02.09.2026 durch STAIRMB5X5 (Stairville Matrix Blinder 5x5 RGBWW).
        self.assertEqual(49, len(alle), f"Builtin-Zahl geaendert: {sorted(alle)}")
        self.assertTrue(self.kennt_kurznamen("SPIDER14"))
        self.assertFalse(self.kennt_kurznamen("Speider"),
                         "'Speider' steht in der frischen Bibliothek — dann "
                         "misst dieser Test die lokale Datei statt den Quelltext")
        # 'Spiider' (Robe, zwei i) ist ein Builtin, 'Speider' (Tippfehler) nur
        # lokal — ein Zeichen Unterschied, und genau daran haengt FM-24.
        self.assertTrue(self.kennt_suchbegriff("Spiider"))
        self.assertFalse(self.kennt_suchbegriff("Speider"),
                         "search_fixtures() findet 'Speider' — dann fragt der "
                         "Anzeigenamen-Weg die lokale Bibliothek")

    def test_keine_ausnahme_ist_ueberfluessig(self):
        """Eine tote Ausnahme ist ein blinder Fleck, der niemandem auffaellt."""
        kurz, such = genannte_geraete(_TESTS, self.extern)
        vorhanden = {(f.datei, f.name) for f in kurz} | {(f.datei, f.name) for f in such}
        tot = sorted(k for k in _AUSNAHMEN if k not in vorhanden)
        self.assertEqual([], tot, f"Ausnahmen ohne Fundstelle: {tot}")
        for schluessel, grund in _AUSNAHMEN.items():
            self.assertGreater(len(grund), 30,
                               f"Ausnahme {schluessel} ohne Begruendung")

    def test_die_bekannten_luecken_sind_gefahren(self):
        """★ Der Waechter sieht NICHT alles. Die Liste gehoert dorthin, wo sie
        jemand liest, der ihn erweitert — nicht in eine Notiz.

        **Nicht gesehen:**

        1. **Zusammengesetzte Namen.** ``_pid("SPI" + "DER14")``, f-Strings,
           ``.format()``, aus einer Datei gelesene Namen — nur Literale werden
           aufgeloest.
        2. **Namen aus einer Zufalls-/Parameterquelle**, etwa
           ``pytest.mark.parametrize`` mit einer berechneten Liste.
        3. **Fremde Helfer.** Eine Senke wird nur innerhalb DERSELBEN Datei
           transitiv verfolgt (plus den in ``_EINGAENGE`` eingetragenen
           Produktions-Eingaengen). Ein Kurzname, der ueber einen Helfer in
           ``tests/_x.py`` laeuft, wird nicht gesehen.
        4. **Doppelte Funktionsnamen** in einer Datei werden zusammengeworfen —
           das erweitert die Suche, verengt sie nie (also keine falschen Gruen).
        5. **Anzeigenamen ausserhalb von ``search_fixtures()``.** Ein Vergleich
           ``profil.name == "…"`` wird NICHT geprueft: ``.name`` tragen auch
           Modi, Kanaele und Hersteller, eine Pruefung darauf beanstandete
           reihenweise Gesundes.
        6. **``tools/*.py``.** Die Build-Skripte nennen ebenfalls Kurznamen
           (``ShowBuilder.patch``), laufen aber nicht im Gate. Sie sind hier
           bewusst nicht erfasst — QA-61 fragt nach den TESTS.
        7. **Modusnamen und Kanalzahlen.** ``mode_name="14-Kanal"`` wird nicht
           gegen den Quelltext gehalten; ein Test kann ein Builtin nennen und
           trotzdem einen nur lokal existierenden Modus verlangen.

        Die Punkte 1, 3 und 5 sind unten **gefahren**, nicht bloss behauptet:
        jede dieser Proben nennt ``"Speider"``, und der Waechter sieht sie
        nicht. Wird hier eine Zeile rot, ist das eine gute Nachricht — die
        Luecke ist zu, und diese Liste gehoert nachgezogen.
        """
        for bezeichnung, quelle, weitere in _LUECKEN:
            with self.subTest(luecke=bezeichnung):
                ordner = self._verzeichnis(_KOPF + quelle, weitere)
                self.assertEqual(
                    [], self._unbekannt(ordner),
                    f"{bezeichnung}: der Waechter SIEHT das jetzt — Luecke "
                    "geschlossen, Liste im Docstring nachziehen")

    # ── Hilfsmittel fuer die Kontrollen ─────────────────────────────────────
    def _verzeichnis(self, quelle: str,
                     weitere: dict[str, str] | None = None) -> str:
        """Ein Wegwerf-Verzeichnis mit echten Dateien darin.

        Bewusst Dateien auf der Platte und nicht ein Zeichenketten-Stub: die
        Kontrollen fahren damit denselben Weg wie der Waechter oben
        (``os.listdir`` -> lesen -> ``ast.parse``), nicht einen abgekuerzten.
        """
        import shutil
        import tempfile
        ordner = tempfile.mkdtemp(prefix="qa61_")
        self.addCleanup(shutil.rmtree, ordner, True)
        for name, text in {"test_probe.py": quelle, **(weitere or {})}.items():
            with open(os.path.join(ordner, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        return ordner


if __name__ == "__main__":
    unittest.main()
