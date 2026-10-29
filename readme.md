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
- `PIPER_SPEECH_SPEED` controls speech-rate as a multiplier, so `1.35` means roughly 1.35x normal speaking speed.

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
# edit .env and fill sensitive values: MICROPHONE_NAME, GROQ_API_KEY,
# optional GROQ_MODEL_NAME, bulb IPs, and optional CALENDAR_CLIENT_ID /
# CALENDAR_CLIENT_SECRET for Google Calendar access.
```

Sherpa-onnx wake-word detection:
- Herbie listens for `Hey Herbie` entirely offline. No account or access token
  is required. The repository includes the quantized sherpa-onnx 3M
  English-capable model and its `HEY_HERBIE` keyword definition under
  `herbie_wakewords/`.
- `WAKEWORD_SCORE` boosts the keyword path during decoding (sherpa-onnx default
  `1.0`; Herbie ships `4.0`). `WAKEWORD_THRESHOLD` is the detection confidence
  cutoff (sherpa-onnx default `0.25`; Herbie ships `0.06`). Raise the threshold or
  lower the score if you get false triggers; do the opposite if you have to shout.
  Tune both against recordings made in the room where Herbie runs.
- `WAKEWORD_SAMPLE_RATE=16000` matches the bundled US English acoustic model.
  `WAKEWORD_BLOCK_SIZE=2048` controls how many mono `int16` samples are read
  from the microphone at a time.
- Sherpa-onnx was selected because it is Apache-2.0 licensed, provides current
  Python 3.13 ARM64 wheels, runs locally on Raspberry Pi, and supports arbitrary
  keywords without retraining. openWakeWord is a strong neural alternative but
  needs a separately trained model to retain the custom phrase. PocketSphinx is
  lightweight and supports arbitrary phrases, but it failed the project's
  synthetic `Hey Herbie` detection check.
- Upstream references:
  - sherpa-onnx keyword spotting: https://k2-fsa.github.io/sherpa/onnx/kws/
  - sherpa-onnx Python package: https://pypi.org/project/sherpa-onnx/
  - openWakeWord: https://github.com/dscripka/openWakeWord
  - PocketSphinx: https://pypi.org/project/pocketsphinx/

Groq inference:
- Herbie uses the Groq API for language-model responses.
- `GROQ_API_KEY` is required in `.env`.
- `GROQ_MODEL_NAME` is optional and defaults to `openai/gpt-oss-20b`. The earlier defaults
  (`meta-llama/llama-4-scout-17b-16e-instruct`, `qwen/qwen3.6-27b`) were shut down by Groq in 2026.
  `openai/gpt-oss-120b` is a drop-in alternative at the same price and about half the speed.
- `GROQ_REASONING_EFFORT` is optional and defaults to `low` to keep voice responses snappy;
  `medium` or `high` trades latency for more careful tool-argument extraction.
- `WEATHER_LOCATION` controls which place Herbie uses for weather analysis and defaults to `Amsterdam`.
- Google Calendar support is read-only. To enable calendar event lookups and schedule analysis, set `CALENDAR_CLIENT_ID` and `CALENDAR_CLIENT_SECRET` in `.env` and let Herbie complete the one-time OAuth flow the first time a calendar tool runs.
- On a headless Raspberry Pi, Google Calendar auth is configured for SSH tunneling by default: `CALENDAR_AUTH_HOST=localhost`, `CALENDAR_AUTH_PORT=8080`, `CALENDAR_AUTH_OPEN_BROWSER=false`.

Headless Google Calendar auth:
```bash
ssh -L 8080:localhost:8080 <pi-host>
source venv/bin/activate
python3 main.py
```
- When Herbie prints the Google auth URL, open it in a browser on your local machine. The callback to `localhost:8080` will traverse the SSH tunnel back to the Pi and create `toolbox/gcalendar_tokens.json`.

## Tool selection

Herbie sends every transcribed request to the model together with the full tool list
(all entries in `TOOL_MAP` in `groq_model.py`) and lets the model decide whether a tool
fits. There is no keyword pre-routing. Guidance that used to be injected per keyword
(valid light colors, the live list of song files, calendar periods, timer unit
conversion, kitchen vs station lights) now lives in the tool schemas and in
`TOOL_GUIDANCE`, which is appended to the system prompt along with the current local
date and time.

To add a tool: register the function in `TOOL_MAP`, write a one-line entry in
`TOOL_DESCRIPTIONS`, and add any parameter enums or bounds to `TOOL_PARAMETER_METADATA`.
Type annotations on the function drive the JSON schema types.

Local non-model shortcuts (the only remaining text matching):
- Time responses are handled locally for `what time is it`, `what's the time`, `tell me the time`, and `current time`.
- A bare `stop` while background audio is playing stops it immediately without a model round-trip.

