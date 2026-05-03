from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

VOICE_SAMPLE_PATH = Path(
    # "/Users/gsm/Results/phi0_synth/full_case_study/recordings/concatenated_final_cutout_extracted_audio_high_quality.m4a"
    '/Users/gsm/Results/clock_timing_jitter_vid/narration.aac'
)

MODEL_NAME = os.getenv("XTTS_MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2")
LOCAL_MODEL_PATH = os.getenv("XTTS_MODEL_PATH")

LANGUAGE = "en"
MAX_CHARS_PER_CHUNK = 230  # XTTS hard limit is 250 for 'en' — keep safe margin
SAMPLE_RATE = 24000

# XTTS Quality Settings
TEMPERATURE = 0.85        # Was 0.75 → more expressive/emotional
REPETITION_PENALTY = 6.0  # Was 5.0 → less robotic, more varied delivery
LENGTH_PENALTY = 1.0      # Controls speech speed (1.0 = natural)
TOP_K = 55                # Was 50 → wider sampling diversity
TOP_P = 0.90              # Was 0.85 → broader nucleus sampling range

OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUT_AUDIO_DIR = OUTPUTS_DIR / "audio"
OUTPUT_VIDEO_DIR = OUTPUTS_DIR / "video"
CHUNK_AUDIO_DIR = OUTPUT_AUDIO_DIR / "chunks"

PREPROCESSED_VOICE_PATH = OUTPUT_AUDIO_DIR / "voice_reference.wav"
OUTPUT_AUDIO_PATH = OUTPUT_AUDIO_DIR / "final_episode.wav"
OUTPUT_MP3_PATH = OUTPUT_AUDIO_DIR / "final_episode.mp3"
OUTPUT_VIDEO_PATH = OUTPUT_VIDEO_DIR / "final_episode.mp4"

DEFAULT_VIDEO_SIZE = "1920x1080"
DEFAULT_VIDEO_FPS = 30
DEFAULT_VIDEO_BG_COLOR = "black"
CHUNK_FADE_MS = 10
MP3_BITRATE = "192k"

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")


def ensure_output_dirs() -> None:
    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    CHUNK_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

