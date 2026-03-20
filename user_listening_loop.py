import sounddevice as sd
import numpy as np
import logging
import asyncio
import time
import wave
import io
import os

CALIBRATION_DURATION_SECONDS = float(os.getenv("CALIBRATION_DURATION_SECONDS", 5.0))
LISTENING_SAMPLE_RATE = int(os.getenv("LISTENING_SAMPLE_RATE", 16000))
LISTENING_CHANNELS = int(os.getenv("LISTENING_CHANNELS", 2))
LISTENING_BLOCK_SIZE = int(os.getenv("LISTENING_BLOCK_SIZE", 1024))
MAX_RECORDING_DURATION_SECONDS = float(os.getenv("MAX_RECORDING_DURATION_SECONDS", 100.0))

""" Recalibrates ambient noise to set silence threshold to finish user input recording """
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
        logging.info("Listening... speak now")
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

"""Compute RMS energy for a chunk of Mono audio"""
def mono_to_rms16(mono_chunk: np.ndarray) -> float:
    x = mono_chunk.astype(np.float32)
    return float(np.sqrt(np.mean(x**2))) 
# Square to make all amplitudes + -> mean to get avg energy of both channels -> √ to return to original scale. 

def stereo_to_mono(chunk: np.ndarray) -> np.ndarray:
    """chunk shape: (frames, channels) -> mono int16 shape: (frames,)"""
    # If we have 2 dimensions, and the second dimension has 2 channels (columns of 2d array)
    if chunk.ndim == 2 and chunk.shape[1] == 2: 
        # Average of two channels, then convert to int16
        return chunk.mean(axis=1).astype(np.int16)
    # If audio is already mono 
    elif chunk.ndim == 2 and chunk.shape[1] == 1:
        return chunk[:, 0].astype(np.int16)
    else:
        return chunk.astype(np.int16).reshape(-1)

""" TO DO: COMPUTE BACKGROUND ENERGY LEVEL NOT HARDCODED VALUE """
def record_until_silence(
    samplerate: int = LISTENING_SAMPLE_RATE,
    channels: int = LISTENING_CHANNELS,
    blocksize: int = LISTENING_BLOCK_SIZE,
    energy_threshold: float = 0,        # Set as env param 
    pause_threshold: float = 1.0,       # Seconds of silence before stop
    max_duration: float = MAX_RECORDING_DURATION_SECONDS
):
    """
    Record from mic until silence exceeds pause_threshold seconds.
    Returns WAV bytes (mono, 16kHz, int16).
    """
    frames_mono = []
    speech_started = False
    silence_start = None
    t0 = time.time()

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
            frames_mono.append(mono.copy())

            energy = mono_to_rms16(mono)
            now = time.time()


            above_silence = energy >= energy_threshold
            logging.debug(f"RMS={energy:.1f}, Above Silence? {above_silence}")

            if above_silence:
                if not speech_started:
                    speech_started = True
                    logging.info("Speech started")
                silence_start = None
            else: # Silent
                if speech_started:
                    if silence_start is None:
                        silence_start = now
                    elif (now - silence_start) >= pause_threshold:
                        logging.info("Silence threshold reached, stopping")
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
        # Explicit cleanup (good for learning)
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass


def listen_for_user_input():
    wav_bytes = record_until_silence(
        samplerate=LISTENING_SAMPLE_RATE,
        channels=LISTENING_CHANNELS,
        blocksize=LISTENING_BLOCK_SIZE,
        energy_threshold=float(os.getenv("AMBIENT_NOISE_THRESHOLD", 700.0)),  # tune this
        pause_threshold=float(os.getenv("SPEECH_PAUSE_THRESHOLD", 1.0)),     # seconds of silence to stop
        max_duration=MAX_RECORDING_DURATION_SECONDS,
    )
    if wav_bytes:
        return wav_bytes
