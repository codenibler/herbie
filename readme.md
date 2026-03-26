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
- The old `d04171` note is not enough by itself. Herbie imports the `rpi_ws281x` Python package from the active virtualenv, not directly from the vendored `rpi_ws281x/` source tree in this repo.
- On Raspberry Pi 5, the stock `rpi_ws281x==5.0.0` wheel still fails with `ws2811_init failed with code -3 (Hardware revision is not supported)`. Pi 5 support currently depends on the Pi 5-capable Python build plus the RP1 kernel module / device-tree-overlay path described upstream.
- Upstream references:
  - Python release: `pi5-beta2` in `rpi-ws281x/rpi-ws281x-python`
  - Pi 5 setup guide: `jgarff/rpi_ws281x` wiki page `Raspberry-Pi-5-Support`

For this project, the working Pi 5 setup was:

```bash
# 1) install a Pi 5-capable Python binding into the venv
#    (the normal 5.0.0 wheel is not enough on Pi 5, and the prebuilt
#    pi5-beta wheel may not match your local Python version)
git clone --depth 1 --branch pi5-beta2 https://github.com/rpi-ws281x/rpi-ws281x-python.git /tmp/rpi-ws281x-python
mkdir -p /tmp/rpi-ws281x-python/library/lib
cp -a rpi_ws281x/. /tmp/rpi-ws281x-python/library/lib/
venv/bin/pip install --force-reinstall /tmp/rpi-ws281x-python/library

# 2) build the RP1 kernel module + overlay from the vendored C sources
cd rpi_ws281x/rp1_ws281x_pwm
make
./dts.sh

# 3) load them for the current boot/session
sudo insmod ./rp1_ws281x_pwm.ko pwm_channel=2
sudo dtoverlay -d . rp1_ws281x_pwm
sudo pinctrl set 18 a3 pn

# 4) allow the normal Herbie user to access the device node
sudo chgrp gpio /dev/ws281x_pwm
sudo chmod 660 /dev/ws281x_pwm
```

Pi 5-specific notes:
- `GPIO18` maps to `PWM0_CHAN2` on Pi 5, which is why the upstream guide uses `pwm_channel=2` with `pinctrl set 18 a3 pn`.
- The `/dev/ws281x_pwm` permission change above is not persistent across reboot or overlay reload unless you add a udev rule or equivalent boot-time setup.
- If you still see LED init failures, check four things in this order: imported `rpi_ws281x` package version, `/dev/ws281x_pwm` existence, `/dev/ws281x_pwm` permissions, and whether `pinctrl get 18` reports `GPIO18 = PWM0_CHAN2`.

Quick reboot protocol:
1. Run `setup/enable_pi5_led_runtime.sh`
2. Make sure it prints `start_result=True`
3. If you want to double-check manually, run `ls -l /dev/ws281x_pwm` and `pinctrl get 18`
4. Start Herbie normally with `source venv/bin/activate` and `python3 main.py`
