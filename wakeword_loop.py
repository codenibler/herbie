import sounddevice as sd
import soundfile as sf
import pvporcupine
import logging
import os


def initialize_wakeword_loop():
    # Ensure porcupine access token is set
    ACCESS_TOKEN = os.getenv("WAKEWORD_ACCESS_TOKEN")    
    assert ACCESS_TOKEN, "WAKEWORD_ACCESS_TOKEN environment variable is not set. Missing in the .env file."

    # Log default microphone information
    logging.info("Wake word loop initializing... Listening for 'Hey Herbie'")
    for idx, device in enumerate(sd.query_devices()):
        logging.debug(f"Device {idx}: {device['name']} (Input channels: {device['max_input_channels']}, Output channels: {device['max_output_channels']})")
        if idx == sd.default.device[0]:  # Check if this is the default input device
            logging.info(f"Default input device: {device['name']} (ID: {idx})")

    # Initialize Porcupine wake word detection
    porcupine = pvporcupine.create(access_key=ACCESS_TOKEN, keyword_paths=['herbie_wakewords/Hey-Herbie_en_raspberry-pi_v4_0_0.ppn'])

    # Initialize audio stream which model checks for wake word. 
    stream = sd.InputStream(samplerate=porcupine.sample_rate,
                        channels=1,
                        dtype='int16',
                        blocksize=porcupine.frame_length)
    stream.start()

    def get_next_audio_frame():
        # Read audio data from the microphone
        audio_data, _ = stream.read(porcupine.frame_length)
        return audio_data.flatten()
    
    while True:
        audio_frame = get_next_audio_frame()
        signal = porcupine.process(audio_frame)
        if signal >= 0:
            logging.debug("Wake word detected! Activating Herbie...")      
            # End stream waiting for wakeword
            stream.stop()
            stream.close()
            return True
        else:
            logging.debug("No wake word detected in this frame.")   
            # Here, if triggered, we move to listening to user and processing audio. 
