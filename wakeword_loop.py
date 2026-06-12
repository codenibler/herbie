import sounddevice as sd
import soundfile as sf
import pvporcupine
import logging
import time
import os
from threading import Event

WAKEWORD_PATH = os.getenv(
    "WAKEWORD_PATH",
    "herbie_wakewords/Hey-Herbie_en_raspberry-pi_v4_0_0.ppn",
)
WAKEWORD_LOG_INTERVAL_SECONDS = float(os.getenv("WAKEWORD_LOG_INTERVAL_SECONDS", 5.0))

def listen_for_wakeword(
    stop_event: Event | None = None,
    *,
    log_initialization: bool = True,
) -> bool:
    # Ensure porcupine access token is set
    ACCESS_TOKEN = os.getenv("WAKEWORD_ACCESS_TOKEN")    
    assert ACCESS_TOKEN, "WAKEWORD_ACCESS_TOKEN environment variable is not set. Missing in the .env file."

    # Log default microphone information
    if log_initialization:
        logging.info("Wake word loop initializing... Listening for 'Hey Herbie'")
        for idx, device in enumerate(sd.query_devices()):
            logging.debug(f"Device {idx}: {device['name']} (Input channels: {device['max_input_channels']}, Output channels: {device['max_output_channels']})")
            if idx == sd.default.device[0]:  # Check if this is the default input device
                logging.info(f"Default input device: {device['name']} (ID: {idx})")

    porcupine = pvporcupine.create(access_key=ACCESS_TOKEN, keyword_paths=[WAKEWORD_PATH])
    stream = sd.InputStream(
        samplerate=porcupine.sample_rate,
        channels=1,
        dtype='int16',
        blocksize=porcupine.frame_length,
    )

    try:
        stream.start()

        def get_next_audio_frame():
            audio_data, _ = stream.read(porcupine.frame_length)
            return audio_data.flatten()

        last_wakeword_not_detected_time = time.time()
        while stop_event is None or not stop_event.is_set():
            audio_frame = get_next_audio_frame()
            signal = porcupine.process(audio_frame)
            if signal >= 0:
                logging.debug("Wake word detected! Activating Herbie...")
                return True
            elif time.time() - last_wakeword_not_detected_time > WAKEWORD_LOG_INTERVAL_SECONDS:
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
        porcupine.delete()

    return False


def initialize_wakeword_loop():
    return listen_for_wakeword()
