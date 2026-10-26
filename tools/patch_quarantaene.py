"""STAB-DEDUP-OPT: verwaiste Patch-Zeilen anzeigen und (nur auf Ansage) in
Quarantäne verschieben.

    venv/bin/python tools/patch_quarantaene.py --echte-daten                 # nur anzeigen
    venv/bin/python tools/patch_quarantaene.py --echte-daten --anwenden      # verschieben
    venv/bin/python tools/patch_quarantaene.py --echte-daten --liste         # Quarantäne zeigen
    venv/bin/python tools/patch_quarantaene.py --echte-daten --zurueck 42    # zurückholen
    venv/bin/python tools/patch_quarantaene.py --show datei.lshow            # Probe in der Sandbox
    (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

**``--echte-daten`` (TOOL-27):** Wie jedes Werkzeug läuft auch dieses zunächst in
einer eigenen Sandbox und sieht die Show-Datenbank des Rechners gar nicht. Erst
mit ``--echte-daten`` arbeitet es an der echten Show (App vorher schließen) —
mit Warnzeile, und auch dann ohne einen Ausgang zu öffnen. Ohne den Schalter
lässt sich mit ``--show`` eine Show-Datei gefahrlos durchsehen.

**Ohne ``--anwenden`` wird nichts verändert.** Das ist keine Höflichkeit,
sondern die Absicherung: der Befund hängt an einem Scan über ein Dutzend
Referenz-Orte, und der Nutzer soll sehen, *warum* ein Gerät als Waise gilt,
bevor es sich bewegt.

Adress-Überlappungen werden mit ausgewiesen, sind aber **nie** ein Grund zur
Quarantäne — zwei Geräte auf derselben Adresse können beide gewollt sein.
"""
import _werkzeug_sandbox  # noqa: F401  (TOOL-27: eigene Sandbox, vor jedem src-Import)
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# TOOL-19: dieses Werkzeug arbeitet bewusst auf der ECHTEN Show-DB — aber es
# gibt kein Licht aus. Ohne die beiden Schalter richtete get_state() die echte
# Ausgabe-Konfiguration ein (Enttec-Port offen) und startete den Sende-Thread:
# ein Wartungslauf haette am Rig DMX gesendet. Die Wegwerfdatei wird nie angelegt.
import tempfile                                                      # noqa: E402
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
os.environ.setdefault(
    "LIGHTOS_UNIVERSES_JSON",
    os.path.join(tempfile.gettempdir(),
                 f"lightos_quarantaene_{os.getpid()}_universes.json"),
)

from src.core.show import patch_dedup                                # noqa: E402


