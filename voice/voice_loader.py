from __future__ import annotations

from pathlib import Path

from config import PREPROCESSED_VOICE_PATH, VOICE_SAMPLE_PATH
from voice.preprocess import preprocess_voice_sample


def prepare_voice_sample(
    input_path: str | Path = VOICE_SAMPLE_PATH,
    output_path: str | Path = PREPROCESSED_VOICE_PATH,
) -> Path:
    return preprocess_voice_sample(input_path=input_path, output_path=output_path)

