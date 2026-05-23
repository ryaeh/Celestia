#!/usr/bin/env python3
"""Celestia — local companion: chat, memory, voice, screen (with security gates)."""

import argparse
import re
import sys
from pathlib import Path

_OPEN_LINE = re.compile(r"^open\s+(.+)$", re.I)

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from celestia_core.secrets import bootstrap

bootstrap()

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

from celestia_core.agent import run_turn
from celestia_core.cli_help import print_help
from celestia_core.config import get, load_config
from celestia_core.preflight import run_checks
from celestia_core import security


def _prompt_tag() -> str:
    return get("app.display_name", "Celestia").lower()


def main() -> int:
    load_config()
    security.bootstrap_security()

    parser = argparse.ArgumentParser(description="Celestia assistant")
    parser.add_argument("message", nargs="?", help="Single message")
    parser.add_argument("-i", "--interactive", action="store_true", help="Chat loop")
    parser.add_argument("--check", action="store_true", help="Verify Ollama + memory + voice")
    parser.add_argument("--speak", action="store_true", help="Speak replies (TTS)")
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Record mic (~5s), transcribe, reply (add --speak for voice out)",
    )
    parser.add_argument("--seconds", type=float, default=5.0, help="Record duration for --listen")
    parser.add_argument(
        "--voice-loop",
        action="store_true",
        help="Repeat: listen → reply → speak (Ctrl+C to exit)",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="System tray + hotkeys (see config)",
    )
    parser.add_argument(
        "--tray-chat",
        action="store_true",
        help="Tray chat console only (opened automatically from tray menu)",
    )
    parser.add_argument(
        "--forget-memory",
        action="store_true",
        help="Delete all stored memories (Chroma) for this user",
    )
    parser.add_argument(
        "--screen",
        nargs="?",
        const="",
        metavar="QUESTION",
        help="Capture screen (confirm first), analyze with vision model",
    )
    parser.add_argument(
        "--screen-mode",
        choices=("region", "fullscreen", "active_window"),
        default=None,
        help="Capture mode (default from config)",
    )
    parser.add_argument(
        "--arm",
        action="store_true",
        help="Arm PC control (use with a quoted message, e.g. --arm \"open notepad\")",
    )
    parser.add_argument("--disarm", action="store_true", help="Disarm PC control")
    parser.add_argument(
        "--trust-config",
        action="store_true",
        help="Record config.yaml hash (integrity baseline)",
    )
    parser.add_argument(
        "--pick-workspace",
        action="store_true",
        help="Print suggested security.workspaces paths for config.yaml",
    )
    parser.add_argument(
        "--settings",
        action="store_true",
        help="Open minimal settings window (mode, workspaces, audit log)",
    )
    parser.add_argument(
        "--logs",
        type=int,
        nargs="?",
        const=20,
        metavar="N",
        help="Show last N lines of tool audit log (default 20)",
    )
    args = parser.parse_args()

    if args.trust_config:
        print(security.trust_config())
        return 0

    if args.pick_workspace:
        from celestia_core.scope import print_pick_workspace_hint

        print_pick_workspace_hint()
        return 0

    if args.settings:
        from ui.settings_app import run_settings

        run_settings()
        return 0

    if args.logs is not None:
        from ui.settings_app import _tail_jsonl
        from celestia_core.config import ROOT

        rel = get("security.audit_log", "logs/tool_audit.jsonl")
        path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
        print(_tail_jsonl(path, int(args.logs)))
        return 0

    if args.arm:
        security.set_armed(True)
        print("[security] PC control ARMED")
    if args.disarm:
        security.set_armed(False)
        print("[security] PC control disarmed (safe)")

    if args.forget_memory:
        from skills.memory.store import clear_all

        uid = get("app.user_id", "atlas_user")
        print(clear_all(uid))
        return 0

    if args.check:
        return 0 if run_checks() else 1

    speak = args.speak or get("voice.always_speak", False)
    tag = _prompt_tag()

    chat_history: list | None = None
    chat_turns = 0
    consolidate_from = 0

    def _try_consolidate(*, end: bool = False) -> None:
        nonlocal chat_history, consolidate_from
        if not chat_history or not get("memory.session_consolidate", True):
            return
        if end and not get("memory.session_consolidate_on_end", True):
            return
        if not end:
            every = int(get("memory.session_consolidate_every", 4))
            if chat_turns < every or chat_turns % every != 0:
                return
        from skills.memory.session_consolidate import consolidate_session_messages

        uid = get("app.user_id", "atlas_user")
        consolidate_from, stored = consolidate_session_messages(
            chat_history,
            uid,
            start_index=consolidate_from,
        )
        if stored and get("memory.session_consolidate_verbose", True):
            for line in stored:
                print(f"[memory] saved: {line}")

    def handle(text: str, *, source: str = "cli") -> None:
        nonlocal chat_history
        text = text.strip()
        if not text:
            return
        use_session = get("chat.session_enabled", True)
        if use_session:
            reply, chat_history = run_turn(
                text, speak=speak, source=source, history=chat_history
            )
        else:
            reply, _ = run_turn(text, speak=speak, source=source)
        print(f"{tag}>", reply)

    if args.screen is not None:
        if not get("vision.enabled", True):
            print("Enable vision.enabled in config.yaml", file=sys.stderr)
            return 1
        from skills.vision import run_screen_ask

        question = args.screen.strip() or input("Question about the screen: ").strip()
        run_screen_ask(
            question,
            mode=args.screen_mode,
            speak=speak or True,
        )
        return 0

    if args.tray_chat:
        from ui.tray import run_tray_chat_console

        run_tray_chat_console(speak=speak or get("voice.always_speak", False))
        return 0

    if args.tray:
        from ui.tray import run_tray

        run_tray(speak=speak or get("voice.always_speak", False), record_seconds=args.seconds)
        return 0

    if args.voice_loop:
        if not get("voice.stt.enabled", True):
            print("Enable voice.stt.enabled in config.yaml", file=sys.stderr)
            return 1
        from skills.stt import record_and_transcribe

        print("Voice loop — Ctrl+C to exit")
        try:
            while True:
                text = record_and_transcribe(seconds=args.seconds)
                if not text:
                    continue
                print(f"[you] {text}")
                reply, _ = run_turn(text, speak=speak or True, source="cli")
                print(f"{tag}>", reply)
        except KeyboardInterrupt:
            print()
        return 0

    if args.listen:
        if not get("voice.stt.enabled", True):
            print("Enable voice.stt.enabled in config.yaml", file=sys.stderr)
            return 1
        from skills.stt import record_and_transcribe

        text = record_and_transcribe(seconds=args.seconds)
        print(f"[you] {text}")
        handle(text)
        return 0

    if args.interactive:
        name = get("app.display_name", "Celestia")
        print(f"{name} interactive — mode: {security.armed_status_label()} (shared with tray)")
        sess = "on" if get("chat.session_enabled", True) else "off"
        cons = "on" if get("memory.session_consolidate", True) else "off"
        print(
            f"  Chat session: {sess} (newchat = clear). "
            f"Auto memory from chat: {cons}. Empty line to quit."
        )
        try:
            while True:
                line = input("you> ").strip()
                if not line:
                    _try_consolidate(end=True)
                    break
                low = line.lower()
                if low == "arm":
                    security.set_mode("armed")
                    print("[security] ARMED — full PC control")
                    continue
                if low == "disarm":
                    security.set_mode("safe")
                    print("[security] safe — PC control off")
                    continue
                if low == "scope" or low.startswith("scope "):
                    from celestia_core.scope import (
                        add_workspace,
                        format_status,
                        remove_workspace,
                    )

                    parts = line.split(maxsplit=2)
                    if len(parts) == 1:
                        print(format_status())
                    elif parts[1] in ("safe", "scoped", "armed"):
                        security.set_mode(parts[1])
                        print(f"[security] mode set to {parts[1]}")
                    elif parts[1] == "add" and len(parts) > 2:
                        print(add_workspace(parts[2]))
                    elif parts[1] == "remove" and len(parts) > 2:
                        print(remove_workspace(parts[2]))
                    else:
                        print("Usage: scope | scope scoped | scope add <path> | scope remove <path>")
                    continue
                if low == "status":
                    inj = get("memory.inject", "smart")
                    print(
                        f"[status] PC: {security.armed_status_label()} (shared) | memory: {inj} | "
                        f"personality: {get('personality.active', 'default')}"
                    )
                    continue
                if low == "memory":
                    from skills.memory.store import format_list

                    uid = get("app.user_id", "atlas_user")
                    print(format_list(uid))
                    continue
                if low == "forget" or low.startswith("forget "):
                    from skills.memory.store import clear_all, delete_matching

                    uid = get("app.user_id", "atlas_user")
                    rest = line[6:].strip() if low.startswith("forget ") else ""
                    if rest:
                        print(delete_matching(uid, rest))
                    else:
                        confirm = input("Clear ALL memories? type yes: ").strip().lower()
                        if confirm == "yes":
                            print(clear_all(uid))
                        else:
                            print("Cancelled.")
                    continue
                if low == "tray":
                    import subprocess

                    tray_py = ROOT / "run_celestia.py"
                    subprocess.Popen(
                        [sys.executable, str(tray_py), "--tray"],
                        cwd=str(ROOT),
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NEW_CONSOLE")
                        else 0,
                    )
                    print("[tray] Started in a new window (icon near the clock). This chat stays open.")
                    continue
                if low in ("newchat", "new chat", "clear chat"):
                    _try_consolidate(end=True)
                    chat_history = None
                    consolidate_from = 0
                    chat_turns = 0
                    print("[chat] New conversation — previous messages forgotten.")
                    continue
                if low == "help":
                    print_help(for_tray=False)
                    continue
                if low.startswith("read ") and len(line) > 5:
                    from skills.files.tools import file_read

                    fpath = line[5:].strip()
                    if "|" in fpath:
                        extra = fpath.split("|", 1)[1]
                        fpath = fpath.split("|", 1)[0].strip()
                        print(
                            f"[hint] read uses path only (ignored '|{extra}'). "
                            "For write: write path|content"
                        )
                    blocked = security.gate_pc_tool("file_read", {"path": fpath})
                    if blocked:
                        print(blocked)
                    else:
                        print(file_read(fpath))
                    continue
                if low.startswith("write ") and len(line) > 6:
                    from skills.files.tools import file_write

                    rest = line[6:].strip()
                    if "|" in rest:
                        fpath, _, content = rest.partition("|")
                        fpath, content = fpath.strip(), content
                        confirm = False
                    else:
                        fpath = rest
                        print("Paste content; empty line alone to finish:")
                        chunks = []
                        while True:
                            sub = input()
                            if sub == "" and chunks:
                                break
                            if sub == "" and not chunks:
                                continue
                            chunks.append(sub)
                        content = "\n".join(chunks)
                        confirm = (
                            input("Overwrite if exists? (yes/no): ").strip().lower() == "yes"
                        )
                    blocked = security.gate_pc_tool(
                        "file_write", {"path": fpath, "content": content}
                    )
                    if blocked:
                        print(blocked)
                    else:
                        print(file_write(fpath, content, confirm_overwrite=confirm))
                    continue
                if low in ("clip", "clipboard"):
                    from skills.clipboard.tools import clipboard_read

                    print(clipboard_read())
                    continue
                if low.startswith("clip set ") or low.startswith("clipboard set "):
                    from skills.clipboard.tools import clipboard_write

                    text = line[9:].strip() if low.startswith("clip set ") else line[14:].strip()
                    confirm = (
                        input("Confirm replace clipboard? (yes/no): ").strip().lower() == "yes"
                    )
                    blocked = security.gate_pc_tool(
                        "clipboard_write", {"text": text, "confirm_write": confirm}
                    )
                    print(blocked or clipboard_write(text, confirm_write=confirm))
                    continue
                from celestia_core.open_dispatch import dispatch_open_line

                opened = dispatch_open_line(line)
                if opened is not None:
                    print(opened)
                    continue
                if low == "listen" and get("voice.stt.enabled", True):
                    from skills.stt import record_and_transcribe

                    text = record_and_transcribe()
                    print(f"[you] {text}")
                    handle(text, source="repl")
                elif low == "screen" or low.startswith("screen "):
                    from skills.vision.flow import parse_screen_command, run_screen_ask

                    mode, q = parse_screen_command(line)
                    if not q:
                        q = input(
                            "Question (for CMD/text: Read every line of text exactly): "
                        ).strip()
                    if not q:
                        q = "Read every line of text in this image exactly."
                    print(run_screen_ask(q, mode=mode, speak=speak))
                else:
                    handle(line, source="repl")
                    chat_turns += 1
                    _try_consolidate()
        except (KeyboardInterrupt, EOFError):
            _try_consolidate(end=True)
            print()
        return 0

    if not args.message:
        parser.print_help()
        return 1

    handle(args.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
