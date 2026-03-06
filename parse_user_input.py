from pathlib import Path

import subprocess
import logging
import time
import io
import os

def parse_user_input(wav_bytes):

    WHISPER_PATH = Path(os.getenv("WHISPER_PATH", "whisper.cpp/build/bin/whisper-cli"))
    WHISPER_MODEL = Path(os.getenv("WHISPER_MODEL", "whisper.cpp/models/ggml-tiny.en.bin"))
    USER_INPUT_DIR = Path(os.getenv("USER_INPUT_DIR", "recorded_wavs"))

    if not os.path.exists(USER_INPUT_DIR):
        os.makedirs(USER_INPUT_DIR)
    
    # Save WAV to file for whisper.
    wav_path = USER_INPUT_DIR / f"user_input_{int(time.time())}.wav"
    with open(wav_path, "wb") as f:
        f.write(wav_bytes)
    logging.info(f"Saved user input WAV to {wav_path}")

    cmd = [
        str(WHISPER_PATH),
        "-m", str(WHISPER_MODEL),
        "-f", wav_path,
        "-nt",   # No timestamps
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        transcription = result.stdout.strip()
        logging.info(f"Transcription result: {transcription}")
        return transcription
    except subprocess.CalledProcessError as e:
        logging.error(f"Error during transcription: {e.stderr}")
        """ TO DO: ADD HERBIE ASKING FOR USER TO REPEAT WHAT THEY SAID """
        return None

