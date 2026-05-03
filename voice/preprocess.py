from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from config import FFMPEG_BIN, SAMPLE_RATE


class FFmpegError(RuntimeError):
    """Raised when an FFmpeg command fails."""


def _ensure_ffmpeg() -> None:
    if Path(FFMPEG_BIN).is_file():
        return
    if shutil.which(FFMPEG_BIN):
        return
    raise FileNotFoundError(
        "FFmpeg was not found. Install ffmpeg and make sure it is available in PATH."
    )


def _run_ffmpeg(command: list[str]) -> None:
    _ensure_ffmpeg()
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or "FFmpeg command failed.")


def convert_to_wav(input_path: str | Path, output_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        str(output_path),
    ]
    _run_ffmpeg(command)
    return output_path


def normalize_audio(input_path: str | Path, output_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(input_path),
        "-af",
        "loudnorm=I=-18:TP=-1.5:LRA=11",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        str(output_path),
    ]
    _run_ffmpeg(command)
    return output_path


def remove_silence(input_path: str | Path, output_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(input_path),
        "-af",
        (
            "silenceremove="
            "start_periods=1:start_silence=0.2:start_threshold=-45dB:"
            "stop_periods=1:stop_silence=0.2:stop_threshold=-45dB"
        ),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        str(output_path),
    ]
    _run_ffmpeg(command)
    return output_path


def trim_audio(
    input_path: str | Path,
    output_path: str | Path,
    duration_seconds: float = 30.0,
    start_seconds: float = 0.0,
) -> Path:
    """
    Trim audio to a specific duration and start offset.
    XTTS internally uses ~6s for voice fingerprinting; 10-30s is the optimal
    reference length — longer files provide no benefit.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        FFMPEG_BIN,
        "-y",
        "-i", str(input_path),
        "-ss", str(start_seconds),
        "-t", str(duration_seconds),
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        str(output_path),
    ]
    _run_ffmpeg(command)
    return output_path


def preprocess_voice_sample(
    input_path: str | Path,
    output_path: str | Path,
    max_duration_seconds: float = 30.0,
    start_seconds: float = 0.0,
) -> Path:
    """
    Preprocessing pipeline: convert → trim to window → normalize.

    Silence removal is intentionally skipped — XTTS clones voice
    from the raw waveform and doesn't benefit from silence stripping.
    Trimming to a clean window is sufficient.

    Args:
        input_path:           Source audio file (any format FFmpeg supports)
        output_path:          Output WAV path
        max_duration_seconds: Length of the voice window in seconds (default: 30s)
        start_seconds:        Start offset into source file (default: 0s)
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Voice sample not found: {input_path}")

    with tempfile.TemporaryDirectory(prefix="voice-prep-") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        converted = tmp_dir_path / "converted.wav"

        convert_to_wav(input_path, converted)
        trimmed = tmp_dir_path / "trimmed.wav"
        trim_audio(
            converted,
            trimmed,
            duration_seconds=max_duration_seconds,
            start_seconds=start_seconds,
        )
        normalize_audio(trimmed, output_path)

    return output_path


