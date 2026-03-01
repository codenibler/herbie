import sounddevice as sd 
import logging
import os 

def setup_default_microphone():
    """Sets the default microphone to the one specified in the .env file."""   
    mic_name = os.getenv("MICROPHONE_NAME")
    if not mic_name:
        raise ValueError("MICROPHONE_NAME not set in .env file.")
    
    devices = sd.query_devices()
    logging.debug(f"Available audio devices: {[device['name'] for device in devices]}")
    for idx, device in enumerate(devices):
        if mic_name in device['name'] and device['max_input_channels'] > 0:
            sd.default.device = idx
            logging.info(f"Default microphone set to: {mic_name} (Device Index: {idx})")
            return
    
    raise ValueError(f"Microphone '{mic_name}' not found or has no input channels.")