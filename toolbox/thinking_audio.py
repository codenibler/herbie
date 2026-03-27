from __future__ import annotations

from helpers.audio_output import (
    build_wav_playback_command,
    cleanup_temp_wavs,
    fade_preferred_output_volume_percent,
    get_preferred_output_volume_percent,
    prepare_wav_for_output_channel_mode,
    set_preferred_output_volume_percent,
)
from pathlib import Path
from threading import Event, Lock, Thread

import logging
import numpy as np
import os
import subprocess
import tempfile
import wave

from dotenv import load_dotenv


load_dotenv(override=True)

THINKING_NOISE_DIR = Path(os.getenv("THINKING_NOISE_DIR", "herbie_responses/thinking_noise"))
THINKING_NOISE_CLIP_SECONDS = int(os.getenv("THINKING_NOISE_CLIP_SECONDS", 30))
THINKING_NOISE_FADE_MS = int(os.getenv("THINKING_NOISE_FADE_MS", 250))
THINKING_NOISE_MAX_GAIN = 0.20
THINKING_NOISE_GAIN = min(
    float(os.getenv("THINKING_NOISE_GAIN", THINKING_NOISE_MAX_GAIN)),
    THINKING_NOISE_MAX_GAIN,
)
THINKING_NOISE_STOP_MAX_WAIT_SECONDS = float(
    os.getenv("THINKING_NOISE_STOP_MAX_WAIT_SECONDS", 2.5)
)
THINKING_NOISE_FILE_PREFERENCES = (
    "thinking_noise.wav",
    "thinking.wav",
    "source.wav",
)

PCM_DTYPE_BY_SAMPLE_WIDTH = {
    1: np.uint8,
    2: np.int16,
    4: np.int32,
}


def _get_thinking_noise_path() -> Path | None:
    if not THINKING_NOISE_DIR.exists():
        logging.warning("Thinking noise directory does not exist: %s", THINKING_NOISE_DIR)
        return None

    for file_name in THINKING_NOISE_FILE_PREFERENCES:
        candidate_path = THINKING_NOISE_DIR / file_name
        if candidate_path.is_file():
            return candidate_path

    thinking_paths = sorted(
        path
        for path in THINKING_NOISE_DIR.iterdir()
        if path.is_file() and path.suffix.lower() == ".wav"
    )
    if not thinking_paths:
        logging.warning("No WAV thinking noise files found in %s", THINKING_NOISE_DIR)
        return None

    if len(thinking_paths) > 1:
        logging.info(
            "Multiple thinking noise files found. Using %s.",
            thinking_paths[0].name,
        )
    return thinking_paths[0]


def _validate_clip_duration(source_path: Path, frame_count: int, sample_rate: int) -> None:
    clip_duration_seconds = frame_count / max(1, sample_rate)
    if clip_duration_seconds < THINKING_NOISE_CLIP_SECONDS - 0.25:
        logging.warning(
            "Thinking clip %s is shorter than the expected %ss duration (%.2fs).",
            source_path,
            THINKING_NOISE_CLIP_SECONDS,
            clip_duration_seconds,
        )


