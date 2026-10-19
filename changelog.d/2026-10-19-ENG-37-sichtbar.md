### 2026-10-19 — Modify sichtbar machen: Zeichen auf Taste und Fader, Hinweis im Chaser-Editor (ENG-37)

#### Neu / Tests
- **Virtuelle Konsole:** Eine Taste, deren Funktion als Modify-Effekt läuft, zeigt unten links
  das Zeichen der Betriebsart — **+** Addieren (Bernstein), **−** Abziehen (Blau), **◐** Abdunkeln
  (Grau), in den Farben der Matrix-Vorschau. Ein Effekt-Fader mit festem Ziel zeigt es links unten
  neben der Spur. Die Beschriftung weicht dem Zeichen aus; Farb-Badge und Gobo oben rechts bleiben
  frei. Haken oder Betriebsart umgestellt → die Konsole zeichnet sofort neu.
- **Chaser-Editor:** Ein Schritt, dessen Funktion (oder ein Kind einer Sammlung/Show darin) ein
  Modify-Effekt ist, steht gelb mit ⚠ und Tooltip in der Liste; darunter die gelbe Zeile
  „Modify-Effekte geben als Chaser-Schritt nichts aus – direkt, in einer Sammlung oder der
  Show-Zeitleiste starten“ (die Engine sperrt solche Schritte).
- Zeichen und Farben aus einer Quelle (`src/ui/widgets/modify_zeichen.py`), auch für die Vorschau
  im Matrix-Editor; `stufen.modify_unter` findet Modify-Effekte auch in Sammlungen und Shows.
- Backlog: ENG-36/38/39/40 auf erledigt, ENG-35/37 abgeglichen, neu ENG-42 (Läufer mit „dunkle
  Lampen durchlassen“) und ENG-43 (Bewegungs-Modify als Versatz). Anleitungen Prioritäten §8 und
  Dimmer-Matrix §5 ergänzt.
- Tests: `tests/test_eng37_modify_sichtbar.py`.
