#!/usr/bin/env bash
# Day-to-day badge workflow. Run from anywhere; it works in firmware/.
#
#   ./dev.sh push      copy changed files in badge/ to the badge, reset, show output
#   ./dev.sh ls        compare badge/ with what is on the badge
#   ./dev.sh ota [H]   push over WiFi (badge on any USB power), then reset;
#                      H = host or IP, default $BADGE_HOST or kevin-badge.local
#   ./dev.sh ota-ls [H] compare over WiFi
#   ./dev.sh repl      open the REPL (Ctrl-] or Ctrl-x to leave)
#   ./dev.sh log       reset and watch the badge's print() output
#   ./dev.sh run F.py  run a file from this computer without copying it
#                      (no display code: run soft-resets, and setting LVGL up a
#                      second time after a soft reset hangs the badge; RESET fixes it)
#   ./dev.sh stubs     (re)install editor stubs into ../typings
#
# Port: $BADGE_PORT if set, else the single badge-style Espressif device
# (USB 303a:4001) in /dev/serial/by-id. The USB-JTAG boards (like a Feather)
# are never picked automatically.
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-}" in
  ota)    exec python3 scripts/update.py push --reset --host "${2:-${BADGE_HOST:-kevin-badge.local}}" ;;
  ota-ls) exec python3 scripts/update.py ls --host "${2:-${BADGE_HOST:-kevin-badge.local}}" ;;
esac

if [[ -z "${BADGE_PORT:-}" ]]; then
  shopt -s nullglob
  ports=(/dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_*)
  if (( ${#ports[@]} != 1 )); then
    echo "Found ${#ports[@]} badge-like ports; set BADGE_PORT=/dev/ttyACMx" >&2
    ls -l /dev/serial/by-id/ >&2 || true
    exit 1
  fi
  BADGE_PORT=${ports[0]}
fi
export BADGE_PORT
mp=(mpremote connect "$BADGE_PORT")

case "${1:-}" in
  push)  python3 scripts/update.py push --port "$BADGE_PORT" && "${mp[@]}" reset && sleep 2 && exec mpremote connect "$BADGE_PORT" resume repl ;;
  ls)    exec python3 scripts/update.py ls --port "$BADGE_PORT" ;;
  repl)  exec "${mp[@]}" repl ;;
  log)   "${mp[@]}" reset; sleep 2; exec mpremote connect "$BADGE_PORT" resume repl ;;
  run)   shift; exec "${mp[@]}" run "$@" ;;
  stubs) python3 -m pip install -U --no-user --target ../typings "micropython-esp32-esp32_generic_s3-stubs==1.24.1.*" ;;
  *)     sed -n '2,16p' "$0"; exit 1 ;;
esac
