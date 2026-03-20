from __future__ import annotations

import logging
import numpy as np
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
DEFAULT_WAV_LEAD_IN_GAIN = 0.02

PCM_DTYPE_BY_SAMPLE_WIDTH = {
    1: np.uint8,
    2: np.int16,
    4: np.int32,
}


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


@lru_cache(maxsize=1)
def get_wav_lead_in_gain() -> float:
    raw_value = os.getenv("WAV_LEAD_IN_GAIN", str(DEFAULT_WAV_LEAD_IN_GAIN))
    try:
        lead_in_gain = float(raw_value)
    except ValueError:
        logging.warning(
            "Invalid WAV_LEAD_IN_GAIN value %r. Falling back to %.3f.",
            raw_value,
            DEFAULT_WAV_LEAD_IN_GAIN,
        )
        return DEFAULT_WAV_LEAD_IN_GAIN

    if not 0 <= lead_in_gain <= 1:
        logging.warning(
            "WAV_LEAD_IN_GAIN %.3f is out of range. Falling back to %.3f.",
            lead_in_gain,
            DEFAULT_WAV_LEAD_IN_GAIN,
        )
        return DEFAULT_WAV_LEAD_IN_GAIN

    return lead_in_gain


def scale_pcm_frames(frames: bytes, sample_width: int, gain: float) -> bytes:
    if not frames:
        return frames

    dtype = PCM_DTYPE_BY_SAMPLE_WIDTH.get(sample_width)
    if dtype is None:
        logging.warning(
            "Unsupported WAV sample width %d for lead-in scaling. Falling back to silence.",
            sample_width,
        )
        return b"\x00" * len(frames)

    samples = np.frombuffer(frames, dtype=dtype).copy()

    if sample_width == 1:
        centered = samples.astype(np.float32) - 128.0
        scaled = np.clip(np.round(centered * gain + 128.0), 0, 255).astype(np.uint8)
        return scaled.tobytes()

    info = np.iinfo(dtype)
    scaled = np.clip(
        np.round(samples.astype(np.float32) * gain),
        info.min,
        info.max,
    ).astype(dtype)
    return scaled.tobytes()


def prepend_silence_to_wav(file_path: str | Path, silence_ms: int | None = None) -> Path:
    source_path = Path(file_path)
    if silence_ms is None:
        silence_ms = get_wav_silence_prefix_ms()

    with wave.open(str(source_path), "rb") as source_wav:
        channels = source_wav.getnchannels()
        sample_width = source_wav.getsampwidth()
        sample_rate = source_wav.getframerate()
        frames = source_wav.readframes(source_wav.getnframes())

    prefix_frame_count = int(sample_rate * silence_ms / 1000)
    prefix_byte_count = prefix_frame_count * channels * sample_width
    lead_in_source = frames[:prefix_byte_count]
    lead_in_bytes = scale_pcm_frames(lead_in_source, sample_width, get_wav_lead_in_gain())
    if len(lead_in_bytes) < prefix_byte_count:
        lead_in_bytes += b"\x00" * (prefix_byte_count - len(lead_in_bytes))

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
        padded_wav.writeframes(lead_in_bytes + frames)

    return padded_path


def cleanup_temp_wav(file_path: str | Path | None) -> None:
    if file_path is None:
        return

    path = Path(file_path)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logging.warning(f"Failed to delete temporary WAV {path}: {exc}")
