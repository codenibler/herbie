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

Run:
```bash
source venv/bin/activate
python3 main.py
```

Local note for WS281x LED testing on Raspberry Pi 5:
- This repo includes a local `rpi_ws281x` patch for Raspberry Pi 5 Model B Rev 1.1 boards reporting revision `d04171`, which otherwise fail with `ws2811_init failed with code -3 (Hardware revision is not supported)`.
- Upstream reference: issue `#555` and PR `#556` in `jgarff/rpi_ws281x`.
