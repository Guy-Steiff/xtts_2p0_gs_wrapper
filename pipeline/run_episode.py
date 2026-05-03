from __future__ import annotations

import argparse
from pathlib import Path

from audio.concat import concat_audio, export_mp3
from audio.normalize import normalize_audio
from config import (
    OUTPUT_AUDIO_PATH,
    OUTPUT_MP3_PATH,
    OUTPUT_VIDEO_PATH,
    PREPROCESSED_VOICE_PATH,
    ensure_output_dirs,
)
from tts.chunking import chunk_text
from tts.synthesize import synthesize_chunks
from video.render import render_video
from voice.voice_loader import prepare_voice_sample


def run_episode(
    script_path: str | Path,
    render_video_output: bool = False,
    normalize: bool = True,
) -> dict[str, Path]:
    script_path = Path(script_path)
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    ensure_output_dirs()

    print(f"\n{'='*80}")
    print(f"PODCAST GENERATION PIPELINE")
    print(f"{'='*80}\n")

    print(f"📄 Script: {script_path}")
    script_text = script_path.read_text(encoding="utf-8")
    print(f"   Length: {len(script_text)} characters\n")

    print(f"🎤 Preparing voice sample...")
    if not PREPROCESSED_VOICE_PATH.exists():
        voice_wav = prepare_voice_sample()
    else:
        voice_wav = PREPROCESSED_VOICE_PATH
        print(f"   Using cached voice reference: {voice_wav}\n")

    print(f"✂️  Chunking text...")
    chunks = chunk_text(script_text)
    print(f"   Created {len(chunks)} chunks\n")

    print(f"🔊 Synthesizing audio chunks...")
    audio_files = synthesize_chunks(chunks, speaker_wav=voice_wav)
    print(f"   Generated {len(audio_files)} audio files\n")

    print(f"🔗 Concatenating audio...")
    concat_audio(audio_files, OUTPUT_AUDIO_PATH)

    final_audio = OUTPUT_AUDIO_PATH
    if normalize:
        print(f"\n📊 Normalizing audio...")
        normalized_path = OUTPUT_AUDIO_PATH.parent / "final_episode_normalized.wav"
        normalize_audio(OUTPUT_AUDIO_PATH, normalized_path)
        final_audio = normalized_path

    print(f"\n💾 Exporting MP3...")
    export_mp3(final_audio, OUTPUT_MP3_PATH)

    results = {
        "wav": final_audio,
        "mp3": OUTPUT_MP3_PATH,
    }

    if render_video_output:
        print(f"\n🎬 Rendering video...")
        render_video(final_audio, OUTPUT_VIDEO_PATH)
        results["video"] = OUTPUT_VIDEO_PATH

    print(f"\n{'='*80}")
    print(f"✅ PIPELINE COMPLETE")
    print(f"{'='*80}\n")
    print(f"Outputs:")
    for key, path in results.items():
        print(f"  {key.upper()}: {path}")
    print()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate podcast audio from text script using voice cloning."
    )
    parser.add_argument(
        "--script",
        type=str,
        default="scripts/example_episode.txt",
        help="Path to the podcast script text file (default: scripts/example_episode.txt)",
    )
    parser.add_argument(
        "--video",
        action="store_true",
        help="Render video output (MP4)",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Skip audio normalization step",
    )

    args = parser.parse_args()

    run_episode(
        script_path=args.script,
        render_video_output=args.video,
        normalize=not args.no_normalize,
    )


if __name__ == "__main__":
    main()

