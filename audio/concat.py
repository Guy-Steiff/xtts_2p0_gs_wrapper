from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from config import CHUNK_FADE_MS
from tts.chunking import PauseMarker


def concat_audio(
    audio_items: list[Path | PauseMarker],
    output_path: str | Path,
    fade_ms: int = CHUNK_FADE_MS,
    sample_rate: int = 24000,
) -> Path:
    """
    Concatenate audio files with optional silence gaps.

    audio_items is an interleaved list of:
      - Path objects  → WAV files to include
      - PauseMarker   → insert N ms of silence at that position

    Example:
        concat_audio([
            Path("chunk_0000.wav"),
            PauseMarker(500),
            Path("chunk_0001.wav"),
            PauseMarker(1000),
            Path("chunk_0002.wav"),
        ], "output.wav")
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wav_count = sum(1 for item in audio_items if isinstance(item, Path))
    if wav_count == 0:
        raise ValueError("No audio files provided for concatenation.")

    print(f"Concatenating {wav_count} audio chunks...")
    combined = AudioSegment.empty()

    for item in audio_items:
        if isinstance(item, PauseMarker):
            silence = AudioSegment.silent(duration=item.ms, frame_rate=sample_rate)
            combined += silence
        else:
            segment = AudioSegment.from_wav(str(item))
            if fade_ms > 0:
                segment = segment.fade_in(fade_ms).fade_out(fade_ms)
            combined += segment

    combined.export(str(output_path), format="wav")
    print(f"Concatenated audio saved to: {output_path}")
    return output_path


def export_mp3(
    input_wav: str | Path,
    output_mp3: str | Path,
    bitrate: str = "192k",
) -> Path:
    input_wav = Path(input_wav)
    output_mp3 = Path(output_mp3)
    output_mp3.parent.mkdir(parents=True, exist_ok=True)

    audio = AudioSegment.from_wav(str(input_wav))
    audio.export(str(output_mp3), format="mp3", bitrate=bitrate)
    print(f"MP3 exported to: {output_mp3}")
    return output_mp3
