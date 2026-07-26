# Herbie wake-word model

Herbie uses the official
[`sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20`](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/)
streaming keyword-spotting model. The included chunk-16 quantized encoder and
joiner reduce storage and CPU use; the FP32 decoder is used because upstream
notes that decoder quantization gives little benefit. Chunk-16 trades 320 ms of
model latency for better accuracy than the chunk-8 variant.

`keywords.txt` defines `HEY_HERBIE` using the model's English phoneme lexicon:

```text
HH EY1 HH ER1 B IY0 @HEY_HERBIE
```

The model runs locally after installation and does not require an account,
access key, or network request. Runtime settings are documented in the project
`readme.md` and `dotenvstructure.txt`.

Source archive:

```text
https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2
```
