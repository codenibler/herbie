import sounddevice as sd
import numpy as np
import sherpa_onnx
import logging
import time
import os
from pathlib import Path
from threading import Event

PROJECT_DIR = Path(__file__).resolve().parent
WAKEWORD_PHRASE = "Hey Herbie"
WAKEWORD_MODEL_DIR = Path(os.getenv("WAKEWORD_MODEL_DIR", "herbie_wakewords"))
if not WAKEWORD_MODEL_DIR.is_absolute():
    WAKEWORD_MODEL_DIR = PROJECT_DIR / WAKEWORD_MODEL_DIR

WAKEWORD_ENCODER_PATH = (
    WAKEWORD_MODEL_DIR / "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx"
)
WAKEWORD_DECODER_PATH = (
    WAKEWORD_MODEL_DIR / "decoder-epoch-13-avg-2-chunk-16-left-64.onnx"
)
WAKEWORD_JOINER_PATH = (
    WAKEWORD_MODEL_DIR / "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx"
)
WAKEWORD_TOKENS_PATH = WAKEWORD_MODEL_DIR / "tokens.txt"
WAKEWORD_KEYWORDS_PATH = WAKEWORD_MODEL_DIR / "keywords.txt"
WAKEWORD_SCORE = float(os.getenv("WAKEWORD_SCORE", 1.0))
WAKEWORD_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", 0.25))
WAKEWORD_NUM_THREADS = int(os.getenv("WAKEWORD_NUM_THREADS", 2))
WAKEWORD_SAMPLE_RATE = int(os.getenv("WAKEWORD_SAMPLE_RATE", 16000))
WAKEWORD_BLOCK_SIZE = int(os.getenv("WAKEWORD_BLOCK_SIZE", 2048))
WAKEWORD_LOG_INTERVAL_SECONDS = float(
    os.getenv("WAKEWORD_LOG_INTERVAL_SECONDS", 5.0)
)
_WAKEWORD_SPOTTER = None


class WakewordInitializationError(RuntimeError):
    """Raised when Herbie cannot start its sherpa-onnx wake-word engine."""


def _get_wakeword_spotter():
    global _WAKEWORD_SPOTTER
    if _WAKEWORD_SPOTTER is not None:
        return _WAKEWORD_SPOTTER

    model_paths = (
        WAKEWORD_ENCODER_PATH,
        WAKEWORD_DECODER_PATH,
        WAKEWORD_JOINER_PATH,
        WAKEWORD_TOKENS_PATH,
        WAKEWORD_KEYWORDS_PATH,
    )
    missing_paths = [str(path) for path in model_paths if not path.is_file()]
    if missing_paths:
        raise WakewordInitializationError(
            f"Missing sherpa-onnx wake-word model file: {missing_paths[0]}"
        )

    try:
        _WAKEWORD_SPOTTER = sherpa_onnx.KeywordSpotter(
            tokens=str(WAKEWORD_TOKENS_PATH),
            encoder=str(WAKEWORD_ENCODER_PATH),
            decoder=str(WAKEWORD_DECODER_PATH),
            joiner=str(WAKEWORD_JOINER_PATH),
            keywords_file=str(WAKEWORD_KEYWORDS_PATH),
            num_threads=WAKEWORD_NUM_THREADS,
            sample_rate=WAKEWORD_SAMPLE_RATE,
            keywords_score=WAKEWORD_SCORE,
            keywords_threshold=WAKEWORD_THRESHOLD,
            provider="cpu",
        )
    except Exception as error:
        raise WakewordInitializationError(
            f"Unable to initialize sherpa-onnx: {error}"
        ) from error

    return _WAKEWORD_SPOTTER


def listen_for_wakeword(
    stop_event: Event | None = None,
    *,
    log_initialization: bool = True,
) -> bool:
    if not 0 < WAKEWORD_THRESHOLD < 1:
        raise WakewordInitializationError(
            "WAKEWORD_THRESHOLD must be between zero and one."
        )
    if WAKEWORD_SCORE <= 0:
        raise WakewordInitializationError(
            "WAKEWORD_SCORE must be greater than zero."
        )

    # Log default microphone information
    if log_initialization:
        logging.info(
            "Wake word loop initializing... Listening for '%s'",
            WAKEWORD_PHRASE,
        )
        for idx, device in enumerate(sd.query_devices()):
            logging.debug(f"Device {idx}: {device['name']} (Input channels: {device['max_input_channels']}, Output channels: {device['max_output_channels']})")
            if idx == sd.default.device[0]:  # Check if this is the default input device
                logging.info(f"Default input device: {device['name']} (ID: {idx})")

    spotter = _get_wakeword_spotter()
    wakeword_stream = spotter.create_stream()

    stream = sd.InputStream(
        samplerate=WAKEWORD_SAMPLE_RATE,
        channels=1,
        dtype='int16',
        blocksize=WAKEWORD_BLOCK_SIZE,
    )

    try:
        stream.start()

        last_wakeword_not_detected_time = time.time()
        while stop_event is None or not stop_event.is_set():
            audio_data, overflowed = stream.read(WAKEWORD_BLOCK_SIZE)
            if overflowed:
                logging.warning("Wake-word microphone input overflowed.")

            samples = audio_data.reshape(-1).astype(np.float32) / 32768.0
            wakeword_stream.accept_waveform(WAKEWORD_SAMPLE_RATE, samples)

            while spotter.is_ready(wakeword_stream):
                spotter.decode_stream(wakeword_stream)
                detected_keyword = spotter.get_result(wakeword_stream)
                if detected_keyword:
                    spotter.reset_stream(wakeword_stream)
                    logging.debug(
                        "Wake word detected (%s)! Activating Herbie...",
                        detected_keyword,
                    )
                    return True

            if (
                time.time() - last_wakeword_not_detected_time
                > WAKEWORD_LOG_INTERVAL_SECONDS
            ):
                logging.debug("No wake word detected in this frame.")
                last_wakeword_not_detected_time = time.time()
    finally:
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    return False


def initialize_wakeword_loop():
    return listen_for_wakeword()
