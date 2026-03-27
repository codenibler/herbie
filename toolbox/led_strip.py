from __future__ import annotations

from array import array
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread

import atexit
import logging
import math
import os
import stat
import subprocess
import sys
import time
import wave

try:
    import rpi_ws281x as rpi_ws281x_module
    from rpi_ws281x import PixelStrip, Color, ws
except Exception as error:
    rpi_ws281x_module = None
    PixelStrip = None
    Color = None
    ws = None
    LED_IMPORT_ERROR = error
else:
    LED_IMPORT_ERROR = None


LED_RUNTIME_MODULE_PATH = getattr(rpi_ws281x_module, "__file__", None)
LED_RUNTIME_VERSION = getattr(rpi_ws281x_module, "__version__", None)
LED_DEVICE_PATH = Path("/dev/ws281x_pwm")
PI5_LED_RUNTIME_SCRIPT = Path(__file__).resolve().parent.parent / "setup" / "enable_pi5_led_runtime.sh"


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_rgb_env(name: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default

    try:
        red, green, blue = [int(component.strip()) for component in raw_value.split(",")]
    except (TypeError, ValueError):
        logging.warning("Invalid %s value %r. Falling back to %s.", name, raw_value, default)
        return default

    return tuple(max(0, min(255, component)) for component in (red, green, blue))


LED_STRIP_ENABLED = _get_bool_env("LED_STRIP_ENABLED", True)
PIXEL_COUNT = int(os.getenv("PIXEL_COUNT", 80))
LED_PIN = int(os.getenv("LED_PIN", 18))
LED_FREQ_HZ = int(os.getenv("LED_FREQ_HZ", 800000))
LED_DMA = int(os.getenv("LED_DMA", 10))
LED_BRIGHTNESS = int(os.getenv("LED_BRIGHTNESS", 80))
LED_INVERT = _get_bool_env("LED_INVERT", False)
LED_CHANNEL = int(os.getenv("LED_CHANNEL", 0))
LED_STRIP_TYPE_NAME = os.getenv("LED_STRIP_TYPE", "WS2811_STRIP_GRB")
LED_FRAME_SECONDS = float(os.getenv("LED_FRAME_SECONDS", 0.04))
LED_IDLE_CYCLE_SECONDS = float(os.getenv("LED_IDLE_CYCLE_SECONDS", 2.8))
LED_IDLE_MIN_BRIGHTNESS = float(os.getenv("LED_IDLE_MIN_BRIGHTNESS", 0.08))
LED_IDLE_COLOR = _get_rgb_env("LED_IDLE_COLOR", (255, 0, 0))
LED_LOADING_COLOR = _get_rgb_env("LED_LOADING_COLOR", (255, 0, 0))
LED_LOADING_BACKGROUND_COLOR = _get_rgb_env("LED_LOADING_BACKGROUND_COLOR", (8, 4, 0))
LED_AUDIO_LOW_COLOR = _get_rgb_env("LED_AUDIO_LOW_COLOR", (200, 0, 0))
LED_AUDIO_HIGH_COLOR = _get_rgb_env("LED_AUDIO_HIGH_COLOR", (255, 0, 0))
LED_AUDIO_CHUNK_MS = int(os.getenv("LED_AUDIO_CHUNK_MS", 40))
LED_AUDIO_GAIN = float(os.getenv("LED_AUDIO_GAIN", 2.6))
LED_AUDIO_FALLOFF = float(os.getenv("LED_AUDIO_FALLOFF", 0.82))

PCM_ARRAY_TYPE_BY_SAMPLE_WIDTH = {
    2: "h",
    4: "i",
}


@dataclass(frozen=True)
class _LedPalette:
    idle_color: tuple[int, int, int]
    loading_color: tuple[int, int, int]
    loading_background_color: tuple[int, int, int]
    audio_low_color: tuple[int, int, int]
    audio_high_color: tuple[int, int, int]


def _resolve_led_strip_type():
    if ws is None:
        return None
    logging.info(f"Led strip name: {LED_STRIP_TYPE_NAME}")
    return getattr(ws, LED_STRIP_TYPE_NAME, ws.WS2811_STRIP_GRB)


def _read_pi_revision() -> str | None:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as cpuinfo_file:
            for line in cpuinfo_file:
                if line.startswith("Revision"):
                    return line.split(":", 1)[1].strip().lower()
    except OSError:
        return None
    return None


def _is_pi5_revision(revision: str | None) -> bool:
    if revision is None:
        return False

    try:
        revision_value = int(revision, 16)
    except ValueError:
        return False

    # Raspberry Pi revision scheme: model field lives in bits 4..11.
    model = (revision_value >> 4) & 0xFF
    return model == 0x17


def _log_process_output(output: str, level: int) -> None:
    for line in output.splitlines():
        logging.log(level, "[pi5-led-runtime] %s", line)


def enable_pi5_led_runtime() -> None:
    pi_revision = _read_pi_revision()
    if not _is_pi5_revision(pi_revision):
        if pi_revision is None:
            logging.info("Skipping Pi 5 LED runtime setup because Pi hardware was not detected.")
        else:
            logging.info(
                "Skipping Pi 5 LED runtime setup because Pi revision %s is not a Pi 5.",
                pi_revision,
            )
        return

    if not _get_bool_env("LED_STRIP_ENABLED", LED_STRIP_ENABLED):
        logging.info("Skipping Pi 5 LED runtime setup because LED strip support is disabled.")
        return

    if not PI5_LED_RUNTIME_SCRIPT.is_file():
        logging.warning("Pi 5 LED runtime setup script is missing: %s", PI5_LED_RUNTIME_SCRIPT)
        return

    logging.info("Running Pi 5 LED runtime setup script: %s", PI5_LED_RUNTIME_SCRIPT)
    try:
        result = subprocess.run(
            ["bash", str(PI5_LED_RUNTIME_SCRIPT)],
            cwd=PI5_LED_RUNTIME_SCRIPT.parent.parent,
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
    except OSError as error:
        logging.warning("Failed to launch Pi 5 LED runtime setup script: %s", error)
        return
    except subprocess.CalledProcessError as error:
        _log_process_output(error.stdout, logging.INFO)
        _log_process_output(error.stderr, logging.ERROR)
        logging.warning(
            "Pi 5 LED runtime setup script failed with exit code %s. Continuing startup.",
            error.returncode,
        )
        return

    _log_process_output(result.stdout, logging.INFO)
    _log_process_output(result.stderr, logging.WARNING)
    logging.info("Pi 5 LED runtime setup complete.")


def _build_led_init_hint(error: Exception) -> str | None:
    error_text = str(error)
    if "Hardware revision is not supported" not in error_text and "Permission denied" not in error_text:
        return None

    details: list[str] = []
    revision = _read_pi_revision()
    if revision is not None:
        details.append(f"Detected Pi revision {revision}.")

    if LED_RUNTIME_VERSION is not None:
        details.append(f"rpi_ws281x Python package version: {LED_RUNTIME_VERSION}.")
    if LED_RUNTIME_MODULE_PATH is not None:
        details.append(f"Imported from: {LED_RUNTIME_MODULE_PATH}.")

    if LED_DEVICE_PATH.exists():
        device_stat = LED_DEVICE_PATH.stat()
        mode = stat.S_IMODE(device_stat.st_mode)
        details.append(
            f"{LED_DEVICE_PATH} exists with mode {oct(mode)} and uid:gid "
            f"{device_stat.st_uid}:{device_stat.st_gid}."
        )
    else:
        details.append(f"{LED_DEVICE_PATH} is missing.")

    if _is_pi5_revision(revision):
        details.append(
            "Pi 5 support requires the Pi 5-capable rpi_ws281x Python build plus the "
            "rp1_ws281x_pwm kernel module and dtoverlay. The vendored rpi_ws281x/ C "
            "sources in this repo are not used unless the Python package in the venv "
            "is rebuilt from Pi 5-capable sources."
        )
        details.append(
            "If the device node exists but is root-only, grant the gpio group access "
            "or run Herbie with sudo."
        )

    return " ".join(details)


def _scale_color(color: tuple[int, int, int], brightness: float) -> tuple[int, int, int]:
    normalized_brightness = max(0.0, min(1.0, brightness))
    return tuple(int(component * normalized_brightness) for component in color)


def _blend_colors(
    start_color: tuple[int, int, int],
    end_color: tuple[int, int, int],
    amount: float,
) -> tuple[int, int, int]:
    normalized_amount = max(0.0, min(1.0, amount))
    return tuple(
        int(start + (end - start) * normalized_amount)
        for start, end in zip(start_color, end_color)
    )


def _cosine_brightness(phase: float) -> float:
    return 0.5 - 0.5 * math.cos(2.0 * math.pi * phase)


def _build_default_palette() -> _LedPalette:
    return _LedPalette(
        idle_color=LED_IDLE_COLOR,
        loading_color=LED_LOADING_COLOR,
        loading_background_color=LED_LOADING_BACKGROUND_COLOR,
        audio_low_color=LED_AUDIO_LOW_COLOR,
        audio_high_color=LED_AUDIO_HIGH_COLOR,
    )


def _tint_color(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return _blend_colors(color, (255, 255, 255), amount)


def _build_runtime_palette(base_color: tuple[int, int, int]) -> _LedPalette:
    # Keep Herbie in the same hue family as the station color, while preserving
    # enough contrast for background and audio animation states.
    idle_color = _tint_color(base_color, 0.18)
    loading_color = _tint_color(base_color, 0.10)
    loading_background_color = _scale_color(_tint_color(base_color, 0.32), 0.18)
    audio_low_color = _tint_color(base_color, 0.24)

    return _LedPalette(
        idle_color=idle_color,
        loading_color=loading_color,
        loading_background_color=loading_background_color,
        audio_low_color=audio_low_color,
        audio_high_color=base_color,
    )


@dataclass
class _AudioSession:
    stop_event: Event
    level: float = 0.0


class LedStripController:
    def __init__(self) -> None:
        self._state_lock = Lock()
        self._start_lock = Lock()
        self._wake_event = Event()
        self._shutdown_event = Event()
        self._strip: PixelStrip | None = None
        self._enabled = False
        self._started = False
        self._idle_enabled = False
        self._loading_ref_count = 0
        self._audio_sessions: dict[int, _AudioSession] = {}
        self._next_audio_session_id = 1
        self._palette = _build_default_palette()
        self._render_thread: Thread | None = None

    def start(self) -> bool:
        if not LED_STRIP_ENABLED:
            return False

        with self._start_lock:
            if self._started:
                return self._enabled

            self._started = True

            if PixelStrip is None or Color is None or ws is None:
                logging.warning(
                    "LED strip support is unavailable. Runtime animations disabled. Error: %s",
                    LED_IMPORT_ERROR,
                )
                return False

            try:
                self._strip = PixelStrip(
                    PIXEL_COUNT,
                    LED_PIN,
                    LED_FREQ_HZ,
                    LED_DMA,
                    LED_INVERT,
                    LED_BRIGHTNESS,
                    LED_CHANNEL,
                    _resolve_led_strip_type(),
                )
                self._strip.begin()
            except Exception as error:
                self._strip = None
                led_hint = _build_led_init_hint(error)
                logging.warning(
                    "Failed to initialize LED strip. Runtime animations disabled. Error: %s",
                    error,
                )
                if led_hint:
                    logging.warning("LED init hint: %s", led_hint)
                return False

            self._enabled = True
            self._render_thread = Thread(
                target=self._render_loop,
                name="herbie-led-strip",
                daemon=True,
            )
            self._render_thread.start()
            atexit.register(self.shutdown)
            logging.info("Initialized LED strip controller with %s pixels.", PIXEL_COUNT)
            return True

    def shutdown(self) -> None:
        if not self._started:
            return

        self._shutdown_event.set()
        self._wake_event.set()

        render_thread = self._render_thread
        if render_thread is not None and render_thread.is_alive():
            render_thread.join(timeout=1.0)

        self._clear_strip()

    def set_idle_enabled(self, enabled: bool) -> None:
        if enabled:
            self.start()

        with self._state_lock:
            self._idle_enabled = enabled

        self._wake_event.set()

    def set_runtime_color_scheme(self, base_color: tuple[int, int, int]) -> None:
        with self._state_lock:
            self._palette = _build_runtime_palette(base_color)

        self._wake_event.set()

    def start_loading(self) -> bool:
        if not self.start():
            return False

        with self._state_lock:
            self._loading_ref_count += 1

        self._wake_event.set()
        return True

    def stop_loading(self) -> None:
        with self._state_lock:
            if self._loading_ref_count > 0:
                self._loading_ref_count -= 1

        self._wake_event.set()

    def begin_audio_visualizer(self, wav_path: str | Path) -> int | None:
        if not self.start():
            return None

        session_id: int
        session = _AudioSession(stop_event=Event())
        with self._state_lock:
            session_id = self._next_audio_session_id
            self._next_audio_session_id += 1
            self._audio_sessions[session_id] = session

        monitor_thread = Thread(
            target=self._monitor_audio_levels,
            args=(session_id, Path(wav_path), session.stop_event),
            name=f"herbie-led-audio-{session_id}",
            daemon=True,
        )
        monitor_thread.start()
        self._wake_event.set()
        return session_id

    def stop_audio_visualizer(self, session_id: int | None) -> None:
        if session_id is None:
            return

        session: _AudioSession | None
        with self._state_lock:
            session = self._audio_sessions.pop(session_id, None)

        if session is not None:
            session.stop_event.set()
            self._wake_event.set()

    def stop_all_audio_visualizers(self) -> None:
        with self._state_lock:
            session_ids = list(self._audio_sessions.keys())

        for session_id in session_ids:
            self.stop_audio_visualizer(session_id)

    def _clear_strip(self) -> None:
        if not self._enabled or self._strip is None:
            return
        self._show_pixels([(0, 0, 0)] * PIXEL_COUNT)

    def _show_pixels(self, pixels: list[tuple[int, int, int]]) -> None:
        if not self._enabled or self._strip is None or Color is None:
            return

        for index, (red, green, blue) in enumerate(pixels):
            self._strip.setPixelColor(index, Color(red, green, blue))
        self._strip.show()

    def _get_render_state(self) -> tuple[bool, bool, bool, float, _LedPalette]:
        with self._state_lock:
            idle_enabled = self._idle_enabled
            loading_active = self._loading_ref_count > 0
            audio_active = bool(self._audio_sessions)
            audio_level = max(
                (session.level for session in self._audio_sessions.values()),
                default=0.0,
            )
            palette = self._palette

        return idle_enabled, loading_active, audio_active, audio_level, palette

    def _render_loop(self) -> None:
        while not self._shutdown_event.is_set():
            now = time.monotonic()
            idle_enabled, loading_active, audio_active, audio_level, palette = self._get_render_state()

            if audio_active:
                self._show_pixels(self._build_audio_frame(audio_level, palette))
            elif loading_active:
                self._show_pixels(self._build_loading_frame(now, palette))
            elif idle_enabled:
                self._show_pixels(self._build_idle_frame(now, palette))
            else:
                self._clear_strip()

            self._wake_event.wait(timeout=LED_FRAME_SECONDS)
            self._wake_event.clear()

    def _build_idle_frame(
        self,
        now: float,
        palette: _LedPalette,
    ) -> list[tuple[int, int, int]]:
        phase = (now % max(LED_IDLE_CYCLE_SECONDS, 0.1)) / max(LED_IDLE_CYCLE_SECONDS, 0.1)
        brightness = LED_IDLE_MIN_BRIGHTNESS + (
            1.0 - LED_IDLE_MIN_BRIGHTNESS
        ) * _cosine_brightness(phase)
        color = _scale_color(palette.idle_color, brightness)
        return [color] * PIXEL_COUNT

    def _build_loading_frame(
        self,
        now: float,
        palette: _LedPalette,
    ) -> list[tuple[int, int, int]]:
        pixels = [_scale_color(palette.loading_background_color, 1.0)] * PIXEL_COUNT
        tail_length = max(4, PIXEL_COUNT // 8)
        position = int((now / max(LED_FRAME_SECONDS, 0.01)) * 1.5) % max(1, PIXEL_COUNT)

        for offset in range(tail_length):
            index = (position - offset) % PIXEL_COUNT
            brightness = 1.0 - (offset / tail_length)
            pixels[index] = _scale_color(palette.loading_color, brightness)

        return pixels

    def _build_audio_frame(
        self,
        level: float,
        palette: _LedPalette,
    ) -> list[tuple[int, int, int]]:
        normalized_level = max(0.0, min(1.0, level))
        exact_height = normalized_level * PIXEL_COUNT
        pixels: list[tuple[int, int, int]] = []

        for index in range(PIXEL_COUNT):
            pixel_fill = max(0.0, min(1.0, exact_height - index))
            if pixel_fill <= 0.0:
                pixels.append((0, 0, 0))
                continue

            color_position = index / max(1, PIXEL_COUNT - 1)
            base_color = _blend_colors(
                palette.audio_low_color,
                palette.audio_high_color,
                color_position,
            )
            pixels.append(_scale_color(base_color, pixel_fill))

        return pixels

    def _monitor_audio_levels(
        self,
        session_id: int,
        wav_path: Path,
        stop_event: Event,
    ) -> None:
        smoothed_level = 0.0

        try:
            with wave.open(str(wav_path), "rb") as wav_file:
                sample_width = wav_file.getsampwidth()
                channels = max(1, wav_file.getnchannels())
                frame_rate = max(1, wav_file.getframerate())
                frames_per_chunk = max(1, int(frame_rate * LED_AUDIO_CHUNK_MS / 1000))
                chunk_duration_seconds = frames_per_chunk / frame_rate
                next_deadline = time.monotonic()

                while not stop_event.is_set():
                    frames = wav_file.readframes(frames_per_chunk)
                    if not frames:
                        break

                    level = self._compute_audio_level(frames, sample_width, channels)
                    smoothed_level = max(level, smoothed_level * LED_AUDIO_FALLOFF)
                    self._set_audio_level(session_id, smoothed_level)

                    next_deadline += chunk_duration_seconds
                    wait_seconds = next_deadline - time.monotonic()
                    if wait_seconds > 0:
                        stop_event.wait(wait_seconds)
                    else:
                        next_deadline = time.monotonic()
        except (FileNotFoundError, wave.Error, OSError) as error:
            logging.warning("Failed to monitor WAV levels for %s: %s", wav_path, error)
        finally:
            self.stop_audio_visualizer(session_id)

    def _set_audio_level(self, session_id: int, level: float) -> None:
        with self._state_lock:
            session = self._audio_sessions.get(session_id)
            if session is None:
                return
            session.level = max(0.0, min(1.0, level))

        self._wake_event.set()

    def _compute_audio_level(self, frames: bytes, sample_width: int, channels: int) -> float:
        if sample_width == 1:
            if not frames:
                return 0.0
            rms = self._compute_unsigned_8bit_rms(frames, channels)
            full_scale = 128.0
        else:
            typecode = PCM_ARRAY_TYPE_BY_SAMPLE_WIDTH.get(sample_width)
            if typecode is None:
                return 0.0

            samples = array(typecode)
            samples.frombytes(frames)
            if not samples:
                return 0.0
            if sys.byteorder != "little":
                samples.byteswap()

            rms = self._compute_signed_rms(samples, channels)
            full_scale = float((1 << (8 * sample_width - 1)) - 1)

        normalized_rms = math.sqrt(max(0.0, rms / max(1.0, full_scale)))
        return min(1.0, normalized_rms * LED_AUDIO_GAIN)

    def _compute_unsigned_8bit_rms(self, frames: bytes, channels: int) -> float:
        if channels <= 1:
            sample_count = len(frames)
            if sample_count == 0:
                return 0.0
            sum_squares = 0.0
            for sample in frames:
                centered_sample = sample - 128.0
                sum_squares += centered_sample * centered_sample
            return math.sqrt(sum_squares / sample_count)

        frame_count = len(frames) // channels
        if frame_count == 0:
            return 0.0

        sum_squares = 0.0
        for frame_index in range(frame_count):
            frame_start = frame_index * channels
            mono_sample = sum(
                frames[frame_start + channel_index] - 128.0
                for channel_index in range(channels)
            ) / channels
            sum_squares += mono_sample * mono_sample
        return math.sqrt(sum_squares / frame_count)

    def _compute_signed_rms(self, samples: array, channels: int) -> float:
        if channels <= 1:
            sample_count = len(samples)
            if sample_count == 0:
                return 0.0
            sum_squares = 0.0
            for sample in samples:
                sum_squares += float(sample) * float(sample)
            return math.sqrt(sum_squares / sample_count)

        frame_count = len(samples) // channels
        if frame_count == 0:
            return 0.0

        sum_squares = 0.0
        for frame_index in range(frame_count):
            frame_start = frame_index * channels
            mono_sample = sum(
                samples[frame_start + channel_index]
                for channel_index in range(channels)
            ) / channels
            sum_squares += mono_sample * mono_sample
        return math.sqrt(sum_squares / frame_count)


LED_STRIP_CONTROLLER = LedStripController()


def start_led_strip_controller() -> bool:
    return LED_STRIP_CONTROLLER.start()


def set_idle_led_mode(enabled: bool) -> None:
    LED_STRIP_CONTROLLER.set_idle_enabled(enabled)


def set_runtime_color_scheme(base_color: tuple[int, int, int]) -> None:
    LED_STRIP_CONTROLLER.set_runtime_color_scheme(base_color)


def start_loading_led_animation() -> bool:
    return LED_STRIP_CONTROLLER.start_loading()


def stop_loading_led_animation() -> None:
    LED_STRIP_CONTROLLER.stop_loading()


def begin_audio_led_visualizer(wav_path: str | Path) -> int | None:
    return LED_STRIP_CONTROLLER.begin_audio_visualizer(wav_path)


def stop_audio_led_visualizer(session_id: int | None) -> None:
    LED_STRIP_CONTROLLER.stop_audio_visualizer(session_id)


def stop_all_audio_led_visualizers() -> None:
    LED_STRIP_CONTROLLER.stop_all_audio_visualizers()
