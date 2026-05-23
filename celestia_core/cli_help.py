"""Interactive / tray command help text."""

from __future__ import annotations

from celestia_core.config import get


def print_help(*, for_tray: bool = False) -> None:
    voice = get("voice.stt.enabled", True)
    vision = get("vision.enabled", True)
    ptt = get("voice.push_to_talk_hotkey", "ctrl+alt+v")
    vhot = get("vision.hotkey", "ctrl+shift+s")

    lines = [
        "",
        "=== Celestia commands ===",
        "",
        "Chat",
        "  <message>          Talk to Celestia (any text not matching a command below)",
        "  newchat            Clear in-session chat history (-i only)",
        "",
        "Security (shared with tray + voice)",
        "  arm                Full PC control (PowerShell, any app, URLs)",
        "  disarm             Same as: scope safe",
        "  status             Mode, memory inject, personality",
        "",
        "  scope              Show mode, workspaces, app allowlist",
        "  scope safe         PC control off — chat/voice/vision only",
        "  scope scoped       Allowlisted apps + read/write files in workspaces",
        "  scope armed        Same as: arm",
        "  scope add <path>   Allow reading/opening files under this folder",
        "  scope remove <path>  Remove folder from runtime workspace list",
        "",
        "Open apps (direct — no AI)",
        "  open <name>        Launch app if mode allows (e.g. open notepad, open calc)",
        "",
        "Files",
        "  read <path>        Read a text file (path only — no | pipe)",
        "  write <path>       Write file (paste lines; or write path|content)",
        "  write path|text    One-line write (pipe separates path and content)",
        "",
        "Clipboard",
        "  clip / clipboard   Read clipboard text",
        "  clip set <text>    Copy text to clipboard (confirm if replacing)",
        "",
        "Memory",
        "  memory             List stored facts",
        "  forget             Clear ALL memories (asks yes/no)",
        "  forget <text>      Delete memories containing <text>",
        "",
    ]

    if voice:
        lines += [
            "Voice",
            "  listen             Record ~5s, reply in chat",
            "",
        ]
    if vision:
        default_mode = get("vision.default_mode", "region")
        lines += [
            "Screen (confirm before send — crop tight for text/CMD)",
            f"  screen                    Use config default mode ({default_mode})",
            "  screen <question>         Default mode + question on one line",
            "  screen region [question]  Drag a rectangle (Esc = cancel)",
            "  screen fullscreen [q]     Whole desktop",
            "  screen window [q]         Active window only (alias: active_window)",
            "",
            "  CLI:",
            "  --screen \"question\"",
            "  --screen-mode region|fullscreen|active_window",
            "",
        ]

    lines += [
        "Other",
        "  help               This list",
        "  tray               Start tray + hotkeys in another window",
        "  settings           Open settings UI (--settings from CLI)",
        "  logs               Tool audit tail (--logs N from CLI)",
        "  (empty line)       Quit interactive mode",
        "",
    ]

    if for_tray:
        lines += [
            "Tray (separate window: run_celestia.py --tray)",
            f"  Menu: Security — cycles safe -> scoped -> armed (tooltip on icon shows mode)",
            "  Menu: Chat — opens a NEW console window for you> prompts",
            "  Menu: Voice (PTT)  One voice question per use",
            f"  Hotkey voice: {ptt}",
        ]
        if vision:
            dm = get("vision.default_mode", "region")
            lines.append(f"  Hotkey screen: {vhot} (uses config default: {dm})")
            lines.append("  Menu: Screen (region / fullscreen / active window)")
        lines.append("  Note: Windows often hides tray icon colors — read the tooltip or menu label.")
        lines.append("")

    print("\n".join(lines))
