import subprocess
import logging
import wave
import sys
import os

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

    logging.info("Playing audio via pipewire...")

    if os.getenv("USE_BLUETOOTH_SPEAKER") == True:
        subprocess.run(["pw-play", str(out_wav)], check=False)
    else:
        subprocess.run(["aplay", str(out_wav)], check=False)



def read_out_response_from_file(file_path: str):
    if os.getenv("USE_BLUETOOTH_SPEAKER") == True:
        subprocess.run(["pw-play", file_path], check=False)
    else:
        subprocess.run(["aplay", file_path], check=False)


if __name__ == "__main__":
    read_out_response(sys.argv[1])