def _zeile(b) -> str:
    ort = f"U{b.universe}:{b.address}"
    ueber = (f"  überlappt mit {b.ueberlappt_mit}" if b.ueberlappt_mit else "")
    if b.ist_kandidat:
        return f"  WAISE   #{b.fid:<4} {ort:<10} {b.label[:28]:<28}{ueber}"
    return (f"  benutzt #{b.fid:<4} {ort:<10} {b.label[:28]:<28}"
            f"  → {', '.join(b.fundstellen)}{ueber}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anwenden", action="store_true",
                    help="Kandidaten wirklich in die Quarantäne verschieben")
    ap.add_argument("--liste", action="store_true",
                    help="Inhalt der Quarantäne zeigen")
    ap.add_argument("--zurueck", type=int, metavar="FID",
                    help="ein Gerät aus der Quarantäne zurückholen")
    ap.add_argument("--alle", action="store_true",
                    help="auch die benutzten Geräte auflisten")
    ap.add_argument("--show", metavar="DATEI",
                    help="Show-Datei vorher laden (dort stehen Funktionen, "
                         "Cuelisten, VC-Layout und Snaps — NICHT in der DB)")
    ap.add_argument("--auch-ohne-show", action="store_true",
                    help="den Unbeladen-Riegel bewusst übergehen (nur, wenn die "
                         "Show wirklich keine Funktionen/Cues/VC/Snaps hat)")
    ap.add_argument(_werkzeug_sandbox.SCHALTER_ECHTE_DATEN, dest="echte_daten",
                    action="store_true",
                    help="an der ECHTEN Show-Datenbank dieses Rechners arbeiten "
                         "(App vorher schließen); ohne den Schalter läuft das "
                         "Werkzeug in einer Sandbox")
    args = ap.parse_args()

    if not args.echte_daten:
        if args.anwenden or args.liste or args.zurueck is not None or not args.show:
            print("ABBRUCH: Dieses Werkzeug läuft ohne --echte-daten in einer Sandbox")
            print("und sieht die Show-Datenbank dieses Rechners nicht.")
            print()
            print("  an der echten Show arbeiten:      --echte-daten  (App vorher schließen)")
            print("  eine Show-Datei nur durchsehen:   --show <datei.lshow>")
            return 2
        print("Sandbox: Die Show wird in eine Wegwerf-Datenbank geladen, an der "
              "echten Show ändert sich nichts.")

    from src.core.app_state import get_state
    state = get_state()

    if args.show:
        from src.core.show.show_file import load_show
        load_show(state, args.show)
        print(f"Show geladen: {args.show}")

    if args.liste:
        eintraege = patch_dedup.liste_quarantaene(state)
        if not eintraege:
            print("Quarantäne ist leer.")
            return 0
        print(f"{len(eintraege)} Gerät(e) in Quarantäne:")
        for e in eintraege:
            print(f"  #{e['fid']:<4} U{e['universe']}:{e['address']:<4} "
                  f"{e['label'][:28]:<28} {e['verschoben_am']}  ({e['grund']})")
        return 0

    if args.zurueck is not None:
        ok = patch_dedup.zurueckholen(state, args.zurueck)
        print(f"#{args.zurueck} " + ("zurückgeholt." if ok else "nicht in Quarantäne."))
        return 0 if ok else 1

    if patch_dedup.wirkt_unbeladen(state) and not args.auch_ohne_show:
        print("ABBRUCH: der Patch ist gefüllt, aber es gibt weder Funktionen noch")
        print("Cuelisten, VC-Widgets oder Snaps. Das sieht nach einer NICHT")
        print("geladenen Show aus — dann läge jede Referenz außerhalb des Scans")
        print("und JEDES Gerät gälte als Waise.")
        print()
        print("  Show laden:            --show <datei.lshow>")
        print("  wirklich so gewollt:   --auch-ohne-show")
        return 2

    try:
        befunde = patch_dedup.analysiere(state)
    except patch_dedup.ScanUnvollstaendig as e:
        print(f"ABBRUCH: {e}")
        print("Es wird nichts verschoben — ein unvollständiger Scan könnte ein "
              "benutztes Gerät als Waise ausweisen.")
        return 2

    kandidaten = [b for b in befunde if b.ist_kandidat]
    print(f"{len(befunde)} gepatchte Geräte, {len(kandidaten)} ohne jede Referenz.")
    print(f"Geprüfte Referenz-Orte: {', '.join(patch_dedup.SCAN_ORTE)}")
    print()
    for b in befunde:
        if b.ist_kandidat or args.alle:
            print(_zeile(b))

    if not kandidaten:
        print("\nNichts zu tun.")
        return 0
    if not args.anwenden:
        print(f"\nNichts verändert. Zum Verschieben: --anwenden")
        return 0

    verschoben = patch_dedup.in_quarantaene(
        state, [b.fid for b in kandidaten], grund="tools/patch_quarantaene.py")
    print(f"\n{len(verschoben)} Gerät(e) verschoben: {verschoben}")
    if len(verschoben) < len(kandidaten):
        print("Einige Kandidaten wurden beim zweiten Scan doch noch referenziert "
              "und blieben stehen.")
    print("Zurückholen: --zurueck <fid>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
