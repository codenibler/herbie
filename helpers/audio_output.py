from __future__ import annotations

import logging
import numpy as np
import os
import re
import subprocess
import tempfile
import time
import wave
from functools import lru_cache
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv


load_dotenv(override=True)

PREFERRED_USB_AUDIO_DEVICE = "plughw:CARD=Audio,DEV=0"
USB_AUDIO_NAME = "USB Audio"
DEFAULT_WAV_SILENCE_PREFIX_MS = 100
DEFAULT_WAV_LEAD_IN_GAIN = 0.02
DEFAULT_WAKEWORD_DUCKED_VOLUME_PERCENT = 20
DEFAULT_WAKEWORD_DUCK_FADE_DURATION_MS = 350
DEFAULT_WAKEWORD_DUCK_FADE_STEP_COUNT = 7
DEFAULT_APLAY_STOP_WAIT_SECONDS = 0.5

PCM_DTYPE_BY_SAMPLE_WIDTH = {
    1: np.uint8,
    2: np.int16,
    4: np.int32,
}

_ducked_volume_lock = Lock()
_ducked_volume_restore_percent: int | None = None


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
def get_preferred_alsa_card_name() -> str | None:
    preferred_device_name = os.getenv("PREFERRED_WAV_OUTPUT_DEVICE", PREFERRED_USB_AUDIO_DEVICE)
    match = re.search(r"CARD=([^,]+)", preferred_device_name)
    if match:
        return match.group(1)

    preferred_device = get_preferred_alsa_output_device()
    if preferred_device is None:
        return None

    match = re.search(r"CARD=([^,]+)", preferred_device)
    if match:
        return match.group(1)
    return None


def get_preferred_output_volume_percent() -> int | None:
    card_name = get_preferred_alsa_card_name()
    if card_name is None:
        logging.warning("Could not determine ALSA card for preferred output volume control.")
        return None

    result = subprocess.run(
        ["amixer", "-c", card_name, "get", "PCM"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logging.warning("amixer get PCM failed for ALSA card %s.", card_name)
        return None

    match = re.search(r"\[(\d+)%\]", result.stdout)
    if match is None:
        logging.warning("Could not parse current PCM volume for ALSA card %s.", card_name)
        return None

    return int(match.group(1))


def set_preferred_output_volume_percent(volume_percent: int, *, log_change: bool = True) -> bool:
    card_name = get_preferred_alsa_card_name()
    if card_name is None:
        logging.warning("Could not determine ALSA card for preferred output volume control.")
        return False

    normalized_volume_percent = max(0, min(100, int(volume_percent)))
    result = subprocess.run(
        ["amixer", "-c", card_name, "set", "PCM", f"{normalized_volume_percent}%"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logging.warning(
            "Failed to set PCM volume to %s%% on ALSA card %s.",
            normalized_volume_percent,
            card_name,
        )
        return False

    if log_change:
        logging.info(
            "Set preferred output volume to %s%% on ALSA card %s.",
            normalized_volume_percent,
            card_name,
        )
    return True


def build_volume_fade_steps(
    start_volume_percent: int,
    end_volume_percent: int,
    step_count: int,
) -> list[int]:
    normalized_step_count = max(1, int(step_count))
    if start_volume_percent == end_volume_percent:
        return [int(end_volume_percent)]

    step_values = []
    for step_index in range(1, normalized_step_count + 1):
        progress = step_index / normalized_step_count
        interpolated = round(
            start_volume_percent + (end_volume_percent - start_volume_percent) * progress
        )
        if not step_values or step_values[-1] != interpolated:
            step_values.append(interpolated)

    if step_values[-1] != int(end_volume_percent):
        step_values.append(int(end_volume_percent))
    return step_values


def fade_preferred_output_volume_percent(
    start_volume_percent: int,
    end_volume_percent: int,
    duration_ms: int = DEFAULT_WAKEWORD_DUCK_FADE_DURATION_MS,
    step_count: int = DEFAULT_WAKEWORD_DUCK_FADE_STEP_COUNT,
) -> bool:
    fade_steps = build_volume_fade_steps(
        start_volume_percent=start_volume_percent,
        end_volume_percent=end_volume_percent,
        step_count=step_count,
    )
    sleep_interval_seconds = max(0.0, duration_ms / 1000.0 / max(1, len(fade_steps)))

    for index, volume_percent in enumerate(fade_steps):
        is_last_step = index == len(fade_steps) - 1
        if not set_preferred_output_volume_percent(volume_percent, log_change=is_last_step):
            return False
        if not is_last_step and sleep_interval_seconds > 0:
            time.sleep(sleep_interval_seconds)

    logging.info(
        "Faded preferred output volume from %s%% to %s%% in %d ms.",
        start_volume_percent,
        end_volume_percent,
        duration_ms,
    )
    return True


def is_aplay_process_active() -> bool:
    result = subprocess.run(
        ["pgrep", "-x", "aplay"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def duck_preferred_output_volume_if_playing(
    ducked_volume_percent: int = DEFAULT_WAKEWORD_DUCKED_VOLUME_PERCENT,
) -> bool:
    global _ducked_volume_restore_percent

    if not is_aplay_process_active():
        return False

    with _ducked_volume_lock:
        if _ducked_volume_restore_percent is not None:
            return True

        current_volume_percent = get_preferred_output_volume_percent()
        if current_volume_percent is None:
            return False

        fade_duration_ms = int(
            os.getenv("WAKEWORD_DUCK_FADE_DURATION_MS", str(DEFAULT_WAKEWORD_DUCK_FADE_DURATION_MS))
        )
        fade_step_count = int(
            os.getenv("WAKEWORD_DUCK_FADE_STEP_COUNT", str(DEFAULT_WAKEWORD_DUCK_FADE_STEP_COUNT))
        )
        if not fade_preferred_output_volume_percent(
            start_volume_percent=current_volume_percent,
            end_volume_percent=ducked_volume_percent,
            duration_ms=fade_duration_ms,
            step_count=fade_step_count,
        ):
            return False

        _ducked_volume_restore_percent = current_volume_percent
        logging.info(
            "Ducked preferred output volume from %s%% to %s%% while listening.",
            current_volume_percent,
            ducked_volume_percent,
        )
        return True


def restore_preferred_output_volume() -> bool:
    global _ducked_volume_restore_percent

    with _ducked_volume_lock:
        restore_percent = _ducked_volume_restore_percent
        if restore_percent is None:
            return False

        if not set_preferred_output_volume_percent(restore_percent):
            return False

        _ducked_volume_restore_percent = None
        logging.info("Restored preferred output volume to %s%%.", restore_percent)
        return True


def stop_active_aplay_playback() -> bool:
    result = subprocess.run(
        ["pkill", "-x", "aplay"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        deadline = time.time() + float(
            os.getenv("APLAY_STOP_WAIT_SECONDS", str(DEFAULT_APLAY_STOP_WAIT_SECONDS))
        )
        while time.time() < deadline and is_aplay_process_active():
            time.sleep(0.05)
        logging.info("Stopped active aplay playback processes.")
        return True
    return False


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
