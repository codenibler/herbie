#!/usr/bin/env python3
"""Keep the Bluetooth speaker connected and awake.

Runs forever as a systemd user service:

1. Make sure the speaker is connected (reconnect through bluetoothctl if not).
2. Wait for its PulseAudio A2DP sink and make that sink the default output.
3. Stream a continuous, practically inaudible dither signal to the sink through
   pacat. The speaker then never sees an idle audio link, so its auto power-off
   never fires, and PulseAudio never suspends the sink, so the A2DP transport
   stays open.

Configuration comes from the project .env:
  BLUETOOTH_ADDRESS_SOUNDCORE   speaker MAC address (required)
  SPEAKER_KEEPALIVE_AMPLITUDE   peak sample value of the dither, 16-bit scale
                                (default 4, roughly -78 dBFS; 1 is the minimum)
"""
from __future__ import annotations

import logging
import os
import random
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:  # the venv interpreter has dotenv; system python may not
    pass

MAC = os.getenv("BLUETOOTH_ADDRESS_SOUNDCORE", "").strip().strip('"').strip("'")
AMPLITUDE = max(1, min(32, int(os.getenv("SPEAKER_KEEPALIVE_AMPLITUDE", "4"))))
SAMPLE_RATE = 44100
CHANNELS = 2
CHUNK_SECONDS = 0.1
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_SECONDS)
CONNECT_RETRY_SECONDS = 5
SINK_WAIT_SECONDS = 15

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def sink_name() -> str:
    return f"bluez_sink.{MAC.replace(':', '_')}.a2dp_sink"


def run(command: list[str], timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def is_connected() -> bool:
    result = run(["bluetoothctl", "info", MAC])
    return "Connected: yes" in result.stdout


def connect() -> bool:
    run(["bluetoothctl", "power", "on"])
    result = run(["bluetoothctl", "connect", MAC], timeout=40)
    ok = "Connection successful" in result.stdout or is_connected()
    if not ok:
        logging.warning("Connect attempt failed: %s", (result.stdout + result.stderr).strip()[-200:])
    return ok


def sink_present() -> bool:
    result = run(["pactl", "list", "sinks", "short"])
    return sink_name() in result.stdout


def wait_for_sink() -> bool:
    deadline = time.time() + SINK_WAIT_SECONDS
    while time.time() < deadline:
        if sink_present():
            return True
        time.sleep(1)
    return False


def set_default_sink() -> None:
    result = run(["pactl", "set-default-sink", sink_name()])
    if result.returncode == 0:
        logging.info("Default PulseAudio sink set to %s", sink_name())
    else:
        logging.warning("Could not set default sink: %s", result.stderr.strip())


def build_dither_chunks(count: int = 16) -> list[bytes]:
    """Precompute a few chunks of random +/-AMPLITUDE samples (16-bit little-endian)."""
    chunks = []
    for _ in range(count):
        samples = bytearray()
        for _ in range(CHUNK_FRAMES * CHANNELS):
            value = random.choice((-AMPLITUDE, AMPLITUDE))
            samples += value.to_bytes(2, "little", signed=True)
        chunks.append(bytes(samples))
    return chunks


def stream_keepalive(chunks: list[bytes]) -> None:
    """Feed dither to pacat until pacat exits (sink gone, speaker dropped, etc.)."""
    command = [
        "pacat",
        "--playback",
        "--raw",
        f"--device={sink_name()}",
        "--format=s16le",
        f"--rate={SAMPLE_RATE}",
        f"--channels={CHANNELS}",
        "--stream-name=herbie-speaker-keepalive",
        "--property=media.role=background",
    ]
    logging.info("Starting keepalive stream (amplitude %d) to %s", AMPLITUDE, sink_name())
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    index = 0
    try:
        while True:
            process.stdin.write(chunks[index])  # blocks when the stream buffer is full
            process.stdin.flush()
            index = (index + 1) % len(chunks)
    except (BrokenPipeError, OSError):
        pass
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        stderr = process.stderr.read().decode(errors="replace").strip() if process.stderr else ""
        process.wait(timeout=5)
        logging.warning("Keepalive stream ended (pacat exit %s). %s", process.returncode, stderr[-300:])


def main() -> int:
    if not MAC:
        logging.error("BLUETOOTH_ADDRESS_SOUNDCORE is not set; nothing to keep alive.")
        return 2

    chunks = build_dither_chunks()
    logging.info("Speaker keepalive started for %s", MAC)
    while True:
        if not is_connected():
            logging.info("Speaker not connected; attempting to connect.")
            if not connect():
                time.sleep(CONNECT_RETRY_SECONDS)
                continue
            logging.info("Speaker connected.")

        if not wait_for_sink():
            logging.warning("A2DP sink did not appear within %ss; retrying.", SINK_WAIT_SECONDS)
            time.sleep(CONNECT_RETRY_SECONDS)
            continue

        set_default_sink()
        stream_keepalive(chunks)
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
