import sounddevice as sd
import numpy as np
import logging
import asyncio
import time
import wave
import io
import os
from math import ceil

from helpers.adaptive_speech_detector import (
    AdaptiveSpeechDetector,
    AdaptiveSpeechDetectorConfig,
)
from helpers.preroll_audio_buffer import PreRollAudioBuffer

CALIBRATION_DURATION_SECONDS = float(os.getenv("CALIBRATION_DURATION_SECONDS", 5.0))
LISTENING_SAMPLE_RATE = int(os.getenv("LISTENING_SAMPLE_RATE", 16000))
LISTENING_CHANNELS = int(os.getenv("LISTENING_CHANNELS", 2))
LISTENING_BLOCK_SIZE = int(os.getenv("LISTENING_BLOCK_SIZE", 1024))
MAX_RECORDING_DURATION_SECONDS = float(os.getenv("MAX_RECORDING_DURATION_SECONDS", 100.0))
SPEECH_START_TRIGGER_MS = float(os.getenv("SPEECH_START_TRIGGER_MS", 150.0))
SPEECH_PREROLL_MS = float(os.getenv("SPEECH_PREROLL_MS", 250.0))
SPEECH_START_RATIO = float(os.getenv("SPEECH_START_RATIO", 2.4))
SPEECH_END_RATIO = float(os.getenv("SPEECH_END_RATIO", 1.35))
SPEECH_START_MARGIN_RMS = float(os.getenv("SPEECH_START_MARGIN_RMS", 180.0))
SPEECH_END_MARGIN_RMS = float(os.getenv("SPEECH_END_MARGIN_RMS", 90.0))
STRONG_SPEECH_RATIO = float(os.getenv("STRONG_SPEECH_RATIO", 0.65))
STRONG_PEAK_RATIO = float(os.getenv("STRONG_PEAK_RATIO", 0.35))

def calibrate_ambient_noise(
    duration: float = CALIBRATION_DURATION_SECONDS,
    samplerate: int = LISTENING_SAMPLE_RATE,
    channels: int = LISTENING_CHANNELS,
    blocksize: int = LISTENING_BLOCK_SIZE,
) -> float:
    logging.info("Calibrating ambient noise level... ")
    stream = sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize)
    try:
        stream.start()
        energy_values = []
        logging.info("Try to be quiet...")
        start_time = time.time()
        while (time.time() - start_time) < duration:
            chunk, overflowed = stream.read(blocksize)
            if overflowed:
                logging.error("Warning: input overflow during calibration")
            mono = stereo_to_mono(chunk)
            energy = mono_to_rms16(mono)
            energy_values.append(energy)
            logging.info(f"Calibration RMS={energy:.1f}")
        ambient_noise_level = np.mean(energy_values)
        logging.info(f"Calibrated ambient noise level: {ambient_noise_level:.1f}")
        return ambient_noise_level
    finally:
        stream.stop()
        stream.close()


async def calibrate_ambient_noise_async(
    duration: float = CALIBRATION_DURATION_SECONDS,
    samplerate: int = LISTENING_SAMPLE_RATE,
    channels: int = LISTENING_CHANNELS,
    blocksize: int = LISTENING_BLOCK_SIZE,
) -> float:
    return await asyncio.to_thread(
        calibrate_ambient_noise,
        duration,
        samplerate,
        channels,
        blocksize,
    )

def mono_to_rms16(mono_chunk: np.ndarray) -> float:
    x = mono_chunk.astype(np.float32)
    return float(np.sqrt(np.mean(x**2))) 
# Square to make all amplitudes + -> mean to get avg energy of both channels -> √ to return to original scale. 

def stereo_to_mono(chunk: np.ndarray) -> np.ndarray:
    # If we have 2 dimensions, and the second dimension has 2 channels (columns of 2d array)
    if chunk.ndim == 2 and chunk.shape[1] == 2: 
        # Average of two channels, then convert to int16
        return chunk.mean(axis=1).astype(np.int16)
    # If audio is already mono 
    elif chunk.ndim == 2 and chunk.shape[1] == 1:
        return chunk[:, 0].astype(np.int16)
    else:
        return chunk.astype(np.int16).reshape(-1)

def seconds_to_frame_count(duration_seconds: float, frame_duration_seconds: float) -> int:
    return max(1, ceil(duration_seconds / frame_duration_seconds))


