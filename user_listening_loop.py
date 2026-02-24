import sounddevice as sd
import numpy as np
import logging
import time
import wave
import io
import os

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
    samplerate: int = 16000,
    channels: int = 2,          # ReSpeaker hw endpoint requires 2
    blocksize: int = 1024,
    energy_threshold: float = 0,        # Set as env param 
    pause_threshold: float = 1.0,       # Seconds of silence before stop
    max_duration: float = 100.0         # Max cap
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
        samplerate=16000,
        channels=2,
        blocksize=1024,
        energy_threshold=float(os.getenv("AMBIENT_NOISE_THRESHOLD", 700.0)),  # tune this
        pause_threshold=float(os.getenv("SPEECH_PAUSE_THRESHOLD", 1.0)),     # seconds of silence to stop
    )
    if wav_bytes:
        return wav_bytes