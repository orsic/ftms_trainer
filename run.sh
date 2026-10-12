#!/usr/bin/env bash
# Usage: ./run.sh test [pytest args] | ./run.sh <scan|click-learn|ride FILE.zwo|export FILE.csv>
set -euo pipefail
cd "$(dirname "$0")"
[ -f vars.env ] || { echo "Missing vars.env (copy vars.env.example)"; exit 1; }
set -a; source vars.env; set +a
mkdir -p "$OUTPUT_DIR"

tty_flags=(-i)
[ -t 0 ] && tty_flags=(-it)

if [ "${1:-}" = test ]; then
    shift
    podman build -q --target test -t trainer-test . >/dev/null
    exec podman run --rm "${tty_flags[@]}" -v "$PWD":/app:Z trainer-test python -m pytest "$@"
fi

podman build -q --target base -t trainer . >/dev/null
exec podman run --rm "${tty_flags[@]}" --userns=keep-id \
    -v "$PWD":/app:Z \
    -v "$OUTPUT_DIR":/out:Z \
    -v /run/dbus/system_bus_socket:/run/dbus/system_bus_socket \
    -v "$XDG_RUNTIME_DIR/bus":/run/user/1000/bus \
    -v "$XDG_RUNTIME_DIR/pulse/native":/run/pulse/native \
    --env-file vars.env \
    -e OUTPUT_DIR=/out \
    -e HOST_OUTPUT_DIR="$OUTPUT_DIR" \
    -e DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
    -e PULSE_SERVER=unix:/run/pulse/native \
    -e TERM=xterm-256color \
    trainer python -m trainer "$@"