def _build_gain_envelope(
    frame_count: int,
    channels: int,
    fade_frame_count: int,
    *,
    include_fade_in: bool,
    include_fade_out: bool,
) -> np.ndarray:
    if frame_count <= 1:
        return np.full(frame_count * max(1, channels), THINKING_NOISE_GAIN, dtype=np.float32)

    fade_frame_count = min(max(1, fade_frame_count), max(1, frame_count // 2))
    envelope = np.full(frame_count, THINKING_NOISE_GAIN, dtype=np.float32)

    if include_fade_in:
        envelope[:fade_frame_count] = np.linspace(
            0.0,
            THINKING_NOISE_GAIN,
            num=fade_frame_count,
            endpoint=True,
        )

    if include_fade_out:
        fade_out = np.linspace(
            THINKING_NOISE_GAIN,
            0.0,
            num=fade_frame_count,
            endpoint=True,
        )
        envelope[-fade_frame_count:] = np.minimum(envelope[-fade_frame_count:], fade_out)

    return np.repeat(envelope, max(1, channels))


def _apply_gain_envelope(
    frames: bytes,
    sample_width: int,
    channels: int,
    fade_frame_count: int,
    *,
    include_fade_in: bool,
    include_fade_out: bool,
) -> bytes:
    if not frames:
        return frames

    dtype = PCM_DTYPE_BY_SAMPLE_WIDTH.get(sample_width)
    if dtype is None:
        logging.warning("Unsupported sample width %d for thinking audio.", sample_width)
        return frames

    samples = np.frombuffer(frames, dtype=dtype).copy()
    if samples.size == 0:
        return frames

    frame_count = max(1, samples.size // max(1, channels))
    envelope = _build_gain_envelope(
        frame_count,
        channels,
        fade_frame_count,
        include_fade_in=include_fade_in,
        include_fade_out=include_fade_out,
    )[: samples.size]

    if sample_width == 1:
        centered_samples = samples.astype(np.float32) - 128.0
        scaled_samples = np.clip(
            np.round(centered_samples * envelope + 128.0),
            0,
            255,
        ).astype(np.uint8)
        return scaled_samples.tobytes()

    info = np.iinfo(dtype)
    scaled_samples = np.clip(
        np.round(samples.astype(np.float32) * envelope),
        info.min,
        info.max,
    ).astype(dtype)
    return scaled_samples.tobytes()


def _build_prepared_thinking_clip(
    source_path: Path,
    *,
    include_fade_in: bool,
    include_fade_out: bool,
    clip_label: str,
) -> Path | None:
    try:
        with wave.open(str(source_path), "rb") as source_wav:
            channels = source_wav.getnchannels()
            sample_width = source_wav.getsampwidth()
            sample_rate = source_wav.getframerate()
            frame_count = source_wav.getnframes()
            if frame_count <= 0:
                logging.warning("Thinking noise file is empty: %s", source_path)
                return None
            _validate_clip_duration(source_path, frame_count, sample_rate)
            frames = source_wav.readframes(frame_count)
    except (wave.Error, OSError) as exc:
        logging.warning("Failed to read thinking noise file %s: %s", source_path, exc)
        return None

    fade_frame_count = int(sample_rate * THINKING_NOISE_FADE_MS / 1000)
    processed_frames = _apply_gain_envelope(
        frames,
        sample_width,
        channels,
        fade_frame_count,
        include_fade_in=include_fade_in,
        include_fade_out=include_fade_out,
    )

    with tempfile.NamedTemporaryFile(
        prefix=f"{source_path.stem}_{clip_label}_",
        suffix=".wav",
        delete=False,
    ) as temp_file:
        temp_clip_path = Path(temp_file.name)

    with wave.open(str(temp_clip_path), "wb") as temp_wav:
        temp_wav.setnchannels(channels)
        temp_wav.setsampwidth(sample_width)
        temp_wav.setframerate(sample_rate)
        temp_wav.writeframes(processed_frames)

    return temp_clip_path


class ThinkingAudioManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_requested = Event()
        self._worker: Thread | None = None
        self._current_process: subprocess.Popen | None = None

    def start_playback(self) -> bool:
        thinking_path = _get_thinking_noise_path()
        if thinking_path is None:
            return False

        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return True

            self._stop_requested.clear()
            self._worker = Thread(
                target=self._playback_worker,
                args=(thinking_path,),
                name="herbie-thinking-audio",
                daemon=True,
            )
            self._worker.start()

        logging.info("Started thinking audio playback from %s.", thinking_path.name)
        return True

    def stop_playback(self) -> bool:
        with self._lock:
            worker = self._worker
            is_active = worker is not None and worker.is_alive()
            self._stop_requested.set()
            current_process = self._current_process

        if not is_active or worker is None:
            return False

        restore_volume_percent: int | None = None
        if current_process is not None and current_process.poll() is None:
            current_volume_percent = get_preferred_output_volume_percent()
            if current_volume_percent is not None:
                restore_volume_percent = current_volume_percent
                if current_volume_percent > 0:
                    fade_step_count = max(2, THINKING_NOISE_FADE_MS // 50)
                    fade_preferred_output_volume_percent(
                        start_volume_percent=current_volume_percent,
                        end_volume_percent=0,
                        duration_ms=THINKING_NOISE_FADE_MS,
                        step_count=fade_step_count,
                    )
            current_process.terminate()

        worker.join(timeout=THINKING_NOISE_STOP_MAX_WAIT_SECONDS)
        if worker.is_alive():
            logging.warning("Thinking audio did not stop gracefully. Terminating active clip.")
            with self._lock:
                current_process = self._current_process
            if current_process is not None and current_process.poll() is None:
                current_process.terminate()
            worker.join(timeout=0.5)

        if restore_volume_percent is not None and set_preferred_output_volume_percent(
            restore_volume_percent,
            log_change=False,
        ):
            logging.info(
                "Restored preferred output volume to %s%% after thinking audio fade-out.",
                restore_volume_percent,
            )

        logging.info("Stopped thinking audio playback.")
        return True

    def _playback_worker(self, thinking_path: Path) -> None:
        intro_clip_path = _build_prepared_thinking_clip(
            thinking_path,
            include_fade_in=True,
            include_fade_out=False,
            clip_label="thinking_intro",
        )
        loop_clip_path = _build_prepared_thinking_clip(
            thinking_path,
            include_fade_in=False,
            include_fade_out=False,
            clip_label="thinking_loop",
        )
        if intro_clip_path is None or loop_clip_path is None:
            cleanup_temp_wavs(intro_clip_path, loop_clip_path)
            with self._lock:
                self._worker = None
                self._current_process = None
            return

        intro_playback_path = prepare_wav_for_output_channel_mode(intro_clip_path)
        loop_playback_path = prepare_wav_for_output_channel_mode(loop_clip_path)
        try:
            if self._stop_requested.is_set():
                return

            if not self._play_clip(intro_playback_path):
                return

            while not self._stop_requested.is_set():
                if not self._play_clip(loop_playback_path):
                    break
        finally:
            cleanup_temp_wavs(
                intro_clip_path,
                loop_clip_path,
                intro_playback_path,
                loop_playback_path,
            )
            with self._lock:
                self._worker = None
                self._current_process = None

    def _play_clip(self, clip_path: Path) -> bool:
        if self._stop_requested.is_set():
            return False

        try:
            process = subprocess.Popen(build_wav_playback_command(clip_path))
        except OSError as exc:
            logging.warning("Failed to start thinking audio playback for %s: %s", clip_path, exc)
            return False

        with self._lock:
            self._current_process = process

        return_code = process.wait()

        with self._lock:
            if self._current_process is process:
                self._current_process = None

        if self._stop_requested.is_set():
            return False

        if return_code != 0:
            logging.warning(
                "Thinking audio playback exited with code %s for %s.",
                return_code,
                clip_path,
            )
            return False

        return True


thinking_audio_manager = ThinkingAudioManager()
THINKING_AUDIO_MANAGER = thinking_audio_manager


def start_thinking_audio() -> bool:
    return thinking_audio_manager.start_playback()


def stop_thinking_audio() -> bool:
    return thinking_audio_manager.stop_playback()
