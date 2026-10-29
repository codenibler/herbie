from dotenv import load_dotenv

import logging
import os
import subprocess

load_dotenv(override=True)

BLUETOOTH_ADDRESS_SOUNDCORE = str(os.getenv("BLUETOOTH_ADDRESS_SOUNDCORE", "")).strip()
SOUNDCORE_SPEAKER_NAME = str(os.getenv("SOUNDCORE_SPEAKER_NAME", "Bluetooth speaker"))


def bluetooth_sink_name() -> str:
    return f"bluez_sink.{BLUETOOTH_ADDRESS_SOUNDCORE.replace(':', '_')}.a2dp_sink"


def bluetooth_ctl_connect() -> bool:
    """Make sure the speaker is connected. The keepalive service normally does this;
    this is a best-effort fallback used at Herbie startup."""
    if not BLUETOOTH_ADDRESS_SOUNDCORE:
        logging.warning("BLUETOOTH_ADDRESS_SOUNDCORE is not set; skipping Bluetooth connect.")
        return False
    info = subprocess.run(["bluetoothctl", "info", BLUETOOTH_ADDRESS_SOUNDCORE], capture_output=True, text=True)
    if "Connected: yes" in info.stdout:
        logging.info(f"{SOUNDCORE_SPEAKER_NAME} is already connected.")
        return True
    subprocess.run(["bluetoothctl", "power", "on"], capture_output=True)
    subprocess.run(["bluetoothctl", "trust", BLUETOOTH_ADDRESS_SOUNDCORE], capture_output=True)
    result = subprocess.run(["bluetoothctl", "connect", BLUETOOTH_ADDRESS_SOUNDCORE], capture_output=True, text=True)
    connected = "Connection successful" in result.stdout
    logging.info("%s connect result: %s", SOUNDCORE_SPEAKER_NAME, "ok" if connected else result.stdout.strip()[-120:])
    return connected


def set_bluetooth_default_sink() -> bool:
    sinks = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True).stdout
    if bluetooth_sink_name() not in sinks:
        logging.warning(
            "Could not find %s sink (%s) in PulseAudio. Is the speaker connected?",
            SOUNDCORE_SPEAKER_NAME,
            bluetooth_sink_name(),
        )
        return False
    result = subprocess.run(["pactl", "set-default-sink", bluetooth_sink_name()], capture_output=True, text=True)
    if result.returncode != 0:
        logging.error("Error setting default sink: %s", result.stderr.strip())
        return False
    logging.info("Default PulseAudio sink set to %s.", bluetooth_sink_name())
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if bluetooth_ctl_connect():
        set_bluetooth_default_sink()
