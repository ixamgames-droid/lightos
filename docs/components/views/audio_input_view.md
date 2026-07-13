# audio_input_view (AudioInputView)

> Konfiguriert den Audio-Capture (WASAPI-Loopback) und zeigt Beats + BPM live an.

## Zweck

Einstellseite für die Audio-Beat-Erkennung. Wählt die Capture-Quelle
(WASAPI-Loopback), startet/stoppt die Aufnahme und visualisiert erkannte Beats
und laufende BPM. Ist keine Capture-Backend verfügbar, wird ein Hinweis statt der
Controls gezeigt.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Quelle/Gerät | WASAPI-Loopback-Endpoint wählen |
| Start/Stop Capture | Audio-Aufnahme + Detection ein/aus |
| Beat-/BPM-Anzeige | Live-Feedback erkannter Beats und BPM |
| Detection-Parameter | Empfindlichkeit/Schwellen der Beat-Erkennung |

## Verknüpfungen

- **Audio-Capture-Thread:** Capture-Callback läuft im Capture-Thread,
  Detektor-Callback im Detector-Thread — UI-Updates marshallen auf den Qt-Thread.
- **BPM-Manager:** erkannte BPM speist die Audio-Quelle des `bpm_manager`
  (siehe [`bpm_manager_view`](bpm_manager_view.md)).
- **Fehlender Backend:** blendet Controls aus, zeigt Hinweis.

## Zugehörige Tests

- `tests/test_audio_input_view.py` — View-Aufbau, Thread-Marshalling, Leerzustand.

## Quelle (file:line)

- `src/ui/views/audio_input_view.py:36` — Klasse `AudioInputView`
- `src/ui/views/audio_input_view.py:301` — Capture-Thread-Callback
- `src/ui/views/audio_input_view.py:324` — Detector-Thread-Callback
- `src/ui/views/audio_input_view.py:195` — Leerzustand (kein Backend)
