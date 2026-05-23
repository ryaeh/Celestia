"""Load personality packs from personalities/ folder."""

from __future__ import annotations

from pathlib import Path

import yaml

from celestia_core.config import ROOT, get

_BASE = """You are {name}, a companion AI assistant on this Windows PC — not a generic smart speaker.
Be natural and warm when appropriate; stay concise for tasks.
For greetings or chat, reply in plain text only — no tools unless needed.
Never open apps, CMD, browsers, or URLs unless the user clearly asked to open something specific.
For Notepad on Windows, use open_path with 'notepad' or 'not defteri' only — never write.exe or WordPad.
Never use example.com or made-up URLs.
When the user asks you to remember something, call memory_add with their exact words (user facts only).
To correct memory: memory_list, memory_delete (wrong entry), then memory_add (correct fact).
When answering about preferences, use stored facts in system context first; do not invent.
On greetings (hi/hello), do not mention stored preferences unless the user asked."""


def _personality_dir() -> Path:
    rel = get("personality.dir", "personalities")
    p = Path(rel)
    return p if p.is_absolute() else ROOT / rel


def load_personality_block() -> str:
    active = get("personality.active", "default")
    if not active:
        return ""

    folder = _personality_dir()
    for ext in (".yaml", ".yml"):
        path = folder / f"{active}{ext}"
        if path.exists():
            return _from_yaml(path)
    md = folder / f"{active}.md"
    if md.exists():
        return md.read_text(encoding="utf-8").strip()
    return ""


def _from_yaml(path: Path) -> str:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parts: list[str] = []

    name = data.get("name") or get("app.display_name", "Celestia")
    parts.append(f"Your name is {name}.")

    if data.get("role"):
        parts.append(str(data["role"]).strip())

    if data.get("tone"):
        parts.append(f"Tone: {data['tone']}.")

    if data.get("speech_style"):
        parts.append(str(data["speech_style"]).strip())

    if data.get("emotion_guidance") and get("voice.tts.emotion_tags", True):
        parts.append(str(data["emotion_guidance"]).strip())

    rules = data.get("rules") or []
    if rules:
        parts.append("Rules:\n" + "\n".join(f"- {r}" for r in rules))

    return "\n\n".join(parts)


def build_system_prompt() -> str:
    display = get("app.display_name", "Celestia")
    prompt = _BASE.format(name=display)
    extra = load_personality_block()
    if extra:
        prompt = prompt + "\n\n--- Personality ---\n" + extra
    return prompt
