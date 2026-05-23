from __future__ import annotations

import re
from pathlib import Path

import ollama
from ollama import ResponseError

from celestia_core.config import get
from celestia_core.resources import free_for_vision

TEXT_TRIGGERS = re.compile(
    r"\b(read|text|file|line|requirements|error|message|code|transcribe|ocr|"
    r"cmd|command|terminal|console|powershell|output|log|stdout|stderr|"
    r"what does it say|what's written|what is written|list|content|package|import|"
    r"copy|verbatim|exactly|komut|defteri|ekran)\b",
    re.I,
)

TRANSCRIBE_ONLY = """You are an OCR assistant. This image is a terminal, CMD, code editor, or document.

Copy EVERY line of visible text exactly as shown, top to bottom.
Use a fenced ```text code block.
Rules:
- Do NOT describe icons, window borders, or guess the application.
- Do NOT invent lines that are not visible.
- If unreadable, write [unclear] for that fragment only.
- Preserve paths, errors, version numbers, and punctuation."""

GENERAL_PROMPT = """Analyze this screenshot for the user.

Rules:
- Only describe what is actually visible. Do not invent UI elements, buttons, or code.
- If unsure, say "unclear".
- Answer the user's question directly.

Question: {question}"""

TEXT_ANSWER_FROM_TRANSCRIPT = """You have an exact transcript from a screenshot (trust it over imagination).

TRANSCRIPT:
{transcript}

USER QUESTION: {question}

Answer using ONLY the transcript. Quote relevant lines. If the answer is not in the transcript, say so."""


def _is_text_task(question: str) -> bool:
    if get("vision.force_text_mode", False):
        return True
    return bool(TEXT_TRIGGERS.search(question))


def _build_prompt(question: str) -> str:
    return GENERAL_PROMPT.format(question=question) + "\n\nKeep the answer concise."


def _text_models() -> list[str]:
    models: list[str] = []
    for key in ("vision.text_model", "llm.vision_text_model"):
        m = get(key, "")
        if m and m not in models:
            models.append(m)
    return models or ["qwen2.5vl:7b"]


def _fallback_models() -> list[str]:
    models = _text_models()
    for m in (
        get("llm.vision_model", "llama3.2-vision:11b"),
        get("llm.vision_fast_model", "moondream"),
    ):
        if m and m not in models:
            models.append(m)
    return models


def _chat_vision(model: str, image_path: Path, prompt: str, *, num_predict: int, temperature: float) -> str:
    response = ollama.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [str(image_path)],
            }
        ],
        options={"temperature": temperature, "num_predict": num_predict},
    )
    return (response["message"].get("content") or "").strip()


def _chat_text_only(model: str, prompt: str) -> str:
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={
            "temperature": float(get("vision.temperature", 0.1)),
            "num_predict": int(get("vision.max_tokens", 2048)),
        },
    )
    return (response["message"].get("content") or "").strip()


def _two_pass_text(image_path: Path, question: str) -> str:
    """Transcribe with vision model, answer from text-only chat (less hallucination)."""
    from skills.vision.preprocess import enhance_for_text

    img = enhance_for_text(image_path) if get("vision.preprocess_text", True) else image_path
    vision_model = _text_models()[0]
    chat_model = get("llm.chat_model", "qwen2.5:7b")

    print(f"[vision] pass 1/2: transcribe with {vision_model}")
    free_for_vision()
    transcript = _chat_vision(
        vision_model,
        img,
        TRANSCRIBE_ONLY,
        num_predict=int(get("vision.transcribe_tokens", 4096)),
        temperature=0.0,
    )
    if not transcript or len(transcript) < 8:
        raise RuntimeError("Transcription empty — recrop tighter on the text area.")

    print(f"[vision] pass 2/2: answer with {chat_model} (text only, no image)")
    answer = _chat_text_only(
        chat_model,
        TEXT_ANSWER_FROM_TRANSCRIPT.format(transcript=transcript, question=question),
    )
    return f"### Transcript\n{transcript}\n\n### Answer\n{answer}"


def analyze_image(image_path: Path, question: str) -> str:
    text_mode = _is_text_task(question)
    if text_mode:
        print("[vision] text mode")
        if get("vision.two_pass_text", True):
            try:
                return _two_pass_text(image_path, question)
            except (ResponseError, RuntimeError) as e:
                print(f"[vision] two-pass failed ({e}), trying single-pass...")

    prompt = _build_prompt(question)
    models = _fallback_models() if not text_mode else _text_models()
    if text_mode and get("llm.vision_model") not in models:
        pass  # text: prefer qwen only; add fallback only on failure below

    free_for_vision()
    last_err: Exception | None = None

    for i, model in enumerate(models):
        print(f"[vision] analyzing with {model}...")
        try:
            if text_mode:
                from skills.vision.preprocess import enhance_for_text

                img = enhance_for_text(image_path) if get("vision.preprocess_text", True) else image_path
                return _chat_vision(
                    model,
                    img,
                    TRANSCRIBE_ONLY + f"\n\nThen answer: {question}",
                    num_predict=int(get("vision.max_tokens", 4096)),
                    temperature=float(get("vision.temperature", 0.0)),
                )
            return _chat_vision(
                model,
                image_path,
                prompt,
                num_predict=int(get("vision.max_tokens", 1536)),
                temperature=float(get("vision.temperature", 0.3)),
            )
        except ResponseError as e:
            last_err = e
            err = str(e).lower()
            if i < len(models) - 1 and ("memory" in err or "status code: 500" in err):
                print(f"[vision] {model} failed ({e}), trying {models[i + 1]}...")
                free_for_vision()
                continue
            raise

    if last_err:
        raise last_err
    raise RuntimeError("No vision model configured")