## Bluetooth speaker (Soundcore Motion Boom)

Herbie plays through a Bluetooth speaker via PulseAudio, and keeps the speaker awake
with a permanent, inaudible keepalive stream so it never auto-powers off.

One-time setup on the Pi:
```bash
sudo apt-get install -y --no-install-recommends pulseaudio-module-bluetooth
systemctl --user restart pulseaudio.service
# put the speaker in pairing mode, then (replace the MAC):
bluetoothctl scan on   # note the speaker's address, then in the same session:
bluetoothctl pair AA:BB:CC:DD:EE:FF && bluetoothctl trust AA:BB:CC:DD:EE:FF && bluetoothctl connect AA:BB:CC:DD:EE:FF
loginctl enable-linger $USER          # user services run without a login session
```

`/etc/bluetooth/main.conf` is set to reconnect to the speaker automatically after link
loss (`[Policy] ReconnectUUIDs=0000110b-...` is the A2DP Sink UUID, with
`ReconnectAttempts=7` and backoff `ReconnectIntervals=1,2,4,8,16,32,64`), plus
`AutoEnable=true` and `FastConnectable=true`. A backup of the original is at
`/etc/bluetooth/main.conf.bak-herbie`.

`.env` values:
- `PREFERRED_WAV_OUTPUT_DEVICE=pulse` routes all of Herbie's `aplay` output through the
  PulseAudio default sink; volume control then uses `pactl` on that sink.
- `USE_BLUETOOTH_SPEAKER=true`, `BLUETOOTH_ADDRESS_SOUNDCORE=<MAC>`, `SOUNDCORE_SPEAKER_NAME`.
- `SPEAKER_KEEPALIVE_AMPLITUDE=4` is the peak sample value of the dither (16-bit scale,
  about -78 dBFS). `1` is the minimum non-zero signal.

Keepalive service:
```bash
setup/install_speaker_keepalive.sh      # installs + enables herbie-speaker-keepalive (systemd --user)
systemctl --user status herbie-speaker-keepalive.service
journalctl --user -u herbie-speaker-keepalive.service -f
```
`setup/speaker_keepalive.py` loops forever: reconnects the speaker if it drops, waits for
its `bluez_sink.<MAC>.a2dp_sink`, sets it as the PulseAudio default sink, then streams
random +/-amplitude dither to it through `pacat`. Because a stream is always playing,
PulseAudio never suspends the sink, the A2DP transport stays open, and the speaker never
sees the idle condition that triggers its auto power-off.

To go back to the USB speaker, set `PREFERRED_WAV_OUTPUT_DEVICE=plughw:CARD=Audio,DEV=0`,
`USE_BLUETOOTH_SPEAKER=false`, and `systemctl --user disable --now herbie-speaker-keepalive`.

## Hardware setup

Herbie is currently set up like a Raspberry Pi build with a USB microphone/speaker path, a WS281x LED strip, and WiZ bulbs on the local network. Pin numbers below are given as `BCM GPIO` and Raspberry Pi physical header pins.

