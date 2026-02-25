import logging
import subprocess
import wave
from piper import PiperVoice, SynthesisConfig

syn_config = SynthesisConfig(
    volume=1.0,
    length_scale=1.0,
    noise_scale=1.3,
    noise_w_scale=1.3,
    normalize_audio=False,
)

voice = PiperVoice.load("piper_voice_model/en_US-kusal-medium.onnx")  # load once

def read_out_response(text: str):
    out_wav = "test.wav"
    with wave.open(out_wav, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)

    logging.info("Playing audio via aplay...")
    subprocess.run(["aplay", "-q", out_wav], check=False)