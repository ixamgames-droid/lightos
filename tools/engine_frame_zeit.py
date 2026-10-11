"""ENG-30 — Engine-Zeit je DMX-Frame an der Buehnen-Show messen (Verteilung je Funktionsart).

Baut ``tools/build_buehnen_show_2026.py`` in einer Sandbox (kein Byte im echten
Datenordner, kein Ausgabe-Thread, kein Fenster), laedt die Show und ruft
``OutputManager._send_all`` in einer Schleife — genau das, was der 44-Hz-Thread
je Frame tut (Funktionen rendern, Programmer, Master, Masken, Senden).

    ./venv/bin/python tools/engine_frame_zeit.py
    (Windows: venv/Scripts/python.exe)

Ausgabe: je Fall (nichts laeuft, jeder Look, alle Funktionen einer Art) die
Zeit je Frame, und fuer die Looks die Verteilung auf Szene, EFX, Matrix,
Chaser und den Rest. Budget bei 44 Hz: 22,7 ms.

Nuetzliche Schalter:

    --schlank 16,32      dieselbe Show auf 16 Moving Heads + 32 PAR gekuerzt
    --abdruck 300        Ausgabe von 300 Frames je Fall hashen — zwei Staende
                         mit gleichem Abdruck geben Byte fuer Byte dasselbe aus
    --profil "Look Drop" cProfile dieses Falls (die 40 teuersten Funktionen)
    --basis ORDNER       Sandbox/Show dort ablegen und wiederverwenden

Zeiten haengen vom Rechner und von dem ab, was nebenher laeuft. Gezeigt wird
deshalb der KLEINSTE Mittelwert aus mehreren Runden; zum Vergleichen zweier
Staende beide abwechselnd laufen lassen. Ergebnisse: docs/ENGINE_FRAME_ZEIT.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOKS = ("Look Intro", "Look Aufbau", "Look Drop", "Look Breakdown", "Look Finale")


def _argumente(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bilder", type=int, default=200, help="Frames je Runde (Standard 200)")
    ap.add_argument("--runden", type=int, default=3, help="Runden je Fall (Standard 3)")
    ap.add_argument("--nur", default="", help="nur Faelle, die so beginnen (Komma-Liste)")
    ap.add_argument("--schlank", default="", metavar="MH,PAR",
                    help="Rig kuerzen: so viele Moving Heads und PAR behalten")
    ap.add_argument("--abdruck", type=int, default=0, metavar="N",
                    help="statt zu messen: N Frames je Fall hashen")
    ap.add_argument("--profil", default="", metavar="FALL", help="cProfile dieses Falls")
    ap.add_argument("--basis", default="", help="Ordner fuer Sandbox und Show (Standard: temporaer)")
    return ap.parse_args(argv)


def _show_laden(basis: str):
    """Sandbox einrichten, Show bauen (einmal je ``basis``) und laden."""
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tools"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from anleitungsbilder import sandbox

    sandbox.einrichten(basis)
    show = os.path.join(basis, "buehnen_show.lshow")
    if not os.path.exists(show):
        bau = subprocess.run(
            [sys.executable, os.path.join(REPO, "tools", "build_buehnen_show_2026.py"),
             "--out", show],
            env=dict(os.environ), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900)
        if bau.returncode != 0:
            raise SystemExit("Show liess sich nicht bauen:\n" + (bau.stdout + bau.stderr)[-2000:])

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.core.app_state import get_state
    from src.core.engine.function_manager import get_function_manager
    from src.core.paths import app_data_dir
    from src.core.show.show_file import load_show

    if not os.path.realpath(app_data_dir()).startswith(os.path.realpath(basis)):
        raise SystemExit(f"Datenordner liegt ausserhalb der Sandbox: {app_data_dir()}")
    ok, meldung = load_show(show)
    if not ok:
        raise SystemExit(f"Show liess sich nicht laden: {meldung}")
    return app, get_state(), get_function_manager()


def _rig_kuerzen(st, schlank: str):
    """Nur N Moving Heads und M PAR behalten; alles andere aus dem Patch."""
    n_mh, n_par = (int(x) for x in schlank.split(","))
    behalten = {"moving_head": n_mh, "par": n_par}
    for f in sorted(st.get_patched_fixtures(), key=lambda f: f.fid):
        art = (getattr(f, "fixture_type", "") or "").lower()
        if behalten.get(art, 0) > 0:
            behalten[art] -= 1
            continue
        st.remove_fixture(f.fid, undoable=False)


class Messung:
    def __init__(self, st, fm, bilder: int, runden: int):
        self.st, self.fm, self.om = st, fm, st.output_manager
        self.bilder, self.runden = bilder, runden
        funktionen = list(fm._functions.values())
        self.nach_name = {f.name: f for f in funktionen}
        nach_art: dict[str, list] = {}
        for f in funktionen:
            nach_art.setdefault(type(f).__name__, []).append(f)
        self.faelle: dict[str, list] = {"nichts laeuft": []}
        for name in LOOKS:
            if name in self.nach_name:
                self.faelle[name] = [self.nach_name[name].id]
        for art, liste in sorted(nach_art.items()):
            self.faelle[f"alle {art} ({len(liste)})"] = [f.id for f in liste]
        self.klassen = sorted({type(f) for f in funktionen}, key=lambda k: k.__name__)

    def ticks(self, n: int):
        for _ in range(n):
            self.om._send_all()

    def neu(self, ids):
        self.fm.stop_all()
        self.om.set_grand_master(1.0)
        self.ticks(3)
        for i in ids:
            self.fm.start(i)
        self.ticks(20)                      # einschwingen (Fades, erste Schritte)

    def zeit(self, ids) -> dict:
        """ms je Frame: kleinster Mittelwert der Runden, Median und p95 aller Frames."""
        self.neu(ids)
        mittel, alle = [], []
        for _ in range(self.runden):
            zeiten = []
            for _ in range(self.bilder):
                t = time.perf_counter()
                self.om._send_all()
                zeiten.append((time.perf_counter() - t) * 1000.0)
            mittel.append(sum(zeiten) / len(zeiten))
            alle.extend(zeiten)
        alle.sort()
        return {"mittel": min(mittel), "median": alle[len(alle) // 2],
                "p95": alle[int(len(alle) * 0.95)]}

    def verteilung(self, ids) -> dict:
        """Zeit je Funktionsart, EXKLUSIV (ohne die Zeit aufgerufener Kinder).

        ``write`` jeder Klasse wird umhuellt; ein Stapel zieht die Kinderzeit ab
        (eine Collection ruft Szenen, ein Chaser seine Schritte). Was uebrig
        bleibt, ist der Frame ohne Funktionen: Programmer, Master, Masken,
        Senden. Die Huellen kosten selbst etwas — die Summe liegt deshalb
        leicht ueber der ungestoerten Messung."""
        pc = time.perf_counter
        exkl: dict[str, float] = {}
        rufe: dict[str, int] = {}
        stapel: list[list] = []
        echte = {}

        def huelle(klasse):
            echt = klasse.write
            echte[klasse] = echt
            name = klasse.__name__

            def ersatz(selbst, *a, **k):
                eintrag = [0.0]
                stapel.append(eintrag)
                t0 = pc()
                try:
                    return echt(selbst, *a, **k)
                finally:
                    dauer = pc() - t0
                    stapel.pop()
                    exkl[name] = exkl.get(name, 0.0) + dauer - eintrag[0]
                    rufe[name] = rufe.get(name, 0) + 1
                    if stapel:
                        stapel[-1][0] += dauer
            klasse.write = ersatz

        for klasse in self.klassen:
            if "write" in vars(klasse):
                huelle(klasse)
        try:
            beste = None
            for _ in range(self.runden):
                self.neu(ids)
                exkl.clear()
                rufe.clear()
                t0 = pc()
                self.ticks(self.bilder)
                gesamt = (pc() - t0) * 1000.0 / self.bilder
                zeile = {"gesamt": gesamt, "arten": {
                    k: (exkl[k] * 1000.0 / self.bilder, rufe[k] / self.bilder) for k in exkl}}
                if beste is None or gesamt < beste["gesamt"]:
                    beste = zeile
        finally:
            for klasse, echt in echte.items():
                klasse.write = echt
        beste["rest"] = beste["gesamt"] - sum(v[0] for v in beste["arten"].values())
        return beste

    def abdruck(self, ids, frames: int) -> tuple[str, int]:
        import hashlib
        import random
        random.seed(20261011)
        self.neu(ids)
        h = hashlib.sha256()
        belegt = 0
        for _ in range(frames):
            self.om._send_all()
            for u in sorted(self.om.universes):
                daten = bytes(self.om.get_display_frame(u))
                h.update(daten)
                belegt += sum(1 for b in daten if b)
        return h.hexdigest()[:16], belegt


def main(argv=None) -> int:
    arg = _argumente(argv)
    basis = os.path.abspath(arg.basis) if arg.basis else tempfile.mkdtemp(prefix="lightos_eng30_")
    os.makedirs(basis, exist_ok=True)
    _app, st, fm = _show_laden(basis)
    if arg.schlank:
        _rig_kuerzen(st, arg.schlank)
    m = Messung(st, fm, arg.bilder, arg.runden)
    nur = [n.strip() for n in arg.nur.split(",") if n.strip()]
    faelle = {n: ids for n, ids in m.faelle.items()
              if not nur or any(n.startswith(x) for x in nur)}
    arten: dict[str, int] = {}
    for f in st.get_patched_fixtures():
        art = (getattr(f, "fixture_type", "") or "?").lower()
        arten[art] = arten.get(art, 0) + 1
    print(f"Rig: {sum(arten.values())} Geraete ("
          + ", ".join(f"{v} {k}" for k, v in sorted(arten.items(), key=lambda kv: -kv[1]))
          + f"), {len(m.om.universes)} Universen")

    if arg.abdruck:
        print(f"\nAbdruck der Ausgabe ueber {arg.abdruck} Frames je Fall:")
        for name, ids in faelle.items():
            kennung, belegt = m.abdruck(ids, arg.abdruck)
            print(f"  {name:30s} {kennung}   Werte ungleich 0: {belegt}")
        fm.stop_all()
        return 0

    print(f"\nZeit je Frame in ms (kleinster Mittelwert aus {arg.runden} x {arg.bilder} Frames)\n")
    print("| Fall | Mittel | Median | p95 |")
    print("|---|---|---|---|")
    for name, ids in faelle.items():
        z = m.zeit(ids)
        print(f"| {name} | {z['mittel']:.2f} | {z['median']:.2f} | {z['p95']:.2f} |", flush=True)

    looks = [n for n in faelle if n in LOOKS]
    if looks:
        spalten = [k.__name__ for k in m.klassen]
        print("\nVerteilung je Funktionsart (ms je Frame, ohne Kinder; in Klammern Aufrufe je Frame)\n")
        print("| Fall | gesamt | " + " | ".join(spalten) + " | Rest (Programmer, Master, Senden) |")
        print("|---|---|" + "---|" * (len(spalten) + 1))
        for name in looks:
            v = m.verteilung(faelle[name])
            zellen = []
            for s in spalten:
                if s in v["arten"]:
                    zellen.append(f"{v['arten'][s][0]:.2f} ({v['arten'][s][1]:.0f})")
                else:
                    zellen.append("–")
            print(f"| {name} | {v['gesamt']:.2f} | " + " | ".join(zellen)
                  + f" | {v['rest']:.2f} |", flush=True)

    if arg.profil:
        import cProfile
        import io
        import pstats
        if arg.profil not in m.faelle:
            raise SystemExit(f"Fall '{arg.profil}' gibt es nicht. Bekannt: {', '.join(m.faelle)}")
        m.neu(m.faelle[arg.profil])
        pr = cProfile.Profile()
        pr.enable()
        m.ticks(arg.bilder)
        pr.disable()
        s = io.StringIO()
        pstats.Stats(pr, stream=s).strip_dirs().sort_stats("tottime").print_stats(40)
        print(f"\ncProfile '{arg.profil}', {arg.bilder} Frames, nach eigener Zeit:\n")
        print(s.getvalue())

    fm.stop_all()
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    # os._exit: die geladene Show haelt Hintergrund-Threads (MIDI-Rueckmeldung,
    # Tempo), die ein gewoehnliches Ende aufhalten wuerden.
    code = main()
    sys.stdout.flush()
    os._exit(code)
