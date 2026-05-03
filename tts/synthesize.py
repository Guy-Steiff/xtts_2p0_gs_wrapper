from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Auto-accept Coqui TTS license (non-commercial use)
os.environ['COQUI_TOS_AGREED'] = '1'

# Patch for missing _lzma module (pyenv Python compiled without lzma support)
try:
    import _lzma
except ImportError:
    try:
        from backports import lzma as _lzma
        sys.modules['_lzma'] = _lzma
        sys.modules['lzma'] = _lzma
    except ImportError:
        pass  # Will fail later with clear error if backports.lzma not installed

from config import (
    CHUNK_AUDIO_DIR, LANGUAGE, LOCAL_MODEL_PATH, MODEL_NAME, SAMPLE_RATE,
    TEMPERATURE, REPETITION_PENALTY, LENGTH_PENALTY, TOP_K, TOP_P,
)

if TYPE_CHECKING:
    from TTS.api import TTS

_tts_instance: TTS | None = None


def get_tts_model() -> TTS:
    global _tts_instance
    if _tts_instance is None:
        from TTS.api import TTS

        if LOCAL_MODEL_PATH and Path(LOCAL_MODEL_PATH).exists():
            _tts_instance = TTS(model_path=LOCAL_MODEL_PATH, progress_bar=False)
        else:
            _tts_instance = TTS(MODEL_NAME, progress_bar=False, gpu=False)
    return _tts_instance


def synthesize_chunk(
    text: str,
    speaker_wav: str | Path,
    output_path: str | Path,
    language: str = LANGUAGE,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tts = get_tts_model()
    tts.tts_to_file(
        text=text,
        speaker_wav=str(speaker_wav),
        language=language,
        file_path=str(output_path),
        temperature=TEMPERATURE,
        repetition_penalty=REPETITION_PENALTY,
        length_penalty=LENGTH_PENALTY,
        top_k=TOP_K,
        top_p=TOP_P,
    )
    return output_path


def synthesize_chunks(
    chunks: list[str],
    speaker_wav: str | Path,
    output_dir: str | Path = CHUNK_AUDIO_DIR,
    language: str = LANGUAGE,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files: list[Path] = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        chunk_path = output_dir / f"chunk_{i:04d}.wav"
        print(f"[{i+1}/{total}] Synthesizing chunk {i:04d} ({len(chunk)} chars)...")
        synthesize_chunk(chunk, speaker_wav, chunk_path, language=language)
        audio_files.append(chunk_path)

    return audio_files



