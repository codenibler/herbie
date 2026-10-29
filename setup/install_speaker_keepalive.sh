#!/usr/bin/env bash
# Install and enable the Bluetooth speaker keepalive as a systemd --user service.
# Requires: pulseaudio-module-bluetooth, the speaker paired+trusted, and
# BLUETOOTH_ADDRESS_SOUNDCORE set in .env. Linger must be enabled for the user
# so the service runs without a login session: loginctl enable-linger $USER
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cp "$HERE/herbie-speaker-keepalive.service" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now herbie-speaker-keepalive.service
systemctl --user --no-pager status herbie-speaker-keepalive.service | head -5
