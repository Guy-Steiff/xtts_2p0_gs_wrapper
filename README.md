# xtts_2p0_gs_wrapper

A production-grade Python wrapper around [Coqui XTTS v2](https://github.com/coqui-ai/TTS) for generating long-form narration audio with voice cloning — fully offline, no API keys required.

Built to solve the real-world gaps in the raw XTTS API: text chunking, gibberish artifact suppression, timed pauses, voice reference preprocessing, loudness normalization, and MP3 export.

---

## Features

- **IDE-runnable** — no CLI arguments needed, just run `demo_class_usage.py`
- **Zero-shot voice cloning** — provide any 10–30s audio clip of a voice; XTTS clones it
- **Automatic text chunking** — splits long scripts at sentence/clause boundaries within XTTS's 250-char hard limit
- **`[pause:N]` markers** — insert precise millisecond silences anywhere in the script
- **Silero VAD tail trimming** — removes voiced gibberish artifacts after sentences using voice activity detection
- **Silence-based second-pass trim** — catches micro-artifacts VAD misses
- **Text sanitization** — normalizes punctuation, strips problematic quote characters, ensures XTTS-safe terminals
- **Loudness normalization** — FFmpeg `loudnorm` (linear mode) to broadcast standard
- **MP3 export** — 192k CBR output alongside WAV


---

## Installation

### Requirements

- Python 3.9–3.11 (3.11 recommended)
- FFmpeg installed and on PATH (`brew install ffmpeg` on macOS)

### Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** On macOS with pyenv Python (missing `_lzma`), the `demo_class_usage.py` includes an automatic patch using `backports.lzma`. No manual action needed.

### First run

The XTTS v2 model (~1.8GB) downloads automatically on first use to:
```
~/Library/Application Support/tts/tts_models--multilingual--multi-dataset--xtts_v2/
```
This is a one-time download per machine.

---

## Quick Start

```python
from podcast_generator import PodcastGenerator

generator = PodcastGenerator(
    voice_sample_path="sample_voices/sample_voice.aac",
    language="en",
    temperature=0.65,
    repetition_penalty=2.0,
)

results = generator.run(
    str_input_txt_path="scripts/example_episode.txt",
    str_output_path="outputs/my_episode",
    b_keep_chunks=False,
    normalize=True,
)

print(f"MP3: {results['mp3']}")
print(f"WAV: {results['wav']}")
```

Or just run the demo directly in your IDE:

```bash
python demo_class_usage.py
```

---

## Script Format

Plain text files. Two special markers are supported:

### Pause markers

Insert silence of N milliseconds between sentences:

```
The results were clear.
[pause:500]
Everything had changed.
[pause:1000]
Nothing would be the same again.
```

### Line breaks

Blank lines between paragraphs are handled naturally — the chunker merges sentences up to the character limit.

### How `[pause:N]` works internally

`[pause:N]` markers are **not** synthesized by XTTS and do not appear in any chunk WAV file. They exist purely as in-memory `PauseMarker` objects in the pipeline. Pauses are injected as silent `AudioSegment` regions during the final concatenation step — so they only exist in `final_episode.wav` and `final_episode.mp3`.

**Implication**: if you manually concatenate the chunk files from the `chunks/` folder (e.g. for a preview during a long run), the resulting audio will be missing all pauses. Use the following Python snippet to concatenate chunks into a preview MP3:

```python
import os
import glob

# Set to your output folder timestamp
str_output_dir = '/path/to/your/output_folder'

lst_paths = sorted(glob.glob(os.path.join(str_output_dir, 'chunks', '*.wav')))

concat_txt = os.path.join(str_output_dir, 'chunks_preview.txt')
with open(concat_txt, 'w') as fid:
    for p in lst_paths:
        fid.write(f"file '{p}'\n")

os.system(
    f"ffmpeg -f concat -safe 0 -i \"{concat_txt}\" "
    f"-acodec libmp3lame -y \"{os.path.join(str_output_dir, 'chunks_preview.mp3')}\""
)
```

> ⚠️ The resulting `chunks_preview.mp3` will contain speech only — all `[pause:N]` silences will be absent. The final output with pauses is only available after the full pipeline run completes.

---

## Pronunciation Tricks & Known XTTS Quirks

XTTS v2 mispronounces certain words and does not always respond naturally to punctuation. The workarounds below were discovered through production use.

### Pause substitutes

An em-dash `—` or a spaced hyphen ` - ` inside a sentence acts as a natural short pause (~200–350ms), equivalent to roughly `[pause:300]`. This is useful for dramatic beats mid-sentence without breaking the chunk:

```
He opened the door — and stopped.
The answer was simple - impossibly simple.
```

For longer explicit pauses between sentences, use `[pause:N]` markers as documented above.

### Pronunciation dictionary

Some words are mispronounced by XTTS v2. Entries marked ✅ were confirmed through production runs with this wrapper. Entries marked ⚠️ are plausible based on general TTS phonetics but have not been verified against XTTS v2 specifically — treat them as starting points to test.

| Intended word | XTTS output | Workaround spelling |
|---|---|---|
| `debug` | "deh-bug" (clipped d) | `dee-bug` |
| `neutral` | "noy-tral" / "noo-tral" | `nyoo-truhl` or `neut-ruhl` |
| `reject` (noun/adj sense, e.g. "a reject") | sounds the same as the verb | `ree-ject` |

> Both entries above were confirmed through production runs with this wrapper. Contributions welcome — if you discover additional mispronunciations or workarounds, please open a PR.

> Results may vary by voice reference sample.

### Planned: automatic text normalizer

A pre-processing step that automatically converts known problematic words to their XTTS-friendly phonetic equivalents before synthesis is planned. It would apply the dictionary above as a text substitution pass, configurable per-project via a `pronunciation_map` dict parameter.

---

## `PodcastGenerator` — Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `voice_sample_path` | `str\|Path` | **required** | Path to voice reference audio (AAC, WAV, MP3, M4A) |
| `language` | `str` | `"en"` | Language code. Supported: `en es fr de it pt pl tr ru nl cs ar zh-cn hu ko ja hi` |
| `max_chars_per_chunk` | `int` | `230` | Max characters per synthesis chunk. XTTS hard limit is 250 for English — keep margin. |
| `sample_rate` | `int` | `24000` | Output audio sample rate in Hz |
| `temperature` | `float` | `0.85` | Synthesis randomness (0.1–1.0). Lower = fewer artifacts, less expressive. **Tuned sweet spot: `0.65`** |
| `repetition_penalty` | `float` | `7.0` | Penalizes repeated tokens. High values cause mid-word cutoffs on polysyllabic words. **Tuned sweet spot: `2.0`** |
| `length_penalty` | `float` | `1.0` | Speech speed control |
| `top_k` | `int` | `60` | Sampling diversity |
| `top_p` | `float` | `0.92` | Nucleus sampling threshold |
| `chunk_fade_ms` | `int` | `10` | Crossfade between chunks in ms. Set to `0` for clean cuts. |
| `mp3_bitrate` | `str` | `"192k"` | MP3 export bitrate |
| `model_name` | `str` | `"tts_models/multilingual/multi-dataset/xtts_v2"` | TTS model identifier |
| `voice_max_duration` | `float` | `30.0` | Trim voice reference to this many seconds. XTTS sweet spot: 10–30s |
| `voice_start_seconds` | `float` | `0.0` | Skip this many seconds at the start of the voice reference (skip intro noise) |

### `generator.run()` — Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `str_input_txt_path` | `str` | **required** | Path to input script `.txt` file |
| `str_output_path` | `str` | `"outputs/audio"` | Output directory |
| `b_keep_chunks` | `bool` | `False` | Keep individual chunk WAV files after completion |
| `normalize` | `bool` | `True` | Apply FFmpeg loudness normalization |

### Return value

```python
{
    "wav": Path,  # final_episode_normalized.wav (or final_episode.wav if normalize=False)
    "mp3": Path,  # final_episode.mp3
}
```

---

## Recommended Parameter Settings

These were tuned over many production runs:

```python
generator = PodcastGenerator(
    voice_sample_path="sample_voices/sample_voice.aac",
    language="en",
    max_chars_per_chunk=230,
    sample_rate=24000,
    temperature=0.65,        # lower = fewer gibberish tails
    repetition_penalty=2.0,  # lower = no mid-word cutoffs on long words
    top_p=0.92,
    chunk_fade_ms=0,
    voice_max_duration=25.0,
    voice_start_seconds=0.0,
)
```

---

## Voice Reference Guidelines

- **Duration**: 10–30 seconds. 25s is the sweet spot.
- **Content**: Clean speech, no music or background noise
- **Format**: AAC, WAV, MP3, M4A — all accepted (converted internally)
- **Quality**: The more expressive and natural the reference, the better the cloned voice
- **Tip**: Record yourself reading a neutral paragraph at a natural pace

A sample voice is included in `sample_voices/sample_voice.aac`.

---

## Project Structure

```
podcasts/
├── podcast_generator.py      # Main PodcastGenerator class
├── demo_class_usage.py       # Ready-to-run example (configure and hit Run)
├── config.py                 # Global defaults (FFMPEG_BIN, SAMPLE_RATE, etc.)
├── requirements.txt
├── sample_voices/
│   └── sample_voice.aac      # Bundled voice reference sample
├── scripts/
│   └── example_episode.txt   # Sample narration script with [pause:N] markers
├── audio/
│   ├── concat.py             # Audio concatenation + MP3 export
│   └── normalize.py          # FFmpeg loudnorm normalization
├── tts/
│   ├── chunking.py           # Text → XTTS-safe chunks + [pause:N] parsing
│   └── synthesize.py         # Low-level synthesis helpers
├── voice/
│   ├── preprocess.py         # Voice reference preprocessing (resample, trim)
│   └── voice_loader.py
└── pipeline/
    └── run_episode.py        # Alternative CLI pipeline runner
```

---

## Known Limitations & Planned Solutions

### 1. Gibberish artifacts after sentences
**Status**: Partially mitigated  
**What happens**: XTTS v2's autoregressive GPT decoder occasionally generates extra voiced tokens after the final word — heard as short nonsense syllables. The vast majority of occurrences happen on chunks ending with `.` — particularly **very short chunks** (single words or short phrases like `"Fast."`, `"Consistent."`, `"No."`). On these, XTTS has little context to work with and the model effectively hallucinates continuation tokens after the period. Longer, well-formed sentences are significantly less affected.  
**Current mitigations**:
- **Duration-based retry** — after synthesis, the chunk duration is compared against an estimated expected duration (`chars / 13.0 chars-per-second`). If the actual audio exceeds the estimate by more than 2 seconds, the chunk is re-synthesized at a lower temperature (up to 3 attempts). This catches chunks where XTTS ran significantly over, which strongly correlates with a gibberish tail being present.
- Silero VAD detects last real speech frame → trims everything after + 300ms pad
- Second-pass silence trim at -33 dBFS catches VAD misses
- `gpt_cond_len=12, gpt_cond_chunk_len=4` (community fix, coqui-ai/TTS #3285)
- `temperature=0.65` reduces hallucination probability
- All quote characters stripped (were triggering continuation tokens)

**Planned**: Whisper closed-loop validation — synthesize → transcribe → compare WER → retry bad chunks automatically. Will be implemented as an optional flag `use_whisper_validation=True`.

**Current workaround**: Listen through the output, identify the timestamp of any remaining gibberish, and cut it out manually using FFmpeg with precise `-ss` and `-to` intervals. For example:
```bash
# Extract clean audio from 0s to 1:23.4, skipping a gibberish burst at 1:23.4–1:23.9
ffmpeg -i final_episode.mp3 -ss 0 -to 83.4 part1.mp3
ffmpeg -i final_episode.mp3 -ss 83.9 part2.mp3

# Build the concat list — macOS / Linux
printf "file 'part1.mp3'\nfile 'part2.mp3'\n" > parts.txt

# Build the concat list — Windows (PowerShell)
"file 'part1.mp3'`nfile 'part2.mp3'" | Out-File -Encoding ascii parts.txt

# Build the concat list — Windows (CMD)
echo file 'part1.mp3' > parts.txt && echo file 'part2.mp3' >> parts.txt


# Join the parts
ffmpeg -f concat -safe 0 -i parts.txt -c copy final_clean.mp3
```
This is tedious but effective for the rare occurrences that pass all automatic filters.

### 2. Occasional mid-word cutoffs
**Status**: Largely resolved  
**What happens**: Long polysyllabic words (maintenance, incompetence) get clipped mid-syllable.  
**Fix**: `repetition_penalty` lowered from 7.0 → 2.0. High penalty penalizes repeating phoneme patterns, which describes the internal structure of long words.

### 3. No emotion/mood control
**Status**: By design — XTTS v2 is a neutral narration model  
**What happens**: `!` and `?` produce limited prosodic variation; dramatic scenes sound flat.  
**Planned**: Integration of **Dia-TTS** (Nari Labs, 2025, Apache 2.0) for emotional scenes. Dia supports inline emotion tokens `(laughs)`, `(sighs)`, `(nervous)` and two-speaker dialogue `[S1]`/`[S2]`. The plan is a hybrid pipeline: XTTS for narrator voice cloning, Dia for expressive character dialogue, mixed in the existing concat pipeline.

### 4. Performance on CPU
**What happens**: XTTS v2 runs ~10–30s per chunk on Intel CPU (no GPU acceleration on Intel Mac).  
**Options**:
- Apple Silicon (M1+): enable MPS backend for 5–8× speedup with zero code changes
- NVIDIA GPU: set `gpu=True` in `_get_tts_model()`
- Cloud GPU: RunPod/Lambda Labs T4 ~$0.20/hr, same code

### 5. Coqui TTS is archived
Coqui AI shut down in January 2024. The model and code remain fully functional. The active community fork is [idiap/coqui-ai-TTS](https://github.com/idiap/coqui-ai-TTS).

---

## Roadmap

- [ ] **Whisper closed-loop validation** — auto-retry chunks with WER > threshold
- [ ] **Dia-TTS integration** — emotional voice support via `[emotion:sad]` script tags
- [ ] **Multi-voice/character support** — `[character:name]` tags routing to different voice references
- [ ] **Background music layer** — `[music:file.mp3:0.15]` tag for ambient underscoring
- [ ] **FastAPI REST wrapper** — serve the generator as a local API endpoint

---

## Dependencies

Key packages (see `requirements.txt` for full list):

| Package | Purpose |
|---|---|
| `TTS` (Coqui) | XTTS v2 model and inference |
| `torch`, `torchaudio` | PyTorch backend |
| `silero-vad` | Voice activity detection for tail trimming |
| `pydub` | Audio concatenation and manipulation |
| `soundfile` | WAV I/O for VAD pipeline |
| `transformers==4.33.0` | Required pinned version (newer versions break XTTS) |
| `ffmpeg` (system) | Normalization and MP3 export |

---

## License

MIT License — see [LICENSE](LICENSE)

This project wraps [Coqui TTS](https://github.com/coqui-ai/TTS) which is licensed under Mozilla Public License 2.0. The XTTS v2 model weights are subject to Coqui's non-commercial use terms.

