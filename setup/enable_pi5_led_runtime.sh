#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODULE_DIR="${REPO_ROOT}/rpi_ws281x/rp1_ws281x_pwm"
MODULE_KO="${MODULE_DIR}/rp1_ws281x_pwm.ko"
OVERLAY_DTBO="${MODULE_DIR}/rp1_ws281x_pwm.dtbo"
PYTHON_BIN="${REPO_ROOT}/venv/bin/python"
DEVICE_NODE="/dev/ws281x_pwm"
GPIO_GROUP="${GPIO_GROUP:-gpio}"
PWM_PIN="${PWM_PIN:-18}"
PWM_CHANNEL="${PWM_CHANNEL:-2}"

log() {
    printf '[pi5-led] %s\n' "$*"
}

require_file() {
    local path="$1"
    if [[ ! -e "${path}" ]]; then
        log "Missing required path: ${path}"
        exit 1
    fi
}

require_file "${MODULE_DIR}"
require_file "${PYTHON_BIN}"

log "Building RP1 WS281x kernel module"
(
    cd "${MODULE_DIR}"
    make
)

log "Building RP1 WS281x device-tree overlay"
(
    cd "${MODULE_DIR}"
    ./dts.sh
)

require_file "${MODULE_KO}"
require_file "${OVERLAY_DTBO}"

if ! lsmod | grep -q '^rp1_ws281x_pwm '; then
    log "Loading kernel module"
    sudo insmod "${MODULE_KO}" pwm_channel="${PWM_CHANNEL}"
else
    log "Kernel module already loaded"
fi

if ! sudo dtoverlay -l | grep -q 'rp1_ws281x_pwm'; then
    log "Loading dtoverlay"
    sudo dtoverlay -d "${MODULE_DIR}" rp1_ws281x_pwm
else
    log "Dtoverlay already loaded"
fi

log "Configuring GPIO${PWM_PIN} for Pi 5 PWM"
sudo pinctrl set "${PWM_PIN}" a3 pn

for _ in 1 2 3 4 5; do
    if [[ -e "${DEVICE_NODE}" ]]; then
        break
    fi
    sleep 0.2
done

if [[ ! -e "${DEVICE_NODE}" ]]; then
    log "Device node ${DEVICE_NODE} did not appear."
    exit 1
fi

log "Granting ${GPIO_GROUP} access to ${DEVICE_NODE}"
sudo chgrp "${GPIO_GROUP}" "${DEVICE_NODE}"
sudo chmod 660 "${DEVICE_NODE}"

log "Running Herbie LED init check"
"${PYTHON_BIN}" - <<'PY'
from toolbox import led_strip
print(f"start_result={led_strip.start_led_strip_controller()}")
PY

log "Final state"
ls -l "${DEVICE_NODE}"
pinctrl get "${PWM_PIN}"
log "Pi 5 LED runtime setup complete"
