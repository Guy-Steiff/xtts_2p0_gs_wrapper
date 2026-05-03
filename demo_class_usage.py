#!/usr/bin/env python3
"""
Demo script showing how to use the PodcastGenerator class.

This example:
- Creates a PodcastGenerator instance with custom voice
- Generates podcast from a script
- Saves to a custom output location
- Deletes chunk files after completion
"""

import os
import sys
import time

# Auto-accept Coqui TTS license
os.environ['COQUI_TOS_AGREED'] = '1'

# Patch for missing _lzma module
try:
    import _lzma
except ImportError:
    try:
        from backports import lzma as _lzma
        sys.modules['_lzma'] = _lzma
        sys.modules['lzma'] = _lzma
    except ImportError:
        pass

from podcast_generator import PodcastGenerator

if __name__ == "__main__":
    str_root_results_folder = os.path.join(os.path.dirname(__file__), 'outputs', 'audio')
    ts_timestamps = time.localtime()
    str_timestamps = str(time.strftime("%Y_%m_%d_%H_%M_%S", ts_timestamps))
    str_full_folder = os.path.join(str_root_results_folder, f'{str_timestamps}')
    os.makedirs(str_full_folder, exist_ok=True)

    # Path to the bundled sample voice — replace with your own .aac/.wav/.mp3 file
    _here = os.path.dirname(os.path.abspath(__file__))
    sample_voice = os.path.join(_here, 'sample_voices', 'sample_voice.aac')

    # Initialize generator with custom settings
    generator = PodcastGenerator(
        voice_sample_path=sample_voice,
        language="en",
        max_chars_per_chunk=230,  # max_chars_per_chunk=230 is safe for 'en' (XTTS hard limit is 250)
        sample_rate=24000,  # Audio sample rate in Hz
        temperature=0.65,  # Lower temp = far fewer artifact tails; still expressive enough for narration
        repetition_penalty=2.0,  # Lowered further — high values cause mid-word cutoffs on polysyllabic words
        top_p=0.92,  # Nucleus sampling (0.0-1.0)
        chunk_fade_ms = 0,  # chunk_fade_ms: Crossfade duration between chunks
        voice_max_duration=25.0,  # Take only the first 25s (default: 30s)
        voice_start_seconds=0.0,  # Skip the first 0s if there's intro noise
    )

    # Generate podcast
    results = generator.run(
        str_input_txt_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'quick_example.txt'),  # bundled demo script
        str_output_path=f"{str_full_folder}",
        b_keep_chunks=False,  # Delete chunks after completion
        normalize=True,
    )

    print(f"\n🎉 Podcast saved to: {results['mp3']}")

