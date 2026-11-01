ID: VCB-37
Prioritaet: P3
Status: done
Status-Notiz: Befund trifft auf main nicht mehr zu: die VC-Taste hat die Aktion „Executor: Umschalten (Go)“ (ButtonAction.TOGGLE, Ziel = Executor-Slot im Feld „Executor-Slot / Function-ID“, src/ui/virtualconsole/vc_button.py ruft executors[slot].press_btn("go")), wird mit action/function_id in der Show gespeichert und geladen, laesst sich wie jede VC-Taste per MIDI lernen und ist in docs/anleitung_vc_widgets/01_button.md beschrieben; Cuelisten machen nur auf einem Executor Licht (src/core/cueliste_ziel.py), BACK liefert das VC-Cuelisten-Widget.
