#!/usr/bin/env bash
# Haelt auf Linux-Systemen mit zwei Realtek-Mikrofonbuchsen den Capture-MUX auf
# der tatsaechlich eingesteckten Buchse. PipeWire/ACP setzt Input Source 0 bei
# Profilwechseln gelegentlich auf "Mic" zurueck, obwohl Jack-Sense "Mic Jack 1"
# meldet. Auf anderer Hardware ist das Skript ein stiller No-op.
set -u

card="${LIGHTOS_ALSA_CARD:-0}"

jack_state="$(amixer -c "$card" cget numid=19 2>/dev/null || true)"
source_info="$(amixer -c "$card" cget numid=8 2>/dev/null || true)"
jack_value="${jack_state##*: values=}"
source_value="${source_info##*: values=}"

if [[ "$jack_value" != "on" ]]; then
    exit 0
fi
if [[ "$source_info" != *"Item #1 'Mic 1'"* ]]; then
    exit 0
fi
if [[ "$source_value" == "1" ]]; then
    exit 0
fi

amixer -q -c "$card" cset numid=8 1
