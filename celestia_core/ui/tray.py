"""System tray + global hotkeys (voice + screen)."""

from __future__ import annotations

import re
import threading

from celestia_core.cli_help import print_help
from celestia_core.config import get, load_config
from celestia_core import security
from celestia_core.shell_chat import send_message

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

    def _session_chat(self, text: str, *, source: str) -> str:
        """Send to the shared shell session store (CC-5)."""
        result = send_message(text, source=source)
        if "error" in result:
            raise RuntimeError(result["error"])
        return str(result.get("reply") or "")

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
                reply = self._session_chat(text, source="voice")
                print(f"{self._prompt_tag()}>", reply)
        except Exception as e:
            print(f"[ptt] error: {e}")
        finally:
            self._busy.release()

    def _on_screen_ask(self, mode: str | None = None):
        if not self._busy.acquire(blocking=False):
            print("[tray] busy — wait for current task")
            return
        try:
            from skills.vision.flow import run_screen_ask

            use_mode = mode or get("vision.default_mode", "region")
            q = "Read every line of text in this image exactly."
            run_screen_ask(q, mode=use_mode, speak=self.speak)
        except Exception as e:
            print(f"[vision] error: {e}")
        finally:
            self._busy.release()

    def _apply_mode(self, mode: str, icon=None) -> None:
        warn = security.set_mode(mode, source="tray")
        if warn:
            print(warn)
        effective = security.get_mode()
        if icon is not None:
            icon.icon = self._icon_image(effective)
            icon.title = f"{self._name} — {_mode_title(effective)}"
        letter = {"safe": "S", "scoped": "C", "armed": "A"}.get(effective, "?")
        print(
            f"[security] mode: {effective} "
            f"(tooltip + menu; icon letter: {letter})"
        )

    def _cycle_mode(self, icon) -> None:
        nxt = security.next_mode_cycled(
            security.get_mode(), max_mode=security.get_tray_max_mode()
        )
        self._apply_mode(nxt, icon)

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
            self._apply_mode("armed")
            return True
        if low in ("disarm", "safe"):
            self._apply_mode("safe")
            return True
        if low == "scope" or low.startswith("scope "):
            from celestia_core.scope import add_workspace, format_status, remove_workspace

            parts = line.split(maxsplit=2)
            if len(parts) == 1:
                print(format_status())
            elif parts[1] in ("safe", "scoped", "armed"):
                self._apply_mode(parts[1])
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
        if low.startswith("write ") and len(line) > 6:
            from skills.files.tools import file_write

            rest = line[6:].strip()
            if "|" in rest:
                fpath, _, content = rest.partition("|")
                confirm = True
            else:
                print("[tray] use: write path|content on one line")
                return True
            blocked = security.gate_pc_tool(
                "file_write", {"path": fpath.strip(), "content": content}
            )
            print(
                blocked
                or file_write(fpath.strip(), content, confirm_overwrite=confirm)
            )
            return True
        if low in ("clip", "clipboard"):
            from skills.clipboard.tools import clipboard_read

            print(clipboard_read())
            return True
        from celestia_core.open_dispatch import dispatch_open_line

        opened = dispatch_open_line(line)
        if opened is not None:
            print(opened)
            return True

        try:
            reply = self._session_chat(line, source="tray")
        except Exception as e:
            print(f"[tray] chat error: {e}")
            return True
        print(f"{tag}>", reply)
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
        nxt = security.next_mode_cycled(mode, max_mode=security.get_tray_max_mode())

        def on_voice(_icon, _item):
            threading.Thread(target=self._on_voice_ptt, daemon=True).start()

        def on_screen_region(_icon, _item):
            threading.Thread(
                target=lambda: self._on_screen_ask("region"), daemon=True
            ).start()

        def on_screen_full(_icon, _item):
            threading.Thread(
                target=lambda: self._on_screen_ask("fullscreen"), daemon=True
            ).start()

        def on_screen_window(_icon, _item):
            threading.Thread(
                target=lambda: self._on_screen_ask("active_window"), daemon=True
            ).start()

        def on_cycle(icon, _item):
            self._cycle_mode(icon)

        def on_chat(_icon, _item):
            load_config()
            if get("ui.shell_settings", True):
                from celestia_core.shell_launch import open_shell_chat

                open_shell_chat()
                return
            threading.Thread(
                target=self._chat_loop,
                daemon=True,
                name="celestia-tray-chat",
            ).start()
            print("[tray] Chat thread started (shared session file; enable shell for the app UI).")

        def on_help(_icon, _item):
            print_help(for_tray=True)

        def on_quit(icon, _item):
            icon.stop()

        sec_label = f"Security: {_mode_title(mode)} -> {_mode_title(nxt)}"
        items = [
            pystray.MenuItem(sec_label, on_cycle),
            pystray.MenuItem(
                "Chat" if get("ui.shell_settings", True) else "Chat (console)",
                on_chat,
            ),
            pystray.MenuItem("Help", on_help),
            pystray.MenuItem("Voice (PTT)", on_voice),
        ]
        if get("vision.enabled", False):
            items.extend(
                [
                    pystray.MenuItem("Screen (region)", on_screen_region),
                    pystray.MenuItem("Screen (fullscreen)", on_screen_full),
                    pystray.MenuItem("Screen (active window)", on_screen_window),
                ]
            )
        items.append(pystray.MenuItem("Quit", on_quit))

        icon = pystray.Icon(
            "Celestia",
            self._icon_image(mode),
            f"{self._name} — {_mode_title(mode)} (S=safe C=scoped A=armed)",
            pystray.Menu(*items),
        )
        self._start_hotkey_listeners()
        print(f"[tray] {self._name} — mode {mode}. Right-click icon near the clock.")
        if get("ui.shell_settings", True):
            print("[tray] Chat opens the desktop shell (same history as voice PTT).")
        else:
            print("[tray] Chat runs in a background thread here (set ui.shell_settings: true for the app).")
        print("[tray] Screen: menu items or vision hotkey when enabled.")
        icon.run()


def run_tray_chat_console(*, speak: bool = False) -> None:
    """Foreground chat console (used by --tray-chat in its own window)."""
    CelestiaTray(speak=speak)._chat_loop()


def run_tray(*, speak: bool = True, record_seconds: float = 5.0) -> None:
    CelestiaTray(speak=speak, record_seconds=record_seconds).run()
