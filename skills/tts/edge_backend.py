from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from celestia_core.config import ROOT, get


async def _synthesize(text: str, out: Path) -> None:
    import edge_tts

    voice = get("voice.tts.edge.voice", "en-US-GuyNeural")
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(out))


def speak_to_file(text: str, out_path: str | Path) -> Path:
    out = Path(out_path)
    asyncio.run(_synthesize(text, out))
    return out


def play_prompt(text: str, *, wait_seconds: float = 4.0) -> None:
    """Short confirm TTS (MP3) without loading Orpheus."""
    out_dir = Path(ROOT) / "outputs"
    out_dir.mkdir(exist_ok=True)
    mp3 = out_dir / "atlas_prompt.mp3"
    asyncio.run(_synthesize(text, mp3))
    path = str(mp3.resolve()).replace("'", "''")

    if sys.platform != "win32":
        os.startfile(mp3)
        return

    ps = f"""
Add-Type -AssemblyName presentationCore
$p = New-Object System.Windows.Media.MediaPlayer
$p.Open('{path}')
$p.Play()
Start-Sleep -Seconds {int(wait_seconds)}
$p.Close()
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        # Fallback: default app (non-blocking)
        try:
            os.startfile(mp3)
        except OSError:
            pass
        print("[vision] confirm audio: read the text above (audio playback unavailable)")