def build_detector_config(
    frame_duration_seconds: float,
    pause_threshold: float,
    initial_noise_floor: float,
) -> AdaptiveSpeechDetectorConfig:
    return AdaptiveSpeechDetectorConfig(
        frame_duration_seconds=frame_duration_seconds,
        initial_noise_floor=initial_noise_floor,
        start_ratio=SPEECH_START_RATIO,
        end_ratio=SPEECH_END_RATIO,
        min_start_margin=SPEECH_START_MARGIN_RMS,
        min_end_margin=SPEECH_END_MARGIN_RMS,
        start_trigger_frames=seconds_to_frame_count(
            SPEECH_START_TRIGGER_MS / 1000.0,
            frame_duration_seconds,
        ),
        end_trigger_frames=seconds_to_frame_count(
            pause_threshold,
            frame_duration_seconds,
        ),
        min_silence_duration_seconds=pause_threshold,
        strong_speech_ratio=STRONG_SPEECH_RATIO,
        strong_peak_ratio=STRONG_PEAK_RATIO,
    )


def record_until_silence(
    samplerate: int = LISTENING_SAMPLE_RATE,
    channels: int = LISTENING_CHANNELS,
    blocksize: int = LISTENING_BLOCK_SIZE,
    initial_noise_floor: float = 0.0,
    pause_threshold: float = 1.0,       # Seconds of silence before stop
    max_duration: float = MAX_RECORDING_DURATION_SECONDS,
    preroll_ms: float = SPEECH_PREROLL_MS,
):
    frames_mono = []
    t0 = time.time()
    frame_duration_seconds = blocksize / samplerate
    detector = AdaptiveSpeechDetector(
        build_detector_config(
            frame_duration_seconds=frame_duration_seconds,
            pause_threshold=pause_threshold,
            initial_noise_floor=initial_noise_floor,
        )
    )
    preroll_buffer = PreRollAudioBuffer.from_duration(
        duration_seconds=preroll_ms / 1000.0,
        samplerate=samplerate,
        blocksize=blocksize,
    )

    stream = sd.InputStream(
        samplerate=samplerate,
        channels=channels,
        dtype='int16',
        blocksize=blocksize
    )

    try:
        stream.start()
        logging.info("Listening... speak now")

        while True:
            # Read one chunk (blocking)
            chunk, overflowed = stream.read(blocksize)

            if overflowed:
                logging.error("Warning: input overflow)")

            # Take latest chunk of input, convert to mono, and compute energy. 
            mono = stereo_to_mono(chunk)
            energy = mono_to_rms16(mono)
            now = time.time()

            if not detector.speech_started:
                preroll_buffer.append(mono.copy())

            decision = detector.process_frame(energy=energy, now=now)
            logging.debug(
                "RMS=%.1f, floor=%.1f, speech_ema=%.1f, peak=%.1f, start=%.1f, end=%.1f, strong=%.1f",
                decision.energy,
                decision.noise_floor,
                decision.speech_ema,
                decision.speech_peak,
                decision.start_threshold,
                decision.end_threshold,
                decision.strong_threshold,
            )

            if decision.speech_started_now:
                frames_mono.extend(preroll_buffer.drain())
                logging.info(
                    "Speech started (noise_floor=%.1f, start_threshold=%.1f, end_threshold=%.1f)",
                    decision.noise_floor,
                    decision.start_threshold,
                    decision.end_threshold,
                )
            elif detector.speech_started:
                frames_mono.append(mono.copy())

            if decision.should_stop:
                logging.info(
                    "Adaptive silence threshold reached, stopping "
                    "(quiet_frames=%d, silence_since_strong=%.2fs, noise_floor=%.1f, speech_peak=%.1f)",
                    decision.quiet_frames,
                    decision.silence_since_strong_speech,
                    decision.noise_floor,
                    decision.speech_peak,
                )
                break

            if (now - t0) >= max_duration:
                logging.info("Max duration reached, stopping")
                break

        # Combine all chunks into one mono signal
        if not frames_mono:
            return None

        audio_mono = np.concatenate(frames_mono).astype(np.int16)

        # Encode to WAV bytes
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(samplerate)
            wf.writeframes(audio_mono.tobytes())

        wav_bytes = buf.getvalue()
        return wav_bytes

    finally:
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass


def listen_for_user_input(initial_noise_floor: float | None = None):
    wav_bytes = record_until_silence(
        samplerate=LISTENING_SAMPLE_RATE,
        channels=LISTENING_CHANNELS,
        blocksize=LISTENING_BLOCK_SIZE,
        initial_noise_floor=(
            initial_noise_floor
            if initial_noise_floor is not None
            else float(os.getenv("AMBIENT_NOISE_THRESHOLD", 700.0))
        ),
        pause_threshold=float(os.getenv("SPEECH_PAUSE_THRESHOLD", 1.0)),
        max_duration=MAX_RECORDING_DURATION_SECONDS,
    )
    if wav_bytes:
        return wav_bytes
