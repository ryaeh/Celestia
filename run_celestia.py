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
from celestia_core import faillog

bootstrap()
faillog.setup()

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


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument("--tray", action="store_true", help="System tray + hotkeys (see config)")
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
        help='Arm PC control (use with a quoted message, e.g. --arm "open notepad")',
    )
    parser.add_argument("--disarm", action="store_true", help="Disarm PC control")
    parser.add_argument(
        "--trust-config",
        action="store_true",
        help="Record config.yaml + security.policy.yaml hashes (integrity baseline)",
    )
    parser.add_argument(
        "--pick-workspace",
        action="store_true",
        help="Print suggested security.workspaces paths for config.yaml",
    )
    parser.add_argument(
        "--settings",
        action="store_true",
        help="Open settings window (Tauri shell or tk fallback)",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Desktop shell — Tauri window + localhost Python API",
    )
    parser.add_argument(
        "--shell-server",
        action="store_true",
        help="Shell API only on 127.0.0.1 (for: cd shell && npm run tauri dev)",
    )
    parser.add_argument(
        "--logs",
        type=int,
        nargs="?",
        const=20,
        metavar="N",
        help="Show last N lines of tool audit log (default 20)",
    )
    parser.add_argument(
        "--graph",
        type=int,
        nargs="?",
        const=50,
        metavar="N",
        help="Inspect the knowledge graph: stats + last N current relations (Feature 10)",
    )
    parser.add_argument(
        "--graph-extract",
        action="store_true",
        help="Extract relations from the active chat into the knowledge graph now (Feature 10)",
    )
    return parser


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------

def _run_screen(args) -> int:
    if not get("vision.enabled", True):
        print("Enable vision.enabled in config.yaml", file=sys.stderr)
        return 1
    from skills.vision import run_screen_ask

    speak = args.speak or get("voice.always_speak", False)
    question = args.screen.strip() or input("Question about the screen: ").strip()
    run_screen_ask(question, mode=args.screen_mode, speak=speak or True)
    return 0


def _voice_reply(text: str, *, tag: str, speak: bool, source: str) -> None:
    """Print the transcript and emit the reply (session send or direct turn)."""
    print(f"[you] {text}")
    if get("chat.session_enabled", True):
        from celestia_core.shell_chat import send_message
        result = send_message(text, source="voice")
        print(f"{tag}>", result.get("reply", ""))
    else:
        reply, _ = run_turn(text, speak=speak, source=source)
        print(f"{tag}>", reply)


def _run_voice_loop(args) -> int:
    if not get("voice.stt.enabled", True):
        print("Enable voice.stt.enabled in config.yaml", file=sys.stderr)
        return 1
    from skills.stt import record_and_transcribe

    speak = args.speak or get("voice.always_speak", False)
    tag = _prompt_tag()
    print("Voice loop — Ctrl+C to exit")
    try:
        while True:
            text = record_and_transcribe(seconds=args.seconds)
            if not text:
                continue
            _voice_reply(text, tag=tag, speak=speak or True, source="cli")
    except KeyboardInterrupt:
        print()
    return 0


def _run_listen(args) -> int:
    if not get("voice.stt.enabled", True):
        print("Enable voice.stt.enabled in config.yaml", file=sys.stderr)
        return 1
    from skills.stt import record_and_transcribe

    speak = args.speak or get("voice.always_speak", False)
    tag = _prompt_tag()
    text = record_and_transcribe(seconds=args.seconds)
    _voice_reply(text, tag=tag, speak=speak, source="voice")
    return 0


