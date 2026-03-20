import subprocess
import logging
import wave
import sys
import os

from helpers.audio_output import build_wav_playback_command, cleanup_temp_wav, prepend_silence_to_wav
from pathlib import Path
from dotenv import load_dotenv
from piper import PiperVoice, SynthesisConfig


load_dotenv(override=True)
voice_model_path = os.getenv("PIPER_VOICE_MODEL_PATH")
voice = PiperVoice.load(voice_model_path) 

def read_out_response(text: str):

    if text is None or len(text) == 0:
        return 

    RESPONSE_AUDIO_DIR = os.getenv("RESPONSE_AUDIO_DIR", "response_audio")

    out_wav = Path(RESPONSE_AUDIO_DIR) / f"{text[:20]}.wav"
    out_wav.parent.mkdir(parents=True, exist_ok=True)  

    logging.debug(f"Synthesizing response to {out_wav}...")

    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    padded_wav = prepend_silence_to_wav(out_wav)
    try:
        playback_command = build_wav_playback_command(padded_wav)
        logging.info(f"Playing audio via preferred USB Audio output: {' '.join(playback_command)}")
        subprocess.run(playback_command, check=False)
    finally:
        cleanup_temp_wav(padded_wav)



def read_out_response_from_file(file_path: str):
    padded_wav = prepend_silence_to_wav(file_path)
    try:
        playback_command = build_wav_playback_command(padded_wav)
        logging.info(f"Playing audio file via preferred USB Audio output: {' '.join(playback_command)}")
        subprocess.run(playback_command, check=False)
    finally:
        cleanup_temp_wav(padded_wav)


if __name__ == "__main__":
    read_out_response(sys.argv[1])
