"""DOC-16: Anleitungsbilder reproduzierbar aus dem Code erzeugen.

Baut die LightOS-Oberflaeche offscreen (1600 x 900) in einer Sandbox auf, laedt
eine Doku-Demo-Show aus eingebauten Generic-Profilen und nimmt je Anleitung die
Szenen aus ``tools/anleitungsbilder/szenen_<anleitung>.py`` auf.

Aufruf (aus dem Repo-Root)::

    venv/bin/python tools/anleitungsbilder.py projektseite     # eine Anleitung
    venv/bin/python tools/anleitungsbilder.py --alle           # alle
    venv/bin/python tools/anleitungsbilder.py projektseite --nur 02_patch
    venv/bin/python tools/anleitungsbilder.py --alle --pruefen # nur baubar?
    venv/bin/python tools/anleitungsbilder.py --liste          # Szenen zeigen
    venv/bin/python tools/anleitungsbilder.py vc_widgets --bildschirm  # 3D-Szenen

Windows (PowerShell/cmd) entsprechend::

    venv/Scripts/python tools/anleitungsbilder.py projektseite

Ausgabe: ``docs/<anleitung>/img/NN_name.png`` (bzw. ``.gif`` fuer Szenen mit
``frames``, DOC-20) + ``bilder.json`` (Manifest ohne
absolute Pfade). ``--pruefen`` schreibt nichts nach ``docs/`` — es rendert in
die Sandbox und meldet, ob jede Szene noch baubar ist (Pixelgleichheit wird
nicht verlangt: die Schrift ist rechnerabhaengig).

Datenschutz: Die Sandbox (``tools/anleitungsbilder/sandbox.py``) lenkt ALLE
Datenpfade und das Arbeitsverzeichnis in einen Wegwerf-Ordner um, bevor ein
``src``-Modul geladen wird, prueft das vor dem ersten Bild und vergleicht nach
dem Lauf die echten Datenorte mit dem Stand davor. Der echte Datenordner wird
weder gelesen noch geschrieben. Doku: ``docs/ANLEITUNGSBILDER.md``.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from anleitungsbilder import sandbox  # noqa: E402  (importiert kein src)


def _argumente(argv):
    ap = argparse.ArgumentParser(
        prog="tools/anleitungsbilder.py",
        description="Anleitungsbilder offscreen in einer Sandbox erzeugen.")
    ap.add_argument("anleitung", nargs="*", help="Name(n) der Anleitung(en), "
                    "z. B. 'projektseite' (= szenen_projektseite.py)")
    ap.add_argument("--alle", action="store_true", help="alle Anleitungen")
    ap.add_argument("--pruefen", action="store_true",
                    help="nur pruefen, ob jede Szene baubar ist (schreibt nichts nach docs/)")
    ap.add_argument("--liste", action="store_true", help="Szenen auflisten, nichts rendern")
    ap.add_argument("--nur", action="append", default=[], metavar="SZENE",
                    help="nur diese Szene(n) (mehrfach oder kommagetrennt)")
    ap.add_argument("--ausgabe", metavar="ORDNER",
                    help="statt docs/<anleitung>/img nach ORDNER/<anleitung> schreiben")
    ap.add_argument("--behalten", action="store_true",
                    help="Sandbox-Ordner nach dem Lauf nicht loeschen (Fehlersuche)")
    ap.add_argument("--bildschirm", action="store_true",
                    help="auf dem echten X11-Bildschirm statt offscreen zeichnen; baut "
                         "NUR Szenen mit braucht_gpu (3D), alle anderen bleiben offscreen")
    return ap.parse_args(argv)


def _je_anleitung_ein_prozess(args, auftraege, nur) -> int:
    """TOOL-8: jede Anleitung in einem eigenen Unterprozess dieses Werkzeugs.

    Der Unterprozess bekommt genau EINE Anleitung und laeuft damit den
    gewohnten Einzelweg (eigene Sandbox, Selbstpruefung, Abgleich der echten
    Datenorte). Anleitungen ohne eine der ``--nur``-Szenen werden ausgelassen.
    Rueckgabe: der schlechteste Exit-Code (0 < 1 Szene nicht baubar < 2 Fehler
    < 3 echte Datenorte veraendert).
    """
    import subprocess
    import time
    skript = os.path.abspath(__file__)
    ausgabe = args.ausgabe
    if ausgabe and not os.path.isabs(ausgabe):
        ausgabe = os.path.abspath(os.path.join(sandbox.REPO, ausgabe))
    code = 0
    t0 = time.time()
    for name, szenen, _ziel in auftraege:
        eigene = sorted(s.name for s in szenen if s.name in nur) if nur else []
        if nur and not eigene:
            continue
        befehl = [sys.executable, skript, name]
        if args.pruefen:
            befehl.append("--pruefen")
        if ausgabe:
            befehl += ["--ausgabe", ausgabe]
        if args.behalten:
            befehl.append("--behalten")
        if eigene:
            befehl += ["--nur", ",".join(eigene)]
        print(f"[anleitungsbilder] == {name} (eigener Prozess) ==", flush=True)
        t = time.time()
        rc = subprocess.run(befehl, cwd=sandbox.REPO).returncode
        print(f"[anleitungsbilder] {name}: Exit {rc} nach {time.time() - t:.1f} s",
              flush=True)
        code = max(code, rc if rc in (0, 1, 2, 3) else 2)
    print(f"[anleitungsbilder] {len(auftraege)} Anleitung(en) in "
          f"{time.time() - t0:.1f} s", flush=True)
    if args.pruefen:
        print("[anleitungsbilder] Pruefung gesamt: " + (
            "alle Szenen baubar." if code == 0 else "NICHT alles baubar, s. o."),
            flush=True)
    return code


def main(argv=None) -> int:
    args = _argumente(sys.argv[1:] if argv is None else argv)
    from anleitungsbilder import runner
    namen = runner.anleitungen() if (args.alle or (args.liste and not args.anleitung)) \
        else args.anleitung
    if not namen:
        print("Keine Anleitung angegeben (oder --alle). Vorhanden: "
              + ", ".join(runner.anleitungen()))
        return 2
    auftraege = []
    for n in namen:
        szenen, ziel = runner.lade_szenen(n)
        auftraege.append((n, szenen, ziel))
    nur = {x.strip() for eintrag in args.nur for x in eintrag.split(",") if x.strip()}
    if nur:
        bekannt = {s.name for _n, sz, _z in auftraege for s in sz}
        fremd = sorted(nur - bekannt)
        if fremd:
            print(f"[anleitungsbilder] Unbekannte Szene(n): {fremd}")
            return 2

    if args.liste:
        for n, szenen, ziel in auftraege:
            print(f"{n}  ->  {ziel}/")
            for s in szenen:
                extra = " [braucht GPU]" if s.braucht_gpu else ""
                if s.frames:
                    extra += f" [GIF, {len(s.frames)} Frames]"
                print(f"  {s.name:<22} {s.titel}{extra}")
        return 0

    # TOOL-8: mehrere Anleitungen -> je Anleitung ein eigener Prozess (frische
    # Sandbox, frisches Hauptfenster, frische Demo-Show). Im selben Fenster
    # nacheinander trug jede Anleitung den Zustand der vorigen weiter
    # (Programmer-Auswahl, BPM 128, „Wiederholen" aktiv, Combo-Inhalte): die
    # Bilder zeigten fremden Zustand, ``--pruefen`` meldete falsche
    # Abweichungen. Ein Zuruecksetzen von Hand haette jeden neuen Zustand
    # einzeln kennen muessen; der eigene Prozess vergisst nichts.
    if len(auftraege) > 1:
        return _je_anleitung_ein_prozess(args, auftraege, nur)

    # Echte Datenorte VOR der Umlenkung erfassen, danach nie wieder anfassen.
    orte = sandbox.echte_datenorte()
    vorher = sandbox.schnappschuss(orte)
    sb = sandbox.einrichten(bildschirm=args.bildschirm)
    code = 2
    try:
        # Lint tests/test_tools_db_isolation.py: der bestehende Bootstrap der
        # Generatoren. Die Sandbox hat LIGHTOS_SHOW_DB schon gesetzt,
        # _gen_env respektiert das (setdefault).
        import _gen_env  # noqa: F401,E402
        ausgabe = args.ausgabe
        if args.pruefen and not ausgabe:
            ausgabe = os.path.join(sb.basis, "pruefen")
        if ausgabe:
            ausgabe = os.path.abspath(os.path.join(sandbox.REPO, ausgabe)) \
                if not os.path.isabs(ausgabe) else ausgabe
        code = runner.lauf(auftraege, sb=sb, pruefen=args.pruefen, ausgabe=ausgabe,
                           nur=nur or None, bildschirm=args.bildschirm)
        if args.pruefen:
            print("[anleitungsbilder] Pruefung: " + ("alle Szenen baubar." if code == 0
                                                     else "Szenen NICHT baubar, s. o."))
    except SystemExit as e:
        if not isinstance(e.code, int):
            print(e.code, flush=True)
        code = e.code if isinstance(e.code, int) else 2
    finally:
        os.chdir(sandbox.REPO)
        app_laeuft = sandbox.laufende_instanz()
        diff = sandbox.vergleiche(vorher, sandbox.schnappschuss(orte),
                                  app_laeuft=app_laeuft)
        if app_laeuft:
            print("[anleitungsbilder] Hinweis: eine LightOS-App laeuft parallel — "
                  "ihre Lebenszeichen-Dateien bleiben beim Abgleich aussen vor.",
                  flush=True)
        if diff:
            print("[anleitungsbilder] FEHLER: echte Datenorte haben sich waehrend des "
                  "Laufs veraendert:", flush=True)
            for z in diff[:20]:
                print("   " + z, flush=True)
            code = 3
        if args.behalten:
            print(f"[anleitungsbilder] Sandbox bleibt liegen: {sb.basis}", flush=True)
        else:
            shutil.rmtree(sb.basis, ignore_errors=True)
    return code


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Harter Ausstieg: der Qt-Abbau eines vollen MainWindow ist fuer ein
    # Werkzeug ohne Nutzen und offscreen gelegentlich instabil.
    os._exit(rc)