def _run_interactive(args) -> int:
    speak = args.speak or get("voice.always_speak", False)
    tag = _prompt_tag()
    name = get("app.display_name", "Celestia")

    print(f"{name} interactive — mode: {security.armed_status_label()} (shared with tray)")
    sess = "on" if get("chat.session_enabled", True) else "off"
    mem_mode = "off"
    if get("memory.session_consolidate", True):
        mem_mode = get("memory.session_consolidate_mode", "auto")
    print(
        f"  Chat session: {sess} (newchat = clear). "
        f"Session→memory: {mem_mode} (auto-save in background). Empty line to quit."
    )

    chat_history: list | None = None
    chat_turns = 0
    consolidate_from = 0

    def _try_consolidate(*, end: bool = False) -> None:
        nonlocal chat_history, consolidate_from
        if not chat_history:
            return
        from skills.memory.session_consolidate import (
            consolidate_mode,
            consolidate_session_messages,
            should_run_consolidation,
        )
        if consolidate_mode() == "off" or not get("memory.session_consolidate", True):
            return
        if not should_run_consolidation(chat_history, start_index=consolidate_from, end=end):
            return
        if not end:
            every = int(get("memory.session_consolidate_every", 6))
            if chat_turns < every or chat_turns % every != 0:
                return
        uid = get("app.user_id", "atlas_user")
        consolidate_from, stored = consolidate_session_messages(
            chat_history, uid, start_index=consolidate_from,
        )
        if stored and get("memory.session_consolidate_verbose", False):
            for line in stored:
                print(f"[memory] saved: {line}")

    def handle(text: str, *, source: str = "cli") -> None:
        nonlocal chat_turns
        text = text.strip()
        if not text:
            return
        if get("chat.session_enabled", True):
            from celestia_core.shell_chat import send_message
            result = send_message(text, source=source)
            print(f"{tag}>", result.get("reply", ""))
            chat_turns += 1
            return
        reply, _ = run_turn(text, speak=speak, source=source)
        print(f"{tag}>", reply)

    def _end_session() -> None:
        if get("chat.session_enabled", True):
            from celestia_core.shell_chat import finalize_active_session
            finalize_active_session()
        else:
            _try_consolidate(end=True)
            try:
                from skills.memory.last_session import update_from_messages
                update_from_messages(chat_history)
            except Exception:
                pass

    try:
        while True:
            line = input("you> ").strip()
            if not line:
                _end_session()
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
                from celestia_core.scope import add_workspace, format_status, remove_workspace
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
                inj = get("memory.inject", "always_budgeted")
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
                if get("chat.session_enabled", True):
                    from celestia_core.shell_chat import create_session
                    create_session()
                    chat_turns = 0
                    print("[chat] New conversation (shared with shell/tray).")
                else:
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
                blocked = security.gate_pc_tool("file_write", {"path": fpath, "content": content})
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
                confirm = input("Confirm replace clipboard? (yes/no): ").strip().lower() == "yes"
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
                if not get("chat.session_enabled", True):
                    chat_turns += 1
                    _try_consolidate()
    except (KeyboardInterrupt, EOFError):
        _end_session()
        print()
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    load_config()
    security.bootstrap_security()

    parser = _build_parser()
    args = parser.parse_args()

    if args.trust_config:
        print(security.trust_config())
        return 0

    if args.pick_workspace:
        from celestia_core.scope import print_pick_workspace_hint
        print_pick_workspace_hint()
        return 0

    if args.settings:
        if get("ui.shell_settings", True):
            from celestia_core.shell_launch import launch_shell
            return launch_shell(route="settings")
        from celestia_core.ui.settings_app import run_settings
        run_settings()
        return 0

    if args.shell:
        from celestia_core.shell_launch import launch_shell
        return launch_shell(route="home")

    if args.shell_server:
        from celestia_core.shell_server import default_port, run_server_forever
        run_server_forever(default_port())
        return 0

    if args.logs is not None:
        from celestia_core.ui.settings_app import _tail_jsonl
        from celestia_core.config import ROOT
        rel = get("security.audit_log", "logs/tool_audit.jsonl")
        path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
        print(_tail_jsonl(path, int(args.logs)))
        return 0

    if args.graph is not None:
        from skills.memory import graph_store as graph
        s = graph.stats()
        print(f"[graph] {s['nodes']} nodes · {s['edges']} edges · {s['current_edges']} current")
        rels = graph.current_relations(int(args.graph))
        if rels:
            print("\nCurrent relations (newest first):")
            for line in rels:
                print(f"  • {line}")
        else:
            print("\n(no relations yet — enable memory.graph.enabled and have a chat)")
        return 0

    if args.graph_extract:
        from celestia_core import shell_chat
        from skills.memory.session_consolidate import _dialog_excerpt
        from skills.memory.graph_extract import extract_and_store
        from skills.memory import graph_store as graph

        if not get("memory.graph.enabled", False):
            print("[graph] memory.graph.enabled is false — enable it in config.yaml first.")
            return 1
        excerpt = _dialog_excerpt(shell_chat.get_history(), 0)
        if len(excerpt.strip()) < 30:
            # Active chat is empty (e.g. a new chat was just started) — fall back
            # to the most recently updated session that actually has content.
            for row in shell_chat.list_sessions():
                ex = _dialog_excerpt(shell_chat.get_history(row["id"]), 0)
                if len(ex.strip()) >= 30:
                    excerpt = ex
                    print(f"[graph] active chat is empty; using most recent chat: {row['title']!r}")
                    break
        if len(excerpt.strip()) < 30:
            print("[graph] no chat with enough content to extract from yet.")
            return 0
        print("[graph] extracting relations (one LLM pass)...")
        lines = extract_and_store(excerpt, source="manual")
        if lines:
            for ln in lines:
                print(f"  + {ln.removeprefix('[graph] ')}")
        else:
            print("  (model found no clear relations in this chat)")
        s = graph.stats()
        print(f"[graph] now {s['nodes']} nodes · {s['current_edges']} current relations")
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

    if args.screen is not None:
        return _run_screen(args)

    if args.tray_chat:
        from celestia_core.ui.tray import run_tray_chat_console
        run_tray_chat_console(speak=args.speak or get("voice.always_speak", False))
        return 0

    if args.tray:
        from celestia_core.ui.tray import run_tray
        run_tray(speak=args.speak or get("voice.always_speak", False), record_seconds=args.seconds)
        return 0

    if args.voice_loop:
        return _run_voice_loop(args)

    if args.listen:
        return _run_listen(args)

    if args.interactive:
        return _run_interactive(args)

    if not args.message:
        parser.print_help()
        return 1

    speak = args.speak or get("voice.always_speak", False)
    tag = _prompt_tag()
    if get("chat.session_enabled", True):
        from celestia_core.shell_chat import send_message
        result = send_message(args.message, source="cli")
        print(f"{tag}>", result.get("reply", ""))
    else:
        reply, _ = run_turn(args.message, speak=speak, source="cli")
        print(f"{tag}>", reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
