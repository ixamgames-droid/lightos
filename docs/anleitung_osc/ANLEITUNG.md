# OSC: freie Adressen, Lernen und Rückmeldung

LightOS versteht über OSC nicht nur seine festen `/lightos/…`-Adressen
(siehe [Externe Pulte](../anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md#nebenweg-osc)),
sondern auch **beliebige Adressen**, die du selbst zuordnest — so passt LightOS zu dem,
was ein Pult, TouchOSC oder ein anderes Programm ohnehin sendet. Umgekehrt meldet
LightOS auf Wunsch Fader, Cue-Stand, Grand Master und Blackout an ein OSC-Ziel zurück.

Ort: Menü **Ausgabe** → **OSC-Zuordnungen & Rückmeldung…**. Der OSC-Eingang selbst
bleibt wie bisher ein eigener Schalter: Menü **Ausgabe** → **OSC-Server (Port 7770)**.

## 1. Eine Adresse zuordnen

Reiter **Eingang**, **+ Zuordnung**, dann je Zeile:

| Spalte | Bedeutung |
|---|---|
| Adresse | Die OSC-Adresse oder ein Muster, siehe unten. |
| Ziel | Executor-Fader · GO / Zurück / Stop Executor · Grand Master · Blackout · Funktion starten / stoppen / umschalten · Tap-Tempo. |
| Nummer | Feste Executor- oder Funktionsnummer, wenn die Adresse keine liefert. |
| Versatz | Wird zur Nummer aus `{n}` bzw. aus dem Argument addiert. |
| Nr. aus Arg. | Das **erste** Argument ist die Zielnummer, das zweite der Wert. |
| Funktion | Name oder Id der Funktion (nur bei Funktions-Zielen; hat Vorrang vor der Nummer). |
| Bereich | Was „voll“ ist: `0–1`, `0–100` oder `0–255`. |

Mit **Übernehmen** wirkt die Tabelle sofort und wird gespeichert. Zeilen mit ungültiger
Adresse bleiben im Dialog stehen, werden aber nicht übernommen — die Statuszeile nennt
ihre Zahl. Der Haken **Zuordnungen aktiv** schaltet alle freien Zuordnungen auf einmal ab.

### Muster

| Muster | passt auf |
|---|---|
| `*` | beliebig viele Zeichen außer `/` |
| `?` | genau ein Zeichen außer `/` |
| `[abc]`, `[a-z]`, `[!0-9]` | ein Zeichen aus der Menge bzw. nicht aus der Menge |
| `{go,start}` | eine der Alternativen |
| `{n}` | eine Zahl mit 1–6 Ziffern — sie ist die **Zielnummer** (höchstens einmal je Adresse) |

Grenzen: höchstens **zwei `*` je Adressteil** (zwischen zwei `/`; `**` zählt als einer),
kein `/` in `[..]` oder `{..}`. Adressen über 256 Zeichen werden nicht verglichen. So
kann keine lange oder seltsame Adresse aus dem Netz LightOS ausbremsen.

Zielnummer = `n` + Versatz. Beispiel: `/Page1/Fader{n}` mit Versatz `-200` macht aus
`/Page1/Fader201` den Executor 1.

### Werte

- Fader und Grand Master lesen int, float, wahr/falsch und Zahlen als Text, dazu
  `on`/`off`. Der Bereich legt fest, welcher Wert 100 % ist; darüber wird begrenzt.
- **Fehlt das Argument oder ist es unbrauchbar** (Text ohne Zahl, NaN, Blob), ändert
  sich nichts. Auch Blackout braucht einen Wert (1 = an, 0 = aus).
- Tasten (GO, Zurück, Stop, Funktionen, Tap) lösen **nur beim Drücken** aus: ab der halben
  Skala des Bereichs. Ohne Argument lösen sie immer aus, wie die festen Adressen.
- Executor-Nummern außerhalb 1–20 werden verworfen.

Eine Nachricht, die eine feste `/lightos/…`-Adresse **und** eine freie Zuordnung trifft,
wirkt auf beiden Wegen. Deshalb feste Adressen nicht zusätzlich frei zuordnen.

## 2. Lernen statt Tippen

1. Den OSC-Server einschalten (Menü **Ausgabe** → **OSC-Server (Port 7770)**).
2. Im Dialog eine Zeile wählen (ohne Auswahl entsteht eine neue) und **Lernen** drücken.
3. Am Pult bzw. in TouchOSC das Bedienelement einmal bewegen oder drücken.

LightOS trägt die Adresse ein und macht aus der **letzten Zahl** `{n}`, schlägt ein Ziel
vor (Fader, GO, Zurück …) und bei Nummern wie 201 den Versatz `-200`; der Bereich wird
aus dem Wert geraten. Die Statuszeile zeigt Adresse, `n` und den Absender. Vorschläge
prüfen, dann **Übernehmen**. Die gelernte Nachricht löst keine freie Zuordnung aus.
Ein zweiter Druck auf den Knopf oder Schließen bricht das Lernen ab.

Beim Lernen **übergangen** (das Lernen wartet weiter, die Nachricht wirkt normal):
feste `/lightos/…`-Adressen — sie wirken schon ohne Zuordnung, zugeordnet lösten sie
doppelt aus — und das Echo der eigenen Rückmeldung (derselbe Wert auf einer eben
gesendeten Adresse). Sendet das Pult ständig etwas anderes (z. B. Eos `/eos/out/…`),
kann das zuerst gelernt werden: dann einfach noch einmal lernen.

## 3. Rückmeldung an Pult oder Tablet

Reiter **Rückmeldung**: Haken **Rückmeldung senden**, Ziel-IP und Port des Empfängers
(z. B. `192.0.2.20`, Port 9000), dann eine **Vorlage** oder eigene Adressen.

| Zustand | Adresse (LightOS-Vorlage) | Wert |
|---|---|---|
| Fader je Executor | `/lightos/exec/{n}/fader` | im gewählten Bereich |
| Executor aktiv | `/lightos/exec/{n}/aktiv` | 1 = eine Cue ist aktiv, sonst 0 |
| Cue-Nummer (GO-Index) | `/lightos/exec/{n}/cue` | 1, 2, … · 0 = keine |
| Grand Master | `/lightos/grandmaster` | im gewählten Bereich |
| Blackout | `/lightos/blackout` | 1 / 0 |

- **Executoren** (z. B. `1-10` oder `1-4, 8`) bestimmt, für welche Executoren gemeldet wird;
  gesendete Nummer = Executor + **Versatz**.
- Gesendet wird **nur bei Änderung** und höchstens so oft wie unter **Rate** (Standard
  30 Durchgänge je Sekunde). Ein nicht gesendeter Wert wird beim nächsten Durchgang
  nachgeholt. **Alles neu senden** schickt alle Werte erneut, etwa nach dem
  Neustart des Tablets.
- **Echo-Schutz:** Viele Pulte und Oberflächen (grandMA3, MagicQ, TouchOSC) schicken
  einen empfangenen Fader-Wert wieder zurück. Kommt innerhalb von 0,5 s genau ein
  Wert zurück, den LightOS eben selbst für dasselbe Ziel (Fader, Grand Master,
  Blackout) gemeldet hat, wird er verworfen — sonst sprang ein lokal gezogener Fader
  auf den alten Wert zurück. Bewegungen am Pult selbst wirken weiter.
- Leere Adresse = dieser Zustand wird nicht gesendet. Als Ziel-IP gilt nur eine
  IP-Adresse, kein Rechnername.

### Vorlagen

Nur die LightOS-Vorlage ist geprüft. Die übrigen Adressen stammen aus öffentlicher
Doku der Hersteller und sind **ohne Gerät ungeprüft** — im Dialog steht „ungeprüft“.

| Vorlage | Fader-Adresse | Bereich / Versatz | Hinweis |
|---|---|---|---|
| LightOS | `/lightos/exec/{n}/fader` | 0–1 | alle fünf Zustände |
| TouchOSC (Layout „Simple“) | `/1/fader{n}`, aktiv `/1/toggle{n}` | 0–1 | an das eigene Layout anpassen |
| ChamSys MagicQ | `/pb/{n}` | 0–100 | ungeprüft |
| grandMA3 | `/Page1/Fader{n}` | 0–100 / +200 | je nach Pult-Einstellung mit Präfix davor; ungeprüft |
| ETC Eos | `/eos/sub/{n}` | 0–1 | Submaster; ungeprüft |

## 4. Beispiele je Pult

Alle Pult-Adressen unten sind aus öffentlicher Doku übernommen und **ungeprüft** — mit
**Lernen** siehst du, was dein Pult wirklich sendet.

| Quelle | Adresse | Ziel | Einstellungen |
|---|---|---|---|
| TouchOSC | `/1/fader{n}` | Executor-Fader | Bereich 0–1 |
| TouchOSC | `/1/push{n}` | GO Executor | — |
| grandMA3 | `/Page1/Fader{n}` | Executor-Fader | Bereich 0–100, Versatz -200 |
| ChamSys MagicQ | `/pb/{n}` | Executor-Fader | Bereich 0–100 |
| ChamSys MagicQ | `/pb/{n}/go` | GO Executor | — |
| ETC Eos | `/eos/out/event/cue/*/*/fire` | GO Executor | Nummer 1 — jede ausgelöste Eos-Cue schaltet Executor 1 weiter |
| Hog 4 | `/hog/playback/go/0` | GO Executor | Nr. aus Arg. (das Argument ist die Playback-Nummer) |
| beliebig | `/szene/{an,start}` | Funktion starten | Funktion `Lauflicht` |
| beliebig | `/tempo/tap` | Tap-Tempo | — |

Manche Pulte senden erst, wenn man es dort einschaltet — bei MagicQ etwa über den
OSC-Befehl `/feedback/pb+exec`, den das Pult selbst erwartet (ungeprüft).

## 5. Gut zu wissen

- Die Zuordnungen liegen in der Datei `osc_zuordnungen.json` im App-Datenordner, nicht
  in der Show. Fehlt die Datei oder ist sie kaputt, ist nichts zugeordnet und die
  Rückmeldung aus; einzelne kaputte Zeilen fallen beim Laden weg.
- Der OSC-Server lauscht ab Werk nur auf dem eigenen Rechner (`127.0.0.1`). Für ein
  Pult im Netz siehe die Einschränkung unter
  [Externe Pulte](../anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md#nebenweg-osc).
  OSC kennt kein Passwort.
- Eingehende Nachrichten werden im OSC-Empfang nur erkannt; angewandt werden sie in der
  Oberfläche. Die Rückmeldung liest den Zustand dort ebenfalls und sendet nur ins Netz.
- Getestet mit nachgebildetem OSC über `127.0.0.1` (python-osc), nicht mit echten
  Pulten.
