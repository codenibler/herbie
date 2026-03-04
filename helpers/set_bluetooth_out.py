from dotenv import load_dotenv

import subprocess
import logging
import os
import re

load_dotenv(override=True)

BLUETOOTH_ADDRESS_SOUNDCORE = str(os.getenv("BLUETOOTH_ADDRESS_SOUNDCORE"))
SOUNDCORE_SPEAKER_NAME = str(os.getenv("SOUNDCORE_SPEAKER_NAME"))

def bluetooth_ctl_connect():
    bluetooth_power_on = subprocess.run(["bluetoothctl", "info", BLUETOOTH_ADDRESS_SOUNDCORE], capture_output=True, text=True)
    if "Connected: yes" in bluetooth_power_on.stdout:
        logging.info(f"{SOUNDCORE_SPEAKER_NAME} is already connected.")
        return
    subprocess.run(["bluetoothctl", "power", "on"])
    subprocess.run(["bluetoothctl", "connect", BLUETOOTH_ADDRESS_SOUNDCORE])
    subprocess.run(["bluetoothctl", "trust", BLUETOOTH_ADDRESS_SOUNDCORE])

if __name__ == "__main__":
    bluetooth_ctl_connect()
    found_speaker = False
    out = subprocess.run(
        ["wpctl", "status"], 
        capture_output=True, 
        text=True
    ).stdout
    sink_section = False
    for line in out.splitlines():
        lowercase_line = line.lower()
        if SOUNDCORE_SPEAKER_NAME.lower() in lowercase_line and sink_section:
            sink_id = re.search(r"\b(\d+)\.", line)
            if sink_id:
                sink_id = sink_id.group(1)
                logging.info(f"Found {SOUNDCORE_SPEAKER_NAME} in wpctl status output. Sink ID: {sink_id}")
                result = subprocess.run(["wpctl", "set-default", sink_id], capture_output=True, text=True)
                if result.returncode != 0:
                    logging.error(f"Error setting default sink: {result.stderr}")
                found_speaker = True
                break
        elif "sinks" in lowercase_line:
            sink_section = True
        elif any(keyword in lowercase_line for keyword in ["devices", "sources", "filters", "streams"]):
            sink_section = False

    if not found_speaker:
        logging.warning(f"Could not find {SOUNDCORE_SPEAKER_NAME} in wpctl status output. Please check the speaker name and ensure it's connected via Bluetooth.")



