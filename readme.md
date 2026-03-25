# Quick setup

Install Python dependencies, add models, and populate `.env` from `dotenvstructure.txt`.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Piper TTS voice model:
```bash 
python3 -m piper.download_voices en_US-lessac-medium
```
- Place ONNX file in `piper_voice_model/` and set `PIPER_VOICE_MODEL_PATH` in `.env`.

Whisper (whisper.cpp):
```bash
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
sh ./models/download-ggml-model.sh base.en
cmake -B build
cmake --build build -j --config Release
# set WHISPER_PATH in .env to the built binary (e.g. ./main/whisper or whisper-cli)
```

.env setup:
```bash
cp dotenvstructure.txt .env
# edit .env and fill sensitive values: WAKEWORD_ACCESS_TOKEN, MICROPHONE_NAME,
# OLLAMA_MODEL_NAME, bulb IPs, etc.
```

## Hardware setup

Herbie is currently set up like a Raspberry Pi build with a USB microphone/speaker path, a GPIO buzzer, a WS281x LED strip, and WiZ bulbs on the local network. Pin numbers below are given as `BCM GPIO` and Raspberry Pi physical header pins.

| Part | Code default / env var | Physical setup |
| --- | --- | --- |
| WS281x LED strip | `LED_PIN=18`, `LED_COUNT=80`, `LED_CHANNEL=0`, `LED_STRIP_TYPE=WS2811_STRIP_GRB` | Connect the strip data input to `GPIO18` (physical pin `12`). Power the strip from a suitable `5V` supply, and tie LED ground to both PSU ground and a Raspberry Pi `GND` pin so the data line has a common ground reference. |
| Buzzer | `BUZZER_PIN=2` | Connect the buzzer signal lead to `GPIO2` (physical pin `3`) and the other lead to `GND`. This code uses `gpiozero.Buzzer`, so it expects a simple on/off buzzer input. |
| Microphone | `MICROPHONE_NAME` | No GPIO wiring is used in code. The current local `.env` expects a device name containing `ReSpeaker`, so plug in the mic and verify `sounddevice` can see it. |
| Speaker / amp | `PREFERRED_WAV_OUTPUT_DEVICE=plughw:CARD=Audio,DEV=0` | No GPIO wiring is used in code. Playback is sent through ALSA to a device named `Audio`, which is typically a USB audio dongle / USB speaker path. |
| WiZ bulbs | `KITCHEN_BULB_IP`, `BULB1_IP`, `BULB2_IP`, `BULB3_IP` | These are LAN devices, not GPIO devices. Put the bulbs on the same network as the Pi and reserve static/DHCP-stable IPs so the addresses in `.env` do not drift. |
| Optional Bluetooth speaker | `USE_BLUETOOTH_SPEAKER`, `BLUETOOTH_ADDRESS_SOUNDCORE`, `SOUNDCORE_SPEAKER_NAME` | Optional wireless output path. `main.py` uses the helper to connect/trust the speaker with `bluetoothctl`; running the helper directly also tries to switch the PipeWire sink with `wpctl`. |

Recommended LED strip wiring notes:
- `GPIO18` is the active LED data pin in the code, so wire the strip's `DIN`/`DI` pad there unless you also change `LED_PIN`.
- A WS281x strip should not be powered from the Pi GPIO data pin. Use a proper `5V` supply sized for your strip and keep grounds common.
- A 3.3V-to-5V logic level shifter on the LED data line is recommended for reliability.
- The LED test script in [led_tests/test.py](led_tests/test.py) uses the same defaults as the main app: `80` pixels on `GPIO18`.

Useful `.env` values for the hardware build that are currently only implied by code:

```dotenv
# WS281x LED strip
LED_STRIP_ENABLED=true
LED_COUNT=80
LED_PIN=18
LED_FREQ_HZ=800000
LED_DMA=10
LED_BRIGHTNESS=80
LED_INVERT=false
LED_CHANNEL=0
LED_STRIP_TYPE=WS2811_STRIP_GRB
```

Hardware-specific setup notes:
- `GPIO2` / physical pin `3` is also the Pi's `SDA1` pin. If you plan to use I2C hardware on this build, move the buzzer to a different GPIO and update `BUZZER_PIN`.
- Wake word detection always opens the microphone as a mono `sounddevice.InputStream`; the speech recorder defaults to `LISTENING_CHANNELS=2`. If your microphone is mono-only, set `LISTENING_CHANNELS=1`.
- Some lighting functions currently look for `KBULB_IP` while others use `KITCHEN_BULB_IP`. If you use the full lighting feature set before that is unified, set both env vars to the same kitchen bulb IP in your local `.env`.
- For quick hardware validation, use [list_sounddevice_devices.py](list_sounddevice_devices.py) to find the microphone name and [led_tests/test.py](led_tests/test.py) to smoke-test the LED strip.

Run:
```bash
source venv/bin/activate
python3 main.py
```

Local note for WS281x LED testing on Raspberry Pi 5:
- This repo includes a local `rpi_ws281x` patch for Raspberry Pi 5 Model B Rev 1.1 boards reporting revision `d04171`, which otherwise fail with `ws2811_init failed with code -3 (Hardware revision is not supported)`.
- Upstream reference: issue `#555` and PR `#556` in `jgarff/rpi_ws281x`.
