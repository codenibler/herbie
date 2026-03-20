from __future__ import annotations

from collections import deque
from math import ceil

import numpy as np


class PreRollAudioBuffer:
    """Keeps a bounded rolling window of mono chunks captured before speech starts."""

    def __init__(self, max_chunks: int):
        self._chunks: deque[np.ndarray] = deque(maxlen=max(1, max_chunks))

    @classmethod
    def from_duration(
        cls,
        duration_seconds: float,
        samplerate: int,
        blocksize: int,
    ) -> "PreRollAudioBuffer":
        chunk_seconds = blocksize / samplerate
        max_chunks = ceil(duration_seconds / chunk_seconds)
        return cls(max_chunks=max_chunks)

    def append(self, chunk: np.ndarray) -> None:
        self._chunks.append(chunk)

    def drain(self) -> list[np.ndarray]:
        chunks = list(self._chunks)
        self._chunks.clear()
        return chunks

    def clear(self) -> None:
        self._chunks.clear()

    def __len__(self) -> int:
        return len(self._chunks)
