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
SPUR = re.compile(r"<!--\s*spur:\s*([^:>]+?)\s*(?:::\s*(.+?)\s*)?-->")
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


# ── Der Griff nach dem echten Repo (in der CI nicht verfuegbar) ──────────────

def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(("git",) + args, cwd=REPO, capture_output=True, text=True, encoding="utf-8")
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
    args = ap.parse_args(argv)

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
