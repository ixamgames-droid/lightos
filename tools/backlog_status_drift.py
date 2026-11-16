#!/usr/bin/env python3
"""QA-64 — misst, ob der Status im BACKLOG.md noch zum CODE auf `main` passt.

Warum es dieses Werkzeug gibt
-----------------------------
Der Backlog-Status driftet gegen `main`, viermal in einer Woche beobachtet, jedes
Mal nach einer Merge-Runde. **Beide Richtungen kosten:**

* Ein Item auf ``todo``, dessen Arbeit laengst auf ``main`` steht, wird beim
  naechsten Lauf **erneut angeboten** — und jemand baut es ein zweites Mal.
* Ein Item auf ``review``/``done``, dessen Zweig nie gelandet ist, **rutscht als
  erledigt durch** — und niemand baut es ueberhaupt.

★ **Warum die naheliegende Pruefung NICHT geht.** „Ist der Zweig in ``main``?"
beantwortet ``git merge-base --is-ancestor`` — und liefert in diesem Repo fuer
JEDEN Zweig ``nein``, auch fuer die laengst gelandeten. Grund: hier wird
**squash-gemerged**; der Squash erzeugt einen neuen Commit, die Zweigspitze wird
nie ein Vorfahr von ``main``. Gemessen am 25.08.2026 an vier Zweigen, davon zwei
nachweislich gelandet (#653, #654) — ``is-ancestor`` sagte bei allen vieren
„nicht gemerged".

Ein Waechter, der alles beanstandet, wird abgeschaltet. Deshalb fragt dieses
Werkzeug nicht nach dem ZWEIG, sondern nach dem **Inhalt**: jedes Item kann eine
*Spur* hinterlegen — eine Datei und ein Kennzeichen darin, das es genau dann auf
``main`` gibt, wenn die Arbeit gelandet ist.

Die Spur steht als unsichtbarer Kommentar in der Item-Zeile::

    <!-- spur: tools/zeitbomben_gate.py :: ZEITSPRUNG-WIRKSAM -->

Ohne Kennzeichen genuegt die Existenz der Datei::

    <!-- spur: tools/zeitbomben_gate.py -->

Zwei getrennte Pruefungen
-------------------------
1. **Spur-Probe** (die eigentliche): Status ``done``/``✅`` -> Spur MUSS auf
   ``main`` sein. Status ``todo`` -> Spur darf NICHT auf ``main`` sein. Status
   ``review`` -> Spur darf NICHT auf ``main`` sein. Status ``blocked``/
   ``decision`` -> beides zulaessig, es wird nur berichtet.

   ★★ **QA-65 — die dritte Zeile war zur Haelfte falsch.** QA-64 gab jedem
   „unterwegs" einen Freibrief, begruendet mit „ein Item im PR hat seine Spur
   naturgemaess nicht auf ``main``". Das stimmt fuer diese eine Richtung. Die
   andere ist der **haeufigste Drift-Fall ueberhaupt**: ``review`` + Spur IST auf
   ``main`` heisst, der PR ist gelandet und nur der Status wurde nie nachgezogen.
   Gemessen auf ``main`` 28e137f2: **neun** Items standen genau so da (PROC-03,
   PROC-04, PROC-06, QA-63, QA-64, VIZ-53, FM-25, FM-29, UI-52) — alle neun
   gelandet, alle neun auf ``review``, Bericht „keine Drift".

   ★ **Warum ``blocked``/``decision`` den Freibrief behalten.** Gemessen an den
   11 Items dieser beiden Status im BACKLOG (25.08.2026): vier von ihnen nennen
   ueberhaupt Dateien, und **alle 8 genannten Dateien liegen bereits auf ``main``**
   (VCG-02: ``src/core/show/vc_assets.py``, ``vc_gallery.py``, ``stage/aim.py``;
   HW-4: ``docs/OPEN_POINTS_OVERVIEW.md``; VIZ-16: ``docs/VIZ3D_OVERHAUL_PLAN.md``,
   ``src/core/engine/tempo_bus.py``, ``tools/viz_render_benchmark.py``; PRIV-03:
   ``tools/pseudonymisieren.py``). Diese Status behaupten NICHT, dass etwas in
   einem PR haengt — sie behaupten, dass jemand auf Hardware oder eine
   Produktentscheidung wartet, waehrend die Vorarbeit laengst gelandet sein darf.
   Dieselbe Schaerfung dort haette also jedes blockierte Item mit Vorarbeit
   beanstandet: 4 Fehlalarme, 0 echte Funde.
2. **Zweig-Behauptung**: nennt der Status „Umsetzung auf ``X``", muss ``X`` auf
   ``origin`` existieren und darf keine neuere ``-vN``-Fassung haben. Genau das
   ist am 25.08. aufgefallen: FM-14b zeigte auf die erste von **drei** Fassungen,
   und die enthielt drei von vier Commits nicht.

   ★ Diese zweite Pruefung war zuerst breiter gebaut — sie las jeden Backtick der
   Form ``a/b`` als Zweignamen und beanstandete **60 Zeilen**, fast alle davon
   gewoehnliche Dateipfade (``tools/verify_loop.sh``, ``docs/…``). Der enge
   Zuschnitt „nur was der STATUS als Umsetzungszweig behauptet" fand dieselbe
   eine echte Drift und sonst nichts.

3. **Implizite Spur** (QA-64, 16.11.2026): Items ohne ausdrueckliche Spur
   gelten als gespurt, wenn eine Testdatei nach ihrer ID heisst
   (``UI-137`` -> ``tests/test_ui137_*.py``). Beanstandet wird nur ``todo`` +
   Datei im Baum; ``review`` + Datei wird als „wartet aufs Einsammeln" gezaehlt.
   Wirksamer Status = BACKLOG.md plus Fragment unter ``backlog.d`` (das
   Fragment uebersteuert). Ausnahme am Item: ``<!-- spur: keine -->``. Diese
   Pruefung braucht KEINE Refs und laeuft deshalb auch als CI-Test
   (``tests/test_qa64_implizite_spur.py``); ``--nur-implizit`` faehrt nur sie.

Warum ein Werkzeug und kein CI-Test
-----------------------------------
Beide Pruefungen brauchen Git-Refs, die es in der CI nicht gibt:
``actions/checkout@v4`` holt standardmaessig **einen** Commit ohne weitere Refs —
kein ``origin/main``, keine Zweigliste. Ein Test, der dort still ueberspringt,
waere genau die Sorte Absicherung, die dieses Repo schon zweimal teuer bezahlt
hat (PROC-02b, PROC-04): sie laeuft, wird gruen und wirkt nicht.

Die LOGIK ist trotzdem festgenagelt — ``tests/test_qa64_status_drift.py`` fuettert
sie mit Nachbildungen und prueft beide Richtungen. Was dort nicht geht, ist der
Griff nach dem echten Repo; genau dafuer ist diese Datei da.

Aufruf::

    ./venv/bin/python tools/backlog_status_drift.py           # Bericht
    ./venv/bin/python tools/backlog_status_drift.py --strict  # Exit 1 bei Drift
      (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

Es wird zuvor ``git fetch`` gefahren; schlaegt das fehl, bricht das Werkzeug mit
Exit 2 ab (*fail closed*, wie ``tools/backlog_ids.py``) — mit veralteten Refs
meldet es eine gerade gelandete Spur als „fehlt". ``--kein-fetch`` faehrt bewusst
auf dem zuletzt geholten Stand.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKLOG = os.path.join(REPO, "BACKLOG.md")

# <!-- spur: pfad/zur/datei.py :: KENNZEICHEN -->   (Kennzeichen optional)
# ★ QA-64 (Nachbesserung): `<!-- spur: keine -->` ist die Ausnahme fuer die
# implizite Spur, KEINE Datei namens „keine". Der Ausschluss steht im Muster
# selbst, damit JEDER Leser (auch tests/test_qa64_status_drift.py, der fuer
# erledigte Items die Spur-Datei verlangt) die Ausnahme ueberspringt — sonst
# wuerde ein Item mit Ausnahme spaetestens nach dem Einsammeln als `done` dort
# rot („Spuren ohne Datei: keine"). Steht daneben eine echte Spur, findet
# ``search`` die.
SPUR = re.compile(r"<!--\s*spur:(?!\s*keine\s*(?:::|-->))\s*([^:>]+?)\s*(?:::\s*(.+?)\s*)?-->")
# Nur was der STATUS behauptet — nicht jeder Backtick in der Beschreibung.
ZWEIG = re.compile(r"Umsetzung auf `([^`]+)`")

# ★★ Das LEITWORT entscheidet, nicht die ganze Zelle (CDX-57, von Codex
# gefunden). Die erste Fassung fragte `any(k in s for k in ("done", "✅"))` —
# und stufte damit jede Zelle als erledigt ein, die IRGENDWO einen Haken nennt.
# Gemessen auf `main` 28e137f2: **sieben** Items stehen auf `teils` und nennen
# im Fliesstext ein `✅` fuer einen fertigen TEILschritt (VIZ-15, VIZ-PERF2,
# VIZ-BEAM-OCCLUSION, FM-20, FM-13, XPLAT-19, DOC-10). Sobald eines davon eine
# Spur bekommt, verlangt der Waechter sie faelschlich auf `main`. Dieselbe
# Bauart las umgekehrt `teils (2026-07-09)` OHNE Haken (QA-LIVE, LAS-08) als
# „unterwegs" — zwei Zellen mit derselben Aussage, zwei verschiedene Klassen.
_LEITWORT = re.compile(r"^(?P<vor>[^0-9A-Za-zÄÖÜäöüß]*)(?P<wort>[0-9A-Za-zÄÖÜäöüß/]*)")

ERLEDIGT = ("done",)
OFFEN = ("todo",)
# ★ QA-65: `review` ist KEIN beliebiges „unterwegs" — der Status behauptet
# ausdruecklich, die Arbeit liege in einem PR und sei NICHT gelandet. Steht die
# Spur trotzdem auf `main`, widerspricht der Status sich selbst.
REVIEW = ("review",)
# ★ Diese Leitworte behaupten NICHTS ueber `main` — beide Spur-Zustaende sind
# richtig. Sie stehen namentlich hier und nicht im Default, weil ein Haken VOR
# dem Leitwort sie sonst nach „erledigt" zoege: `✅ teils (…)` ist teils, nicht
# fertig. Genau diese Verwechslung ist oben gemessen.
FREIBRIEF = ("teils", "blocked", "decision", "n/a")

REVIEW_SPUR_AUF_MAIN = ("Status sagt review, aber die Spur steht schon auf main"
                        " — der PR ist gelandet, nur der Status wurde nie"
                        " nachgezogen")


def zeilen_mit_items(text: str) -> list[tuple[str, str, str]]:
    """``(item, status, ganze Zeile)`` fuer jede Tabellenzeile mit einer ID."""
    treffer = []
    for z in text.splitlines():
        if not z.startswith("| "):
            continue
        sp = z.split("|")
        if len(sp) < 5:
            continue
        item, status = sp[1].strip(), sp[3].strip()
        # Kopf- und Trennzeilen haben keine ID-artige erste Spalte …
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", item):
            continue
        # … mit EINER Ausnahme: die Kopfzeile `| ID | Prio | Status | …` sieht
        # genauso aus wie ein Item namens "ID". Der eigene Test hat das gefangen
        # (sonst haette jede der Tabellen ein Geister-Item beigesteuert), und die
        # zweite Spalte entscheidet es sauber: jedes echte Item traegt dort eine
        # Prioritaet, die Kopfzeile das Wort "Prio".
        if not re.fullmatch(r"P[0-9]", sp[2].strip()):
            continue
        treffer.append((item, status, z))
    return treffer


def leitwort(status: str) -> tuple[str, str]:
    """``(Auszeichnung davor, Leitwort)`` — das erste WORT der Status-Zelle.

    ``"✅ done (2026-08-24)"`` -> ``("✅ ", "done")``,
    ``"⛔ n/a — kein Fund"`` -> ``("⛔ ", "n/a")``.
    """
    m = _LEITWORT.match(status.strip())
    return m.group("vor"), m.group("wort").lower()


def status_klasse(status: str) -> str:
    vor, wort = leitwort(status)
    if wort in ERLEDIGT:
        return "erledigt"
    if wort in OFFEN:
        return "offen"
    if wort in REVIEW:
        return "review"
    if wort in FREIBRIEF:
        return "unterwegs"
    # Ein Haken VOR dem Leitwort heisst erledigt, auch wenn das Wort selbst
    # unbekannt ist (`✅ verifiziert → 🎨 Design`). Ein Haken IM Fliesstext
    # heisst es nicht — das ist der ganze Unterschied zur alten Fassung.
    if "✅" in vor:
        return "erledigt"
    return "unterwegs"


def spur_urteil(klasse: str, auf_main: bool) -> str | None:
    """``None`` = in Ordnung, sonst der Text der Beanstandung.

    Die Regel steht bewusst hier und nicht im Aufrufer: sie ist die eigentliche
    Aussage des Werkzeugs, und der Test misst genau diese Funktion.
    """
    if klasse == "erledigt" and not auf_main:
        return "Status sagt erledigt, aber die Spur steht NICHT auf main"
    if klasse == "offen" and auf_main:
        return "Status sagt todo, aber die Spur steht bereits auf main"
    # ★ QA-65 — der haeufigste Drift-Fall ueberhaupt, und QA-64 hat ihn per
    # Bauart nicht angesehen: am 25.08.2026 standen NEUN gelandete Items auf
    # `review` (PROC-03/04/06, QA-63/64, VIZ-53, FM-25/29, UI-52), und der
    # Bericht meldete „keine Drift".
    if klasse == "review" and auf_main:
        return REVIEW_SPUR_AUF_MAIN
    # ★ Die GEGENRICHTUNG bleibt frei: `review` + Spur nicht auf main ist der
    # voellig normale Zustand eines Items, an dem gerade jemand arbeitet. Wer
    # beide meldet, hat einen Waechter gebaut, der bei jedem laufenden PR
    # anschlaegt — der wird abgeschaltet.
    return None


# ── Implizite Spur: die Testdatei, die nach der Item-ID heisst ───────────────
#
# ★★ Warum es sie gibt. Ausdrueckliche Spuren trugen am 16.11.2026 27 von 1064
# Items — von Hand nachzutragen waeren rund 1000 Zeilen in einer Datei, die seit
# PROC-20 kein PR mehr anfasst. Fast jedes Item bringt aber ohnehin eine
# Testdatei mit, die nach seiner ID heisst: ``UI-137`` -> ``test_ui137_*.py``.
# Diese Datei IST eine Spur, und sie braucht keine Git-Refs: es zaehlt nur, ob
# sie im Arbeitsbaum steht. Deshalb wirkt diese Pruefung als echter Test in der
# CI (``tests/test_qa64_implizite_spur.py``), die ausdrueckliche nicht.
#
# ★ Das Urteil ist bewusst ENG — nur ein einziger Fall wird beanstandet:
#   ``todo`` + ID-Testdatei im Baum. Genau der ist teuer: das Item wird beim
#   naechsten Lauf erneut angeboten, obwohl seine Arbeit (samt Test) gelandet ist.
#   * ``review`` + Datei ist seit dem Fragment-Verfahren (PROC-20) der NORMALE
#     Zustand — im PR und nach dem Merge, bis der Sammel-Lauf ``done`` daraus
#     macht. Das wird nur gezaehlt („wartet aufs Einsammeln"), nie rot.
#   * ``teils``/``blocked``/``decision``/zurueckgestellt: Vorarbeit samt Test darf
#     gelandet sein — kein Urteil (gleiche Begruendung wie beim Freibrief oben).
#   * ``done`` OHNE Datei: kein Urteil. Fehlt eine implizite Spur, gibt es
#     schlicht keine; viele Items haben ihren Test anders benannt.
#
# ★ Ausnahme am Item: ``<!-- spur: keine -->`` (optional ``:: Grund``) in der
# Zeile bzw. im Freitext des Fragments schaltet die implizite Spur ab — fuer den
# seltenen Fall, dass ein ``todo``-Item absichtlich schon eine ID-Testdatei hat.

KEINE_SPUR = re.compile(r"<!--\s*spur:\s*keine\s*(?:::[^>]*?)?-->")

IMPLIZIT_TODO = ("Status sagt todo, aber eine Testdatei mit dieser ID steht im"
                 " Baum — die Arbeit ist gelandet (oder: Ausnahme"
                 " <!-- spur: keine --> am Item)")


def id_schluessel(item_id: str) -> str:
    """Der Teil des Testdatei-Namens, der der ID entspricht.

    ``UI-137`` -> ``ui137``, ``FM-14b`` -> ``fm14b``, ``QA-LIVE`` -> ``qalive``.
    Bindestriche fallen weg, alles klein — so benennt das Repo seine Tests.
    """
    return re.sub(r"[^0-9a-z]", "", item_id.lower())


def datei_schluessel(dateiname: str) -> str | None:
    """Das ID-Stueck eines Testdatei-Namens: ``test_ui137_x.py`` -> ``ui137``.

    ★ Die ID-GRENZE ist der Unterstrich (bzw. das Dateiende): das Stueck ist
    alles zwischen ``test_`` und dem naechsten ``_``. Damit trifft ``UI-13``
    (``ui13``) die Datei ``test_ui137_x.py`` (``ui137``) nicht, und ``FM-14``
    nicht ``test_fm14b_x.py`` — verglichen wird auf GLEICHHEIT, nie per Praefix.
    """
    if not (dateiname.startswith("test_") and dateiname.endswith(".py")):
        return None
    stueck = dateiname[len("test_"):-len(".py")].split("_", 1)[0]
    return stueck or None


def testdateien_nach_schluessel(dateinamen) -> dict[str, list[str]]:
    """Die Dateiliste EINMAL zum Nachschlage-Index machen: Schluessel -> Namen."""
    index: dict[str, list[str]] = {}
    for n in sorted(dateinamen):
        s = datei_schluessel(n)
        if s:
            index.setdefault(s, []).append(n)
    return index


def implizite_spur(item_id: str, index: dict[str, list[str]]) -> list[str]:
    """Die Testdateien, die nach ``item_id`` heissen (leer = keine Spur).

    ★ Sonder-IDs ohne Nummer (``QA-LIVE``, ``VIZ-PERF``) werden genauso
    behandelt: ``qalive`` trifft nur ``test_qalive_*.py``, nie
    ``test_qa_live_*.py`` oder ``test_qalive2_*.py``. Gemessen am 16.11.2026:
    keine der 80 Sonder-IDs hat so eine Datei, also auch keinen Zufallstreffer
    (jede Backlog-ID hat einen Bindestrich; zusammengezogen ergibt das kein
    gewoehnliches Wort wie ``test_backlog_``).
    """
    return list(index.get(id_schluessel(item_id), ()))


def implizit_urteil(klasse: str, hat_datei: bool) -> str | None:
    """``None`` = kein Befund; ``"wartet"`` = review + Datei (nur zaehlen);
    sonst der Text der Beanstandung. Bewusst eng, siehe Kommentar oben."""
    if not hat_datei:
        return None
    if klasse == "offen":
        return IMPLIZIT_TODO
    if klasse == "review":
        return "wartet"
    return None


def _sammler():
    """``tools/backlog_sammeln.py`` — derselbe Leseweg fuer Fragmente wie dort."""
    hier = os.path.dirname(os.path.abspath(__file__))
    if hier not in sys.path:
        sys.path.insert(0, hier)
    import backlog_sammeln  # noqa: E402
    return backlog_sammeln


def wirksame_items(backlog_text: str, fragmente) -> list[tuple[str, str, str]]:
    """``(item, wirksamer Status, Text fuer Spur-Kommentare)`` je Item.

    Wirksam ist BACKLOG.md PLUS das Fragment: ein Fragment uebersteuert den
    Status der Zeile (so schreibt der Sammel-Lauf es spaeter hinein), sein
    Freitext zaehlt fuer Spur-Kommentare mit. Ein Fragment ohne Zeile ist ein
    neues Item und zaehlt ebenso. ``fragmente`` sind ``Fragment``-Objekte aus
    ``backlog_sammeln.lies_alle``.
    """
    je_frag = {f.id: f for f in fragmente}
    aus = []
    gesehen = set()
    for item, status, zeile in zeilen_mit_items(backlog_text):
        gesehen.add(item)
        f = je_frag.get(item)
        if f is None:
            aus.append((item, status, zeile))
        else:
            aus.append((item, f.status, zeile + "\n" + (f.freitext or "")))
    for item, f in sorted(je_frag.items()):
        if item not in gesehen:
            aus.append((item, f.status, f.freitext or ""))
    return aus


def implizite_pruefung(items, testdateien) -> dict:
    """Die ref-freie Pruefung ueber ``wirksame_items`` und eine Dateiliste.

    Liefert ``ausdruecklich``/``implizit``/``ohne``/``ausnahme`` (Item-Listen),
    ``wartet`` (review + Datei) und ``beanstandet`` (Texte).
    """
    index = testdateien_nach_schluessel(testdateien)
    erg = {"ausdruecklich": [], "implizit": [], "ohne": [], "ausnahme": [],
           "wartet": [], "beanstandet": []}
    for item, status, text in items:
        # Eine echte ausdrueckliche Spur geht vor (SPUR ueberspringt die
        # Ausnahme selbst); die Ausnahme betrifft nur die implizite Spur.
        if SPUR.search(text):
            erg["ausdruecklich"].append(item)
            continue
        if KEINE_SPUR.search(text):
            erg["ausnahme"].append(item)
            continue
        dateien = implizite_spur(item, index)
        if not dateien:
            erg["ohne"].append(item)
            continue
        erg["implizit"].append(item)
        urteil = implizit_urteil(status_klasse(status), True)
        if urteil == "wartet":
            erg["wartet"].append(item)
        elif urteil:
            erg["beanstandet"].append(
                f"{item}: {urteil}  (tests/{', tests/'.join(dateien)})")
    return erg


def implizite_pruefung_im_repo(repo: str = REPO) -> dict:
    """Dasselbe gegen den Arbeitsbaum: BACKLOG.md, Fragmente, ``tests/``."""
    from pathlib import Path
    bs = _sammler()
    with open(os.path.join(repo, "BACKLOG.md"), encoding="utf-8") as f:
        text = f.read()
    frags, _fehler = bs.lies_alle(Path(repo))
    tests = os.path.join(repo, "tests")
    namen = os.listdir(tests) if os.path.isdir(tests) else []
    return implizite_pruefung(wirksame_items(text, frags), namen)


def abdeckung(erg: dict) -> float:
    """Anteil der Items mit IRGENDEINER Spur (ausdruecklich oder implizit)."""
    gesamt = sum(len(erg[k]) for k in ("ausdruecklich", "implizit", "ohne", "ausnahme"))
    return (len(erg["ausdruecklich"]) + len(erg["implizit"])) / gesamt if gesamt else 0.0


def bericht_implizit(erg: dict) -> list[str]:
    gesamt = sum(len(erg[k]) for k in ("ausdruecklich", "implizit", "ohne", "ausnahme"))
    z = [f"[abdeckung] {gesamt} Items: ausdrueckliche Spur {len(erg['ausdruecklich'])},"
         f" implizite Spur (ID-Testdatei) {len(erg['implizit'])},"
         f" keine {len(erg['ohne'])}"
         + (f", Ausnahme 'spur: keine' {len(erg['ausnahme'])}" if erg["ausnahme"] else "")
         + f" — Abdeckung {abdeckung(erg):.0%}",
         f"[implizit] review + ID-Testdatei, wartet aufs Einsammeln: {len(erg['wartet'])}"]
    return z


# ── Der Griff nach dem echten Repo (in der CI nicht verfuegbar) ──────────────

def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(("git",) + args, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout


def spur_auf_main(datei: str, kennzeichen: str | None) -> bool:
    rc, inhalt = _git("show", f"origin/main:{datei}")
    if rc != 0:
        return False
    return True if not kennzeichen else (kennzeichen in inhalt)


def zweige_auf_origin() -> set[str]:
    rc, out = _git("ls-remote", "--heads", "origin")
    if rc != 0:
        return set()
    return {l.split("refs/heads/")[1] for l in out.splitlines() if "refs/heads/" in l}


# ``feature/fm14b-ring-bedienung-v3`` -> ``("feature/fm14b-ring-bedienung", 3)``
_VERSION = re.compile(r"^(?P<stamm>.+)-v(?P<nr>\d+)$")


def stamm_und_version(zweig: str) -> tuple[str, int]:
    """Zweigname ohne ``-vN`` plus die Nummer (ohne Suffix: Fassung 1)."""
    m = _VERSION.match(zweig)
    return (m.group("stamm"), int(m.group("nr"))) if m else (zweig, 1)


def neuere_fassungen(zweig: str, zweige) -> list[str]:
    """Zweige mit demselben Stamm und HOEHERER Nummer, aufsteigend.

    ★★ CDX-57, von Codex gefunden: die erste Fassung suchte
    ``x.startswith(b + "-v")`` — bei ``…-v3`` also nach ``…-v3-v…``. Genau die
    naechste Fassung (``…-v4``) fiel damit durch, und das ist der einzige Fall,
    der zaehlt: FM-14b zeigte am 25.08. auf ``-v1``, waehrend ``-v3`` die Arbeit
    trug. Verglichen wird deshalb der STAMM, und die Nummer NUMERISCH — sonst
    sortiert ``-v10`` vor ``-v9``.
    """
    stamm, nr = stamm_und_version(zweig)
    treffer = []
    for x in zweige:
        x_stamm, x_nr = stamm_und_version(x)
        if x_stamm == stamm and x_nr > nr:
            treffer.append((x_nr, x))
    return [x for _nr, x in sorted(treffer)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="Exit 1, wenn eine Drift gefunden wurde")
    ap.add_argument("--kein-fetch", action="store_true",
                    help="nicht vorher `git fetch` — dann gilt der zuletzt geholte Stand")
    ap.add_argument("--nur-implizit", action="store_true",
                    help="nur die ref-freie Pruefung der ID-Testdateien (ohne git)")
    args = ap.parse_args(argv)

    # ── 0) Implizite Spur (ref-frei; dieselbe Pruefung wie der CI-Test) ─────
    # Aus dem Ordner von BACKLOG (nicht fest REPO): so faehrt der Test von
    # main() auf seiner Wegwerf-Tabelle auch diese Pruefung im Wegwerf-Ordner.
    implizit = implizite_pruefung_im_repo(os.path.dirname(BACKLOG))
    if args.nur_implizit:
        for z in bericht_implizit(implizit):
            print(z)
        print()
        if implizit["beanstandet"]:
            print(f"⚠ {len(implizit['beanstandet'])} Drift(s):")
            for b in implizit["beanstandet"]:
                print(f"  - {b}")
        else:
            print("✓ kein todo-Item mit ID-Testdatei im Baum.")
        return 1 if (implizit["beanstandet"] and args.strict) else 0

    if not args.kein_fetch:
        rc, _ = _git("fetch", "--quiet", "--prune", "origin")
        if rc != 0:
            # ★ CDX-57: fail closed, gleiche Behandlung wie in
            # `tools/backlog_ids.py` (#670). Mit veralteten Refs meldet dieses
            # Werkzeug eine gerade GELANDETE Spur als „fehlt" — also einen
            # Fehlalarm genau gegen die Items, die eben durchgegangen sind. Ein
            # Waechter, der das still tut, wird abgeschaltet.
            print("FEHLER: `git fetch` fehlgeschlagen — mit veralteten Refs waere "
                  "jedes Urteil hier wertlos. Netz/Zugang pruefen, oder bewusst "
                  "mit --kein-fetch fahren.")
            return 2

    with open(BACKLOG, encoding="utf-8") as f:
        text = f.read()
    items = zeilen_mit_items(text)

    rc, _ = _git("rev-parse", "--verify", "-q", "origin/main")
    if rc != 0:
        print("FEHLER: kein origin/main — dieses Werkzeug braucht die Refs des "
              "echten Repos (siehe Docstring: deshalb ist es kein CI-Test).")
        return 2

    beanstandet = []

    # ── 1) Spur-Probe ────────────────────────────────────────────────────────
    mit_spur = 0
    geurteilt = 0
    for item, status, zeile in items:
        # SPUR ueberspringt `<!-- spur: keine -->` (Ausnahme der impliziten
        # Spur, keine Datei namens „keine") von selbst.
        m = SPUR.search(zeile)
        if not m:
            continue
        mit_spur += 1
        datei, kennzeichen = m.group(1), m.group(2)
        auf_main = spur_auf_main(datei, kennzeichen)
        klasse = status_klasse(status)
        # ★ Ueber welche Klassen ueberhaupt geurteilt wird, entscheidet
        # `spur_urteil`. Eine Spur an einem Item, dessen Klasse einen Freibrief
        # hat (`teils`, `blocked`, `decision`), wird gezaehlt, aber nie
        # beurteilt — das ist Absicht, muss aber im Bericht stehen.
        # `status_klasse` liefert Klassennamen, nicht Leitworte — die
        # Freibrief-Klasse heisst hier „unterwegs".
        if klasse != "unterwegs":
            geurteilt += 1
        urteil = spur_urteil(klasse, auf_main)
        if urteil:
            wo = f"{datei}" + (f" :: {kennzeichen}" if kennzeichen else "")
            beanstandet.append(f"{item}: {urteil}  ({wo})")

    # ★ Die Abdeckung MUSS mitgemeldet werden. Ohne sie sieht „0 Beanstandungen"
    # bei null hinterlegten Spuren aus wie ein sauberer Backlog.
    #
    # ★★ Und sie muss die GEURTEILTEN nennen, nicht nur die vorhandenen Spuren:
    # in der Gegenpruefung stand hier „19 von 478 Items haben eine Spur", waehrend
    # nur 15 davon ueberhaupt ein Urteil bekamen — die restlichen vier lagen an
    # Items der Freibrief-Klasse. In kleiner Form war der Fleck damit zurueck,
    # gegen den diese Zeile gebaut ist.
    ungeurteilt = mit_spur - geurteilt
    print(f"[spur]  {mit_spur} von {len(items)} Items haben eine Spur — "
          f"beurteilt: {geurteilt}"
          + (f", ohne Urteil (Freibrief-Klasse): {ungeurteilt}" if ungeurteilt else ""))
    if mit_spur == 0:
        print("        -> es wurde NICHTS geprueft. Spuren hinterlegen:"
              " <!-- spur: datei :: kennzeichen -->")
    for z in bericht_implizit(implizit):
        print(z)
    beanstandet.extend(implizit["beanstandet"])

    # ── 2) Zweig-Behauptung ──────────────────────────────────────────────────
    zweige = zweige_auf_origin()
    if not zweige:
        print("[zweig] origin nicht erreichbar — Zweig-Behauptungen ungeprueft")
    else:
        geprueft = 0
        for item, status, _zeile in items:
            m = ZWEIG.search(status)
            if not m:
                continue
            geprueft += 1
            b = m.group(1)
            if b not in zweige:
                beanstandet.append(f"{item}: nennt Zweig '{b}' — der existiert auf origin nicht")
                continue
            neuer = neuere_fassungen(b, zweige)
            if neuer:
                beanstandet.append(
                    f"{item}: nennt Zweig '{b}', aber es gibt eine neuere Fassung: {', '.join(neuer)}")
        print(f"[zweig] {geprueft} Items nennen einen Umsetzungszweig")

    print()
    if beanstandet:
        print(f"⚠ {len(beanstandet)} Drift(s):")
        for b in beanstandet:
            print(f"  - {b}")
    else:
        print("✓ keine Drift in dem, was geprueft werden konnte.")
    return 1 if (beanstandet and args.strict) else 0


if __name__ == "__main__":
    # XPLAT-20: Windows-Konsolen und -Pipes laufen ohne PYTHONUTF8 auf cp1252.
    # Die Statuszeichen dieses Werkzeugs (✓ ⚠ ★ ⏳) haben dort keine Abbildung,
    # der Bericht stirbt also mitten in der Ausgabe an einem UnicodeEncodeError.
    # Bewusst HIER und nicht auf Modulebene: beim Import (Tests laden die
    # Werkzeuge per exec_module) bleibt der Datenstrom des Aufrufers unberuehrt.
    for _strom in (sys.stdout, sys.stderr):
        if hasattr(_strom, "reconfigure"):
            _strom.reconfigure(encoding="utf-8")
    sys.exit(main())