| Part | Code default / env var | Physical setup |
| --- | --- | --- |
| WS281x LED strip | `LED_PIN=13`, `PIXEL_COUNT=80`, `LED_CHANNEL=0`, `LED_STRIP_TYPE=WS2811_STRIP_GRB` | Connect the strip data input to `GPIO13` (physical pin `33`). Power the strip from a suitable `5V` supply, and tie LED ground to both PSU ground and a Raspberry Pi `GND` pin so the data line has a common ground reference. |
| Microphone | `MICROPHONE_NAME` | No GPIO wiring is used in code. The current local `.env` expects a device name containing `ReSpeaker`, so plug in the mic and verify `sounddevice` can see it. |
| Speaker / amp | `PREFERRED_WAV_OUTPUT_DEVICE=plughw:CARD=Audio,DEV=0` | No GPIO wiring is used in code. Playback is sent through ALSA to a device named `Audio`, which is typically a USB audio dongle / USB speaker path. |
| WiZ bulbs | `KITCHEN_BULB_IP`, `BULB1_IP`, `BULB2_IP`, `BULB3_IP` | These are LAN devices, not GPIO devices. Put the bulbs on the same network as the Pi and reserve static/DHCP-stable IPs so the addresses in `.env` do not drift. |
| Bluetooth speaker | `USE_BLUETOOTH_SPEAKER`, `BLUETOOTH_ADDRESS_SOUNDCORE`, `SOUNDCORE_SPEAKER_NAME` | Wireless output path through PulseAudio (see the Bluetooth speaker section). `main.py` connects/trusts the speaker with `bluetoothctl` and sets the PulseAudio default sink with `pactl`; the keepalive user service does the same continuously. |

Recommended LED strip wiring notes:
- `GPIO13` is the active LED data pin in the code, so wire the strip's `DIN`/`DI` pad there unless you also change `LED_PIN`.
- A WS281x strip should not be powered from the Pi GPIO data pin. Use a proper `5V` supply sized for your strip and keep grounds common.
- A 3.3V-to-5V logic level shifter on the LED data line is recommended for reliability.
- The LED test script in [led_tests/test.py](led_tests/test.py) uses the same defaults as the main app: `80` pixels on `GPIO13`.

Useful `.env` values for the hardware build that are currently only implied by code:

```dotenv
# WS281x LED strip
LED_STRIP_ENABLED=true
PIXEL_COUNT=80
LED_PIN=13
LED_FREQ_HZ=800000
LED_DMA=10
LED_BRIGHTNESS=80
LED_INVERT=false
LED_CHANNEL=0
LED_STRIP_TYPE=WS2811_STRIP_GRB
```

Hardware-specific setup notes:
- Wake word detection opens the microphone as a 16 kHz mono `sounddevice.InputStream`; the speech recorder defaults to `LISTENING_CHANNELS=2`. If your microphone is mono-only, set `LISTENING_CHANNELS=1`.
- Kitchen lighting uses `KITCHEN_BULB_IP` for the kitchen bulb IP in your local `.env`.
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
sudo insmod ./rp1_ws281x_pwm.ko pwm_channel=1
sudo dtoverlay -d . rp1_ws281x_pwm
sudo pinctrl set 13 a0 pn

# 4) allow the normal Herbie user to access the device node
sudo chgrp gpio /dev/ws281x_pwm
sudo chmod 660 /dev/ws281x_pwm
```

Pi 5-specific notes:
- `GPIO13` maps to `PWM0_CHAN1` on Pi 5, hence `pwm_channel=1` with `pinctrl set 13 a0 pn`. (The upstream guide uses `GPIO18` = `PWM0_CHAN2` with `pwm_channel=2` and `a3`. On this board GPIO18 is stuck high and GPIO12 (`PWM0_CHAN0`) can no longer switch fast enough for WS281x data, so neither is used. The remaining PWM0 option is `GPIO19` = `PWM0_CHAN3` on `a3`.)
- The `/dev/ws281x_pwm` permission change above is not persistent across reboot or overlay reload unless you add a udev rule or equivalent boot-time setup.
- If you still see LED init failures, check four things in this order: imported `rpi_ws281x` package version, `/dev/ws281x_pwm` existence, `/dev/ws281x_pwm` permissions, and whether `pinctrl get 13` reports `GPIO13 = PWM0_CHAN1`.

Quick reboot protocol:
1. Run `setup/enable_pi5_led_runtime.sh`
2. Make sure it prints `start_result=True`
3. If you want to double-check manually, run `ls -l /dev/ws281x_pwm` and `pinctrl get 13`
4. Start Herbie normally with `source venv/bin/activate` and `python3 main.py`
