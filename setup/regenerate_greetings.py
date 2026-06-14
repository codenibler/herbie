from __future__ import annotations

from pathlib import Path
import os
import wave

from dotenv import load_dotenv
from piper import PiperVoice, SynthesisConfig


load_dotenv(override=True)

PRERECORDED_RESPONSE_TEXTS = {
    "greetings": {
        "good_to_hear_you.wav": "Good to hear you. What is on your mind?",
        "hello_there.wav": "Hello there, what can I help you with?",
        "lets_dig_in.wav": "Let us dig in. What do you need?",
        "mentor_mode.wav": "Mentor mode engaged. Hit me with your question.",
        "ready_when_you_are.wav": "Ready when you are. What are we figuring out today?",
        "strange_thing_today.wav": "What delightfully strange thing are we tackling today?",
        "welcome_back.wav": "Welcome back. What are we exploring this time?",
    },
    "ack_tool/portfolio": {
        "on_it_from_herbie.wav": "On it from Herbie.",
    },
}


def _get_optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return float(value)


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_effective_length_scale() -> float | None:
    base_length_scale = _get_optional_float_env("PIPER_LENGTH_SCALE")
    speech_speed = _get_optional_float_env("PIPER_SPEECH_SPEED")

    if speech_speed is not None and speech_speed <= 0:
        raise ValueError("PIPER_SPEECH_SPEED must be greater than zero.")

    if base_length_scale is not None and base_length_scale <= 0:
        raise ValueError("PIPER_LENGTH_SCALE must be greater than zero.")

    if speech_speed is None:
        return base_length_scale

    effective_base = 1.0 if base_length_scale is None else base_length_scale
    return effective_base / speech_speed


def build_synthesis_config() -> SynthesisConfig:
    return SynthesisConfig(
        length_scale=_get_effective_length_scale(),
        noise_scale=_get_optional_float_env("PIPER_NOISE_SCALE"),
        noise_w_scale=_get_optional_float_env("PIPER_NOISE_W_SCALE"),
        normalize_audio=_get_bool_env("PIPER_NORMALIZE_AUDIO", True),
        volume=float(os.getenv("PIPER_VOLUME", "1.0")),
    )


def main() -> None:
    voice_model_path = os.getenv("PIPER_VOICE_MODEL_PATH")
    if not voice_model_path:
        raise RuntimeError("PIPER_VOICE_MODEL_PATH is not set.")

    voice = PiperVoice.load(voice_model_path)
    synthesis_config = build_synthesis_config()

    base_responses_dir = Path("herbie_responses")
    greetings_dir = Path(
        os.getenv("GREETING_RESPONSES_DIR", str(base_responses_dir / "greetings"))
    )

    response_dirs = {
        "greetings": greetings_dir,
        "ack_tool/portfolio": base_responses_dir / "ack_tool" / "portfolio",
    }

    for relative_dir, responses in PRERECORDED_RESPONSE_TEXTS.items():
        target_dir = response_dirs[relative_dir]
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename, text in responses.items():
            output_path = target_dir / filename
            with wave.open(str(output_path), "wb") as wav_file:
                voice.synthesize_wav(text, wav_file, syn_config=synthesis_config)
            print(f"Regenerated {output_path}")


if __name__ == "__main__":
    main()
