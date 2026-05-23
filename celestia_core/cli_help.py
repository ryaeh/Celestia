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
        "",
        "Security (shared with tray + voice)",
        "  arm                Full PC control (PowerShell, any app, URLs)",
        "  disarm             Same as: scope safe",
        "  status             Mode, memory inject, personality",
        "",
        "  scope              Show mode, workspaces, app allowlist",
        "  scope safe         PC control off — chat/voice/vision only",
        "  scope scoped       Allowlisted apps (notepad, calc, …) + file_read in workspaces",
        "  scope armed        Same as: arm",
        "  scope add <path>   Allow reading/opening files under this folder",
        "  scope remove <path>  Remove folder from runtime workspace list",
        "",
        "Open apps (direct — no AI)",
        "  open <name>        Launch app if mode allows (e.g. open notepad, open calc)",
        "",
        "Files",
        "  read <path>        Read a text file (scoped: workspace only; armed: most paths)",
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
        "  (empty line)       Quit interactive mode",
        "",
    ]

    if for_tray:
        lines += [
            "Tray (separate window)",
            f"  Menu: Security — cycles safe -> scoped -> armed (tooltip on icon shows mode)",
            f"  Menu: Chat — multi-turn chat in the tray console (not one message only)",
            "  Menu: Voice (PTT)  One voice question per use",
            f"  Hotkey voice: {ptt}",
        ]
        if vision:
            dm = get("vision.default_mode", "region")
            lines.append(f"  Hotkey screen: {vhot} (uses config default: {dm})")
            lines.append("  Menu: Screen ask — region capture + default question")
        lines.append("  Note: Windows often hides tray icon colors — read the tooltip or menu label.")
        lines.append("")

    print("\n".join(lines))
