from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(override=True)

PREFERRED_USB_AUDIO_DEVICE = "plughw:CARD=Audio,DEV=0"
USB_AUDIO_NAME = "USB Audio"
DEFAULT_WAV_SILENCE_PREFIX_MS = 100


@lru_cache(maxsize=1)
def get_preferred_alsa_output_device() -> str | None:
    preferred_device_name = os.getenv("PREFERRED_WAV_OUTPUT_DEVICE", PREFERRED_USB_AUDIO_DEVICE)
    try:
        result = subprocess.run(
            ["aplay", "-L"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logging.warning("aplay is not available; cannot resolve preferred USB Audio output device.")
        return None

    if result.returncode != 0:
        logging.warning("aplay -L failed while resolving preferred USB Audio device.")
        return None

    available_devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if preferred_device_name in available_devices:
        return preferred_device_name

    for device in available_devices:
        if "CARD=Audio" in device and "DEV=0" in device:
            return device

    return None


def build_wav_playback_command(file_path: str | Path) -> list[str]:
    command = ["aplay"]
    preferred_device = get_preferred_alsa_output_device()
    if preferred_device is not None:
        command.extend(["-D", preferred_device])
    else:
        logging.warning("Preferred USB Audio device not found. Falling back to default aplay output.")
    command.append(str(file_path))
    return command


@lru_cache(maxsize=1)
def get_wav_silence_prefix_ms() -> int:
    raw_value = os.getenv("WAV_SILENCE_PREFIX_MS", str(DEFAULT_WAV_SILENCE_PREFIX_MS))
    try:
        silence_ms = int(raw_value)
    except ValueError:
        logging.warning(
            "Invalid WAV_SILENCE_PREFIX_MS value %r. Falling back to %d ms.",
            raw_value,
            DEFAULT_WAV_SILENCE_PREFIX_MS,
        )
        return DEFAULT_WAV_SILENCE_PREFIX_MS

    if silence_ms < 0:
        logging.warning(
            "Negative WAV_SILENCE_PREFIX_MS value %d is invalid. Falling back to %d ms.",
            silence_ms,
            DEFAULT_WAV_SILENCE_PREFIX_MS,
        )
        return DEFAULT_WAV_SILENCE_PREFIX_MS

    return silence_ms


def prepend_silence_to_wav(file_path: str | Path, silence_ms: int | None = None) -> Path:
    source_path = Path(file_path)
    if silence_ms is None:
        silence_ms = get_wav_silence_prefix_ms()

    with wave.open(str(source_path), "rb") as source_wav:
        channels = source_wav.getnchannels()
        sample_width = source_wav.getsampwidth()
        sample_rate = source_wav.getframerate()
        frames = source_wav.readframes(source_wav.getnframes())

    silence_frame_count = int(sample_rate * silence_ms / 1000)
    silence_bytes = b"\x00" * silence_frame_count * channels * sample_width

    with tempfile.NamedTemporaryFile(
        prefix=f"{source_path.stem}_prefixed_",
        suffix=".wav",
        delete=False,
    ) as temp_file:
        padded_path = Path(temp_file.name)

    with wave.open(str(padded_path), "wb") as padded_wav:
        padded_wav.setnchannels(channels)
        padded_wav.setsampwidth(sample_width)
        padded_wav.setframerate(sample_rate)
        padded_wav.writeframes(silence_bytes + frames)

    return padded_path


def cleanup_temp_wav(file_path: str | Path | None) -> None:
    if file_path is None:
        return

    path = Path(file_path)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logging.warning(f"Failed to delete temporary WAV {path}: {exc}")
