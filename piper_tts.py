import subprocess
import logging
import wave
import sys
import os

from pathlib import Path
from piper import PiperVoice, SynthesisConfig

syn_config = SynthesisConfig(
    volume=1.0,
    length_scale=1.0,
    noise_scale=1.3,
    noise_w_scale=1.3,
    normalize_audio=False,
)

voice_model_path = os.getenv("PIPER_VOICE_MODEL_PATH", "piper_voice_model/en_US-lessac-medium.onnx")
voice = PiperVoice.load(voice_model_path) 

def read_out_response(text: str):

    RESPONSE_AUDIO_DIR = os.getenv("RESPONSE_AUDIO_DIR", "response_audio")
    out_wav = Path(RESPONSE_AUDIO_DIR) / f"{text}.wav"
    out_wav.parent.mkdir(parents=True, exist_ok=True)  

    logging.debug(f"Synthesizing response to {out_wav}...")

    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)

    logging.info("Playing audio via aplay...")
    subprocess.run(["aplay", "-q", str(out_wav)], check=False)


def read_out_response_from_file(file_path: str):
    subprocess.run(["aplay", "-q", file_path], check=False)


if __name__ == "__main__":
    read_out_response(sys.argv[1])