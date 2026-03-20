from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AdaptiveSpeechDetectorConfig:
    frame_duration_seconds: float
    initial_noise_floor: float = 0.0
    min_noise_floor: float = 1.0
    start_ratio: float = 2.4
    end_ratio: float = 1.35
    min_start_margin: float = 180.0
    min_end_margin: float = 90.0
    start_trigger_frames: int = 2
    end_trigger_frames: int = 12
    min_silence_duration_seconds: float = 1.0
    noise_floor_rise_alpha: float = 0.18
    noise_floor_fall_alpha: float = 0.05
    speech_ema_alpha: float = 0.35
    speech_decay_alpha: float = 0.12
    speech_peak_decay: float = 0.97
    strong_speech_ratio: float = 0.65
    strong_peak_ratio: float = 0.35


@dataclass(slots=True)
class SpeechFrameDecision:
    energy: float
    noise_floor: float
    speech_ema: float
    speech_peak: float
    start_threshold: float
    end_threshold: float
    strong_threshold: float
    speech_started_now: bool
    is_speaking: bool
    is_strong_speech: bool
    quiet_frames: int
    silence_since_strong_speech: float
    should_stop: bool


class AdaptiveSpeechDetector:
    """Adaptive, hysteresis-based speech detector for chunked microphone audio."""

    def __init__(self, config: AdaptiveSpeechDetectorConfig):
        self.config = config
        self.speech_started = False
        self.noise_floor = max(config.initial_noise_floor, config.min_noise_floor)
        self.speech_ema = self.noise_floor
        self.speech_peak = self.noise_floor
        self._speech_candidate_frames = 0
        self._quiet_frames = 0
        self._last_strong_speech_at: float | None = None

    def process_frame(self, energy: float, now: float) -> SpeechFrameDecision:
        self._seed_noise_floor(energy)

        start_threshold = self._threshold(self.config.start_ratio, self.config.min_start_margin)
        end_threshold = self._threshold(self.config.end_ratio, self.config.min_end_margin)

        speech_started_now = False
        should_stop = False
        is_strong_speech = False

        if not self.speech_started:
            if energy >= start_threshold:
                self._speech_candidate_frames += 1
                self._update_speech_metrics(energy, is_active=True)
            else:
                self._speech_candidate_frames = 0
                self._update_noise_floor(energy)
                self._update_speech_metrics(energy, is_active=False)

            if self._speech_candidate_frames >= self.config.start_trigger_frames:
                self.speech_started = True
                speech_started_now = True
                self._speech_candidate_frames = 0
                self._quiet_frames = 0
                self._last_strong_speech_at = now

        else:
            is_active_speech = energy >= end_threshold
            self._update_speech_metrics(energy, is_active=is_active_speech)

            strong_threshold = self._strong_threshold(end_threshold)
            is_strong_speech = energy >= strong_threshold
            silence_since_strong_speech = self._silence_since_strong_speech(now)

            if is_strong_speech:
                self._last_strong_speech_at = now
                self._quiet_frames = 0
            elif is_active_speech and silence_since_strong_speech < self.config.min_silence_duration_seconds:
                self._quiet_frames = 0
            else:
                self._quiet_frames += 1
                self._update_noise_floor(energy)

            silence_since_strong_speech = self._silence_since_strong_speech(now)
            if (
                self._quiet_frames >= self.config.end_trigger_frames
                and silence_since_strong_speech >= self.config.min_silence_duration_seconds
            ):
                should_stop = True
        strong_threshold = self._strong_threshold(end_threshold)
        silence_since_strong_speech = self._silence_since_strong_speech(now)

        return SpeechFrameDecision(
            energy=energy,
            noise_floor=self.noise_floor,
            speech_ema=self.speech_ema,
            speech_peak=self.speech_peak,
            start_threshold=start_threshold,
            end_threshold=end_threshold,
            strong_threshold=strong_threshold,
            speech_started_now=speech_started_now,
            is_speaking=self.speech_started,
            is_strong_speech=is_strong_speech,
            quiet_frames=self._quiet_frames,
            silence_since_strong_speech=silence_since_strong_speech,
            should_stop=should_stop,
        )

    def _seed_noise_floor(self, energy: float) -> None:
        if self.noise_floor <= self.config.min_noise_floor and self.config.initial_noise_floor <= 0:
            self.noise_floor = max(energy, self.config.min_noise_floor)
            self.speech_ema = self.noise_floor
            self.speech_peak = self.noise_floor

    def _threshold(self, ratio: float, min_margin: float) -> float:
        return max(self.noise_floor * ratio, self.noise_floor + min_margin)

    def _update_noise_floor(self, energy: float) -> None:
        alpha = (
            self.config.noise_floor_rise_alpha
            if energy >= self.noise_floor
            else self.config.noise_floor_fall_alpha
        )
        self.noise_floor = max(
            self.config.min_noise_floor,
            self.noise_floor + (energy - self.noise_floor) * alpha,
        )

    def _update_speech_metrics(self, energy: float, is_active: bool) -> None:
        if is_active:
            self.speech_ema = self.speech_ema + (energy - self.speech_ema) * self.config.speech_ema_alpha
            self.speech_peak = max(energy, self.speech_peak * self.config.speech_peak_decay)
            return

        self.speech_ema = self.speech_ema + (self.noise_floor - self.speech_ema) * self.config.speech_decay_alpha
        self.speech_peak = max(self.noise_floor, self.speech_peak * self.config.speech_peak_decay)

    def _strong_threshold(self, end_threshold: float) -> float:
        return max(
            end_threshold,
            self.speech_ema * self.config.strong_speech_ratio,
            self.speech_peak * self.config.strong_peak_ratio,
        )

    def _silence_since_strong_speech(self, now: float) -> float:
        if self._last_strong_speech_at is None:
            return 0.0
        return now - self._last_strong_speech_at
