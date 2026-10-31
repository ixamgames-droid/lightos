# Lizenz und Testzugang

LightOS ist in der **Testphase**. Urheber ist
[ixamgames-droid](https://github.com/ixamgames-droid/lightos) — alle Rechte vorbehalten.
Der verbindliche Text steht in der Datei [`LICENSE`](../LICENSE); diese Seite erklärt, was
das im Alltag heißt.

## Was erlaubt ist

| | ohne Erlaubnis | mit Testlizenz |
|---|---|---|
| Quelltext auf GitHub ansehen | ja | ja |
| Programm starten und benutzen | nein | ja, im vereinbarten Rahmen |
| Verändern, weitergeben, verkaufen | nein | nein (nur mit eigener schriftlicher Erlaubnis) |

Mitgelieferte Bestandteile anderer Urheber (three.js, Socket.IO, Geräteprofile auf
QLC+-Basis) stehen unter ihren eigenen Lizenzen — siehe
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Daran ändert die LightOS-Lizenz nichts.

## Testzugang bekommen

Einen Testzugang gibt es **auf Anfrage über GitHub**
(<https://github.com/ixamgames-droid/lightos>). Du bekommst eine kleine Datei, die
**Lizenzdatei**. Sie ist

- **persönlich** — sie nennt dich bzw. deinen Testplatz,
- **in der Regel befristet** — sie nennt meist ein Ablaufdatum,
- **nicht übertragbar** — bitte nicht weitergeben.

Die Datei ist signiert. Wer Name oder Datum darin ändert, macht sie ungültig.

## Wohin die Datei gehört

Am einfachsten: LightOS starten. Ohne gültige Lizenz erscheint das Fenster
**„LightOS — Testlizenz erforderlich“**. Dort auf **„Lizenzdatei auswählen…“** klicken und
die erhaltene Datei auswählen — LightOS prüft sie und legt sie selbst an den richtigen Ort.

Von Hand geht es auch. Die Datei muss `lightos-lizenz.lic` heißen und im
LightOS-Datenordner liegen:

| System | Ort |
|---|---|
| Windows | `%APPDATA%\LightOS\lightos-lizenz.lic` |
| Linux | `~/.local/share/LightOS/lightos-lizenz.lic` |
| macOS | `~/Library/Application Support/LightOS/lightos-lizenz.lic` |

Wer die Datei woanders liegen lassen will, setzt die Umgebungsvariable `LIGHTOS_LIZENZ` auf
ihren Pfad.

Den Stand zeigt **Hilfe → Über LightOS** in der Zeile „Lizenz“ (für wen, gültig bis wann).
Außerdem nennt dasselbe Fenster die Bestandteile anderer Urheber, die unter der LGPL stehen,
und verweist auf die Aufstellung `THIRD_PARTY_NOTICES.md` und den **Ordner „licenses“** im
Programmordner (als Link, wenn der Ordner vorhanden ist) — dort liegen die vollständigen
Lizenztexte.

## Was beim Ablauf passiert

- **Geprüft wird nur beim Programmstart.** Läuft LightOS, passiert beim Ablauf **nichts**:
  eine laufende Show wird nie unterbrochen, nichts wird gesperrt, kein Fenster geht auf.
- Ab **14 Tagen vor dem Ablauf** steht beim Start ein kurzer Hinweis in der Statuszeile
  („Testlizenz läuft am … ab“). Er hält den Start nicht auf.
- **Nach dem Ablauf** fragt der *nächste* Start wieder nach einer Lizenzdatei. Deine Shows
  und Einstellungen bleiben unberührt; mit einer neuen Lizenzdatei geht es weiter wie vorher.

Wer vor einer Veranstaltung sichergehen will: in **Über LightOS** das Datum ansehen.

## Kein Internet, keine Datensammlung

LightOS geht für die Lizenz **nie ins Internet**. Die Prüfung liest die Datei und rechnet —
es gibt keine Aktivierung bei einem Server, kein „Nachhause-Telefonieren“, keine Übertragung
von Daten. Das Programm läuft vollständig ohne Netzverbindung.

Im Programm-Log und im Diagnosepaket steht der Lizenzstatus nur mit einer **gekürzten
Kennung** der Lizenz, nicht mit dem Namen des Lizenznehmers.

## Urheberangabe in Dateien

Gespeicherte Shows und Diagnosepakete tragen einen Vermerk „erstellt mit LightOS von
ixamgames-droid“ samt Programmversion. Alte Shows ohne den Vermerk laden unverändert.

## Für Entwicklung und Tests

`--selbsttest`, `--diagnose`, die Testsuite und die Werkzeuge unter `tools/` fragen nicht
nach einer Lizenz — die Abfrage hängt nur am echten Start des Programmfensters.
