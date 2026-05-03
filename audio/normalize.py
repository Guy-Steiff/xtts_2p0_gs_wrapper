from __future__ import annotations

import subprocess
from pathlib import Path

from config import FFMPEG_BIN, SAMPLE_RATE


def normalize_audio(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(input_path),
        "-af",
        # loudnorm with linear=true applies a single static gain offset (like a volume knob)
        # rather than dynamic per-sample compression. This preserves silence gaps exactly —
        # the dynamic mode was bridging over short [pause:N] silences between chunks.
        "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true",
        "-ar",
        str(SAMPLE_RATE),
        str(output_path),
    ]

    print(f"Normalizing audio: {input_path.name}...")
    subprocess.run(command, capture_output=True, check=True)
    print(f"Normalized audio saved to: {output_path}")
    return output_path

