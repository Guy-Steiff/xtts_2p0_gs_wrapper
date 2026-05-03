from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Auto-accept Coqui TTS license (non-commercial use)
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

from audio.concat import concat_audio, export_mp3
from audio.normalize import normalize_audio
from tts.chunking import chunk_script, PauseMarker
from voice.preprocess import preprocess_voice_sample

if TYPE_CHECKING:
    from TTS.api import TTS


class PodcastGenerator:
    """
    Modular podcast generator with configurable voice cloning and synthesis.

    Example:
        generator = PodcastGenerator(
            voice_sample_path="/path/to/voice.m4a",
            temperature=0.85
        )
        results = generator.run(
            str_input_txt_path="/path/to/script.txt",
            str_output_path="/path/to/output",
            b_keep_chunks=False
        )
    """

    def __init__(
        self,
        voice_sample_path: str | Path,
        language: str = "en",
        max_chars_per_chunk: int = 230,  # XTTS hard limit is 250 for 'en' — keep margin
        sample_rate: int = 24000,
        temperature: float = 0.85,
        repetition_penalty: float = 7.0,
        length_penalty: float = 1.0,
        top_k: int = 60,
        top_p: float = 0.92,
        chunk_fade_ms: int = 10,
        mp3_bitrate: str = "192k",
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        voice_max_duration = 30.0,  # XTTS sweet spot for voice reference length
        voice_start_seconds = 0.0
    ):
        """
        Initialize podcast generator with voice and synthesis parameters.

        Args:
            voice_sample_path: Path to voice reference audio file
            language: Language code (default: "en")
            max_chars_per_chunk: Max characters per synthesis chunk
            sample_rate: Audio sample rate in Hz
            temperature: Synthesis temperature (0.1-1.0, higher=more expressive)
            repetition_penalty: Avoid repetitive patterns (2.0-10.0)
            length_penalty: Speech speed control (0.5-1.5)
            top_k: Sampling diversity
            top_p: Nucleus sampling (0.0-1.0)
            chunk_fade_ms: Crossfade duration between chunks
            mp3_bitrate: MP3 export bitrate
            model_name: TTS model identifier
        """
        self.voice_sample_path = Path(voice_sample_path)
        self.language = language
        self.max_chars_per_chunk = max_chars_per_chunk
        self.sample_rate = sample_rate
        self.temperature = temperature
        self.repetition_penalty = repetition_penalty
        self.length_penalty = length_penalty
        self.top_k = top_k
        self.top_p = top_p
        self.chunk_fade_ms = chunk_fade_ms
        self.mp3_bitrate = mp3_bitrate
        self.model_name = model_name
        self.voice_max_duration = voice_max_duration
        self.voice_start_seconds = voice_start_seconds
        self._tts_instance: TTS | None = None
        self._voice_reference_cache: Path | None = None
        self._vad_model = None  # Silero VAD singleton

    def _get_tts_model(self) -> TTS:
        """Get or create TTS model instance (singleton per generator instance)."""
        if self._tts_instance is None:
            from TTS.api import TTS
            print(f"Loading TTS model: {self.model_name}...")
            self._tts_instance = TTS(self.model_name, progress_bar=False, gpu=False)
        return self._tts_instance

    def _get_vad_model(self):
        """Get or create Silero VAD model (singleton per generator instance)."""
        if self._vad_model is None:
            from silero_vad import load_silero_vad
            print("Loading Silero VAD model...")
            self._vad_model = load_silero_vad()
        return self._vad_model

    def _prepare_voice_reference(self, output_dir: Path) -> Path:
        """Prepare voice reference (cached per instance)."""
        if self._voice_reference_cache is not None and self._voice_reference_cache.exists():
            return self._voice_reference_cache

        voice_ref_path = output_dir / "voice_reference.wav"

        if voice_ref_path.exists():
            print(f"   Using cached voice reference: {voice_ref_path}")
            self._voice_reference_cache = voice_ref_path
            return voice_ref_path

        print(f"   Preprocessing voice sample: {self.voice_sample_path.name}")
        preprocess_voice_sample(
            self.voice_sample_path,
            voice_ref_path,
            max_duration_seconds=self.voice_max_duration,
            start_seconds=self.voice_start_seconds,
        )
        self._voice_reference_cache = voice_ref_path
        return voice_ref_path

    @staticmethod
    def _clean_text_for_tts(text: str) -> str:
        """Sanitise text before sending to XTTS to prevent common artefacts."""
        import re

        t = text.strip()
        if not t:
            return t

        # 0. Strip all quote characters — XTTS does not use them for prosody/intonation
        #    and they frequently cause gibberish tails (the tokenizer sees them as
        #    continuation signals). All variants removed:
        #    " "  straight double
        #    " "  curly double open/close  (U+201C / U+201D)
        #    « »  guillemets double        (U+00AB / U+00BB)
        #    ‹ ›  guillemets single        (U+2039 / U+203A)
        #    ‟ „  low double quotes        (U+201F / U+201E)
        # NOTE: curly single quotes U+2018 ' and U+2019 ' are intentionally KEPT —
        # U+2019 doubles as the apostrophe in contractions (You've, don't, it's).
        # Stripping them breaks pronunciation. Only double-quote variants are removed.
        _QUOTES = '""\u201c\u201d\u00ab\u00bb\u2039\u203a\u201f\u201e'
        t = t.translate(str.maketrans('', '', _QUOTES))

        # 1. Ellipsis → comma (produces a natural pause in speech rather than "dot")
        #    Using comma instead of period because XTTS treats comma as "sentence continues"
        #    which gives a natural hesitation beat — matches the feel of "..." in prose.
        t = re.sub(r'\.{2,}', ',', t)

        # 2. Trailing colon/semicolon → period (complete utterance)
        t = re.sub(r'[;:]\s*$', '.', t)

        # 3. Short word (1-3 chars) + period at end → strip period
        #    Prevents XTTS vocalising "dot" on "No." "It." "so." etc.
        #    Extended to 4-char words ending in common stop patterns ("dot" artefact
        #    community fix — coqui-ai/TTS #2883: period on short final word = "dot" spoken)
        t = re.sub(r'(?<!\w)(\w{1,4})\.$', r'\1', t)

        # 4. Clean up double punctuation
        t = re.sub(r'([.!?])\s*[.!?,]+', r'\1', t)
        t = re.sub(r',\s*[,]+', ',', t)

        # 5. Ensure terminal punctuation — ALWAYS end with .!? (never comma)
        #    A trailing comma tells XTTS the sentence continues → gibberish
        t = t.rstrip()
        if t and t[-1] == ',':
            t = t[:-1] + '.'
        # Quotes are already stripped above, so only .!? and comma need handling here
        if t and t[-1] not in '.!?':
            t += '.'
        # Trailing space gives the BPE tokenizer a clean boundary signal before EOS
        t += ' '

        return t

    @staticmethod
    def _trim_anchor_token(wav_path: Path, anchor_duration_ms: int = 400) -> None:
        """Trim the trailing anchor token ('Mm.') from a synthesised chunk.

        The anchor is always the last spoken element — typically 200-350ms.
        We trim up to anchor_duration_ms from the end, stopping at the first
        frame above -50 dBFS when scanning backwards (= end of real speech).
        This never touches real speech because 'Mm' is appended AFTER it.
        """
        from pydub import AudioSegment
        import numpy as np

        audio = AudioSegment.from_wav(str(wav_path))
        if len(audio) < anchor_duration_ms + 100:
            return  # too short to trim safely

        # Only look at the last anchor_duration_ms window
        tail = audio[-anchor_duration_ms:]
        mono = tail.set_channels(1)
        samples = np.array(mono.get_array_of_samples(), dtype=np.float32)
        sr = mono.frame_rate
        frame_ms = 10
        frame_samples = int(sr * frame_ms / 1000)
        if frame_samples == 0:
            return

        n_frames = len(samples) // frame_samples
        # Find where real speech ends (scan backwards from end of tail)
        cut_frame = n_frames  # default: don't cut
        for i in range(n_frames - 1, -1, -1):
            frame = samples[i * frame_samples: (i + 1) * frame_samples]
            rms = float(np.sqrt(np.mean(frame ** 2))) if len(frame) else 0.0
            db = 20.0 * np.log10(rms / 32768.0) if rms > 0 else -96.0
            if db > -50.0:
                # This frame has energy — real speech ends here
                cut_frame = i + 1
                break

        cut_ms_in_tail = cut_frame * frame_ms
        # Keep 80ms of natural decay after last energy frame
        cut_ms_in_tail = min(cut_ms_in_tail + 80, anchor_duration_ms)

        # Only trim if we'd remove at least 80ms
        trim_ms = anchor_duration_ms - cut_ms_in_tail
        if trim_ms >= 80:
            trimmed = audio[: len(audio) - trim_ms]
            trimmed.export(str(wav_path), format="wav")

    def _vad_trim_tail(self, wav_path: Path, post_speech_pad_ms: int = 300) -> None:
        """Trim gibberish/silence tail using Silero VAD.

        XTTS v2 frequently appends voiced gibberish after the last real word.
        Energy-based and silence-based trimmers can't catch *voiced* artifacts.
        Silero VAD detects actual speech probability per frame, letting us find
        exactly where the last real spoken word ends.

        post_speech_pad_ms: keep this many ms after the last detected speech frame
        to preserve natural phoneme decay. 150ms is enough for a clean stop without
        letting short gibberish bursts bleed in.
        """
        import torch
        import soundfile as sf
        import numpy as np

        vad_model = self._get_vad_model()

        # Read audio — Silero VAD needs 16 kHz mono
        audio_24k, sr = sf.read(str(wav_path), dtype="float32")
        if audio_24k.ndim > 1:
            audio_24k = audio_24k.mean(axis=1)  # stereo → mono

        # Resample 24kHz → 16kHz using torchaudio (already a Coqui dep)
        import torchaudio.functional as AF
        audio_tensor = torch.from_numpy(audio_24k).unsqueeze(0)
        audio_16k = AF.resample(audio_tensor, orig_freq=sr, new_freq=16000).squeeze(0)

        # Run Silero VAD — get speech timestamps at 16 kHz
        from silero_vad import get_speech_timestamps
        speech_ts = get_speech_timestamps(
            audio_16k,
            vad_model,
            sampling_rate=16000,
            threshold=0.15,               # very permissive — ensures trailing fricatives/plosives ("ce", "t", "d") are kept
            min_speech_duration_ms=60,    # catch short real words (e.g. "Fast.", "No.")
            min_silence_duration_ms=40,   # small gap between word and gibberish is enough to split them
        )

        if not speech_ts:
            # No speech detected at all — leave untouched
            return

        # Last speech frame end in 16kHz samples → convert back to 24kHz samples
        last_speech_end_16k = speech_ts[-1]["end"]
        scale = sr / 16000
        last_speech_end_24k = int(last_speech_end_16k * scale)

        # Add natural decay pad
        pad_samples = int(post_speech_pad_ms / 1000.0 * sr)
        cut_sample = min(last_speech_end_24k + pad_samples, len(audio_24k))

        # Only trim if we'd actually remove something meaningful (>80ms)
        if cut_sample < len(audio_24k) - int(0.08 * sr):
            trimmed = audio_24k[:cut_sample]
            sf.write(str(wav_path), trimmed, sr)
            audio_24k = trimmed  # update for second pass below

        # ── Second pass: silence-based trim on whatever VAD left ──────────────
        # Catches very brief micro-gibberish bursts (< 60ms) that slip past VAD's
        # min_speech_duration_ms floor. Uses -38 dBFS — aggressive enough to catch
        # mumbled artefacts but won't clip natural word-final fricatives (which sit
        # around -25 to -30 dBFS).
        from pydub import AudioSegment
        from pydub.silence import detect_leading_silence
        pydub_audio = AudioSegment.from_wav(str(wav_path))
        reversed_audio = pydub_audio.reverse()
        sil_ms = detect_leading_silence(reversed_audio, silence_threshold=-33.0)
        keep_ms = 120  # always keep 120ms of natural tail decay
        trim_ms = sil_ms - keep_ms
        if trim_ms > 60:
            pydub_audio = pydub_audio[:len(pydub_audio) - trim_ms]
            pydub_audio.export(str(wav_path), format="wav")

    def _synthesize_chunk(self, text: str, speaker_wav: Path, output_path: Path) -> Path:
        """Synthesize a single text chunk to audio, with VAD-based tail trimming."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._clean_text_for_tts(text)

        tts = self._get_tts_model()

        chars_per_second = 13.0
        expected_sec = len(text) / chars_per_second
        max_allowed_sec = expected_sec + 2.0

        attempts = [
            (self.temperature, self.repetition_penalty),
            (max(self.temperature - 0.1, 0.5), self.repetition_penalty),
            (0.5, 1.5),  # last resort: very stable
        ]

        for attempt_num, (temp, rep_pen) in enumerate(attempts):
            tts.tts_to_file(
                text=text,
                speaker_wav=str(speaker_wav),
                language=self.language,
                file_path=str(output_path),
                temperature=temp,
                repetition_penalty=rep_pen,
                length_penalty=self.length_penalty,
                top_k=self.top_k,
                top_p=self.top_p,
                speed=0.95,
                # gpt_cond_len=12: longer conditioning stabilises GPT token generation
                # at sentence ends (coqui-ai/TTS #3285)
                gpt_cond_len=12,
                gpt_cond_chunk_len=4,
            )

            from pydub import AudioSegment
            audio = AudioSegment.from_wav(str(output_path))
            actual_sec = len(audio) / 1000.0

            if actual_sec <= max_allowed_sec:
                break
            else:
                print(f"   ⚠️  Chunk duration {actual_sec:.1f}s > expected {expected_sec:.1f}s "
                      f"— retrying (attempt {attempt_num + 2})...")

        # ── VAD tail trim ────────────────────────────────────────────────────
        # Strip any voiced gibberish after the last real word using Silero VAD.
        # This is the community-proven fix for XTTS v2 artifact tails — energy/
        # silence-based trimmers miss *voiced* artifacts; VAD detects them.
        self._vad_trim_tail(output_path)

        return output_path

    def run(
        self,
        str_input_txt_path: str,
        str_output_path: str = "outputs/audio",
        b_keep_chunks: bool = False,
        normalize: bool = True,
    ) -> dict[str, Path]:
        """
        Generate podcast from text script.

        Args:
            str_input_txt_path: Path to input text script (REQUIRED)
            str_output_path: Output directory for audio files (default: "outputs/audio")
            b_keep_chunks: Keep individual chunk WAV files (default: False)
            normalize: Apply loudness normalization (default: True)

        Returns:
            Dictionary with paths to generated files: {"wav": Path, "mp3": Path}
        """
        # Validate input
        input_path = Path(str_input_txt_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Script not found: {input_path}")

        # Setup output directory
        output_dir = Path(str_output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        chunk_dir = output_dir / "chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*80}")
        print(f"🎙️  PODCAST GENERATION")
        print(f"{'='*80}\n")

        # Load script
        print(f"📄 Script: {input_path}")
        script_text = input_path.read_text(encoding="utf-8")
        print(f"   Length: {len(script_text)} characters\n")

        # Prepare voice
        print(f"🎤 Preparing voice sample...")
        voice_wav = self._prepare_voice_reference(output_dir)
        print()

        # Chunk text (preserving [pause:N] markers)
        print(f"✂️  Chunking text...")
        script_items = chunk_script(
            script_text,
            max_chars_per_chunk=self.max_chars_per_chunk,
            language=self.language,
        )
        text_chunks = [item for item in script_items if isinstance(item, str)]
        print(f"   Created {len(text_chunks)} text chunks\n")

        # Synthesize text chunks only
        print(f"🔊 Synthesizing audio chunks...")
        chunk_index = 0
        audio_items: list[Path | PauseMarker] = []

        for item in script_items:
            if isinstance(item, PauseMarker):
                audio_items.append(item)
                print(f"   [pause] {item.ms}ms silence queued")
            else:
                chunk_path = chunk_dir / f"chunk_{chunk_index:04d}.wav"
                print(f"   [{chunk_index+1}/{len(text_chunks)}] Chunk {chunk_index:04d} ({len(item)} chars)...")
                self._synthesize_chunk(item, voice_wav, chunk_path)
                audio_items.append(chunk_path)
                chunk_index += 1

        print(f"   ✅ Generated {chunk_index} audio files\n")

        # Concatenate (with pause silences in position)
        print(f"🔗 Concatenating audio...")
        output_wav = output_dir / "final_episode.wav"
        concat_audio(audio_items, output_wav, fade_ms=self.chunk_fade_ms)

        # Normalize
        final_audio = output_wav
        if normalize:
            print(f"\n📊 Normalizing audio...")
            normalized_path = output_dir / "final_episode_normalized.wav"
            normalize_audio(output_wav, normalized_path)
            final_audio = normalized_path

        # Export MP3
        print(f"\n💾 Exporting MP3...")
        output_mp3 = output_dir / "final_episode.mp3"
        export_mp3(final_audio, output_mp3, bitrate=self.mp3_bitrate)

        # Cleanup chunks if requested
        if not b_keep_chunks:
            print(f"\n🧹 Cleaning up chunks...")
            shutil.rmtree(chunk_dir, ignore_errors=True)
            print(f"   Removed {chunk_index} chunk files")

        # Results
        results = {
            "wav": final_audio,
            "mp3": output_mp3,
        }

        print(f"\n{'='*80}")
        print(f"✅ PODCAST COMPLETE")
        print(f"{'='*80}\n")
        print(f"Outputs:")
        for key, path in results.items():
            print(f"  {key.upper()}: {path}")
        print()

        return results

