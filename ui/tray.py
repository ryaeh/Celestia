"""System tray + global hotkeys (voice + screen)."""

from __future__ import annotations

import re
import threading

from celestia_core.agent import run_turn
from celestia_core.cli_help import print_help
from celestia_core.config import get
from celestia_core import security

_OPEN_LINE = re.compile(r"^open\s+(.+)$", re.I)


def _hotkey_to_pynput(spec: str) -> str:
    mapping = {
        "ctrl": "<ctrl>",
        "control": "<ctrl>",
        "shift": "<shift>",
        "alt": "<alt>",
        "space": "<space>",
    }
    out = []
    for part in spec.split("+"):
        p = part.strip().lower()
        if p in mapping:
            out.append(mapping[p])
        elif len(p) == 1:
            out.append(p)
        else:
            raise ValueError(f"Unknown hotkey part: {part}")
    return "+".join(out)


def _mode_title(mode: str) -> str:
    return {"armed": "ARMED", "scoped": "Scoped", "safe": "Safe"}.get(mode, mode)


def _next_mode(mode: str) -> str:
    order = ("safe", "scoped", "armed")
    return order[(order.index(mode) + 1) % len(order)]


def _icon_colors(mode: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if mode == "armed":
        return (140, 40, 40), (255, 100, 100)
    if mode == "scoped":
        return (120, 90, 20), (255, 200, 60)
    return (20, 80, 140), (60, 160, 255)


class CelestiaTray:
    def __init__(self, *, speak: bool = True, record_seconds: float = 5.0):
        self.speak = speak
        self.record_seconds = record_seconds
        self._busy = threading.Lock()
        self._chat_running = False
        self._name = get("app.display_name", "Celestia")

    def _prompt_tag(self) -> str:
        return self._name.lower()

    def _on_voice_ptt(self):
        if not self._busy.acquire(blocking=False):
            print("[tray] busy — wait for current task")
            return
        try:
            from skills.stt import record_and_transcribe

            print("[ptt] listening...")
            text = record_and_transcribe(seconds=self.record_seconds)
            if text:
                print(f"[you] {text}")
                print(f"{self._prompt_tag()}>", run_turn(text, speak=self.speak, source="tray"))
        except Exception as e:
            print(f"[ptt] error: {e}")
        finally:
            self._busy.release()

    def _on_screen_ask(self):
        if not self._busy.acquire(blocking=False):
            print("[tray] busy — wait for current task")
            return
        try:
            from skills.vision.flow import run_screen_ask

            default = get("vision.default_mode", "region")
            print(f"[vision] mode: {default} (or type: screen fullscreen / screen window)")
            q = "Read every line of text in this image exactly."
            run_screen_ask(q, mode=default, speak=self.speak)
        except Exception as e:
            print(f"[vision] error: {e}")
        finally:
            self._busy.release()

    def _cycle_mode(self, icon) -> None:
        nxt = _next_mode(security.get_mode())
        security.set_mode(nxt)
        icon.icon = self._icon_image(nxt)
        icon.title = f"{self._name} — {_mode_title(nxt)}"
        print(f"[security] mode: {nxt} (tooltip + menu show this; icon letter: {nxt[0].upper()})")

    def _icon_image(self, mode: str):
        from PIL import Image, ImageDraw, ImageFont

        bg, fill = _icon_colors(mode)
        img = Image.new("RGB", (64, 64), color=bg)
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=fill)
        letter = {"safe": "S", "scoped": "C", "armed": "A"}.get(mode, "?")
        try:
            font = ImageFont.load_default()
            d.text((24, 22), letter, fill=(255, 255, 255), font=font)
        except Exception:
            pass
        return img

    def _dispatch_line(self, line: str) -> bool:
        """Handle one tray-console line. Return False to exit chat loop."""
        line = line.strip()
        if not line:
            return False
        low = line.lower()
        tag = self._prompt_tag()

        if low == "help":
            print_help(for_tray=True)
            return True
        if low == "arm":
            security.set_mode("armed")
            print("[security] ARMED")
            return True
        if low in ("disarm", "safe"):
            security.set_mode("safe")
            print("[security] safe")
            return True
        if low == "scope" or low.startswith("scope "):
            from celestia_core.scope import add_workspace, format_status, remove_workspace

            parts = line.split(maxsplit=2)
            if len(parts) == 1:
                print(format_status())
            elif parts[1] in ("safe", "scoped", "armed"):
                security.set_mode(parts[1])
                print(f"[security] mode: {parts[1]}")
            elif parts[1] == "add" and len(parts) > 2:
                print(add_workspace(parts[2]))
            elif parts[1] == "remove" and len(parts) > 2:
                print(remove_workspace(parts[2]))
            else:
                print("Usage: scope | scope scoped | scope add <path> | scope remove <path>")
            return True
        if low == "status":
            print(f"[status] {security.armed_status_label()} (shared)")
            return True
        if low == "screen" or low.startswith("screen "):
            from skills.vision.flow import parse_screen_command, run_screen_ask

            mode, q = parse_screen_command(line)
            if not q:
                q = input("Question about screen: ").strip()
            if not q:
                q = "Read every line of text in this image exactly."
            print(run_screen_ask(q, mode=mode, speak=self.speak))
            return True
        if low.startswith("read ") and len(line) > 5:
            from skills.files.tools import file_read

            fpath = line[5:].strip()
            blocked = security.gate_pc_tool("file_read", {"path": fpath})
            print(blocked or file_read(fpath))
            return True
        m_open = _OPEN_LINE.match(line)
        if m_open:
            from skills.pc_control.tools import execute_pc

            target = m_open.group(1).strip()
            blocked = security.gate_pc_tool("open_path", {"path": target})
            print(blocked or execute_pc("open_path", {"path": target}))
            return True

        print(f"{tag}>", run_turn(line, speak=self.speak, source="tray"))
        return True

    def _chat_loop(self):
        if self._chat_running:
            print("[tray] chat already running in this window")
            return
        self._chat_running = True
        try:
            mode = security.get_mode()
            print(
                f"\n[tray] Chat — mode: {mode}. Empty line to leave. Type help for commands.\n"
            )
            while True:
                try:
                    line = input("you> ")
                except (EOFError, KeyboardInterrupt):
                    break
                if not self._dispatch_line(line):
                    print("[tray] chat ended — use menu Chat again or Voice PTT")
                    break
        finally:
            self._chat_running = False

    def _start_hotkey_listeners(self):
        from pynput import keyboard

        hotkeys: list = []

        if get("voice.stt.enabled", True):
            combo = _hotkey_to_pynput(get("voice.push_to_talk_hotkey", "ctrl+alt+v"))
            hotkeys.append(
                (
                    combo,
                    lambda: threading.Thread(target=self._on_voice_ptt, daemon=True).start(),
                )
            )

        if get("vision.enabled", False):
            combo = _hotkey_to_pynput(get("vision.hotkey", "ctrl+shift+s"))
            hotkeys.append(
                (
                    combo,
                    lambda: threading.Thread(target=self._on_screen_ask, daemon=True).start(),
                )
            )

        if not hotkeys:
            return

        parsed = [
            (keyboard.HotKey(keyboard.HotKey.parse(c), act), c) for c, act in hotkeys
        ]
        holder: list = []

        def on_press(key):
            for hk, _ in parsed:
                hk.press(holder[0].canonical(key))

        def on_release(key):
            for hk, _ in parsed:
                hk.release(holder[0].canonical(key))

        holder.append(keyboard.Listener(on_press=on_press, on_release=on_release))
        holder[0].daemon = True
        holder[0].start()
        for _, combo in parsed:
            print(f"[tray] hotkey: {combo}")

    def run(self):
        import pystray

        mode = security.get_mode()
        nxt = _next_mode(mode)

        def on_voice(_icon, _item):
            threading.Thread(target=self._on_voice_ptt, daemon=True).start()

        def on_screen(_icon, _item):
            threading.Thread(target=self._on_screen_ask, daemon=True).start()

        def on_cycle(icon, _item):
            self._cycle_mode(icon)

        def on_chat(_icon, _item):
            threading.Thread(target=self._chat_loop, daemon=True).start()

        def on_help(_icon, _item):
            print_help(for_tray=True)

        def on_quit(icon, _item):
            icon.stop()

        sec_label = f"Security: {_mode_title(mode)} -> {_mode_title(nxt)}"
        items = [
            pystray.MenuItem(sec_label, on_cycle),
            pystray.MenuItem("Chat (multi-turn)", on_chat),
            pystray.MenuItem("Help", on_help),
            pystray.MenuItem("Voice (PTT)", on_voice),
        ]
        if get("vision.enabled", False):
            items.append(pystray.MenuItem("Screen ask", on_screen))
        items.append(pystray.MenuItem("Quit", on_quit))

        icon = pystray.Icon(
            "Celestia",
            self._icon_image(mode),
            f"{self._name} — {_mode_title(mode)} (S=safe C=scoped A=armed)",
            pystray.Menu(*items),
        )
        self._start_hotkey_listeners()
        print(f"[tray] {self._name} — mode {mode}. Tooltip on icon shows mode. Menu: Chat = multi-turn.")
        print("[tray] Type help in Chat or see -i interactive mode.")
        icon.run()


def run_tray(*, speak: bool = True, record_seconds: float = 5.0) -> None:
    CelestiaTray(speak=speak, record_seconds=record_seconds).run()
