from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from celestia_core.config import ROOT, get


def speak(text: str, *, play: bool = True) -> Path:
    text = text.strip()
    if not text:
        raise ValueError("empty text")

    out_dir = Path(ROOT) / "outputs"
    out_dir.mkdir(exist_ok=True)
    wav_path = out_dir / "celestia_last_reply.wav"

    provider = get("voice.tts.provider", "orpheus").lower()
    backend = get("voice.tts.orpheus.backend", "local").lower()
    data: bytes | None = None

    if provider == "orpheus":
        try:
            if backend == "local":
                from skills.tts import orpheus_local

                data = orpheus_local.synthesize_wav(text)
            else:
                from skills.tts import orpheus_backend

                data = orpheus_backend.synthesize_wav(text)
                orpheus_backend.stop_if_idle()
        except Exception as e:
            print(f"[tts] Orpheus failed ({e}), using edge-tts")

    if data is None:
        from skills.tts import edge_backend

        edge_backend.speak_to_file(text, wav_path)
    else:
        wav_path.write_bytes(data)

    if play:
        _play(wav_path)
    return wav_path


def _play(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'(New-Object Media.SoundPlayer "{path}").PlaySync()',
            ],
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0,
        )
