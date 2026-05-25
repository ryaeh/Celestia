"""Minimal settings UI (Phase 4 spike) — mode, workspaces, audit tail."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from celestia_core.config import ROOT, get, load_config
from celestia_core import security
from celestia_core.scope import format_status, list_workspaces


def _tail_jsonl(path: Path, n: int = 20) -> str:
    if not path.is_file():
        return f"(no file: {path})"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-n:]
    out = []
    for line in tail:
        try:
            row = json.loads(line)
            out.append(
                f"{row.get('ts', '?')} [{row.get('tool') or row.get('event', '?')}] "
                f"{row.get('result') or row.get('mode', '')} {row.get('summary', '')[:60]}"
            )
        except json.JSONDecodeError:
            out.append(line[:120])
    return "\n".join(out) if out else "(empty log)"


class SettingsApp:
    def __init__(self) -> None:
        load_config()
        self.root = tk.Tk()
        self.root.title(f"{get('app.display_name', 'Celestia')} Settings")
        self.root.geometry("720x520")

        mode_frame = ttk.LabelFrame(self.root, text="Security mode")
        mode_frame.pack(fill="x", padx=8, pady=6)
        for label, mode in (("Safe", "safe"), ("Scoped", "scoped"), ("Armed", "armed")):
            ttk.Button(
                mode_frame,
                text=label,
                command=lambda m=mode: self._set_mode(m),
            ).pack(side="left", padx=4, pady=4)

        self.status_var = tk.StringVar(value=security.armed_status_label())
        ttk.Label(mode_frame, textvariable=self.status_var).pack(side="left", padx=12)

        ws_frame = ttk.LabelFrame(self.root, text="Workspaces")
        ws_frame.pack(fill="both", expand=False, padx=8, pady=4)
        self.ws_list = tk.Listbox(ws_frame, height=5)
        self.ws_list.pack(fill="x", padx=4, pady=4)
        self._refresh_workspaces()

        log_frame = ttk.LabelFrame(self.root, text="Recent tool audit (last 20)")
        log_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)
        self._refresh_log()

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=8, pady=6)
        ttk.Button(btn_frame, text="Refresh logs", command=self._refresh_log).pack(side="left")
        ttk.Button(btn_frame, text="Scope details", command=self._show_scope).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Close", command=self.root.destroy).pack(side="right")

    def _set_mode(self, mode: str) -> None:
        security.set_mode(mode)
        self.status_var.set(security.armed_status_label())
        messagebox.showinfo("Celestia", f"Mode set to {mode}")

    def _refresh_workspaces(self) -> None:
        self.ws_list.delete(0, tk.END)
        for p in list_workspaces():
            self.ws_list.insert(tk.END, str(p))

    def _refresh_log(self) -> None:
        rel = get("security.audit_log", "logs/tool_audit.jsonl")
        path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
        text = _tail_jsonl(path)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, text)
        self.log_text.configure(state="disabled")

    def _show_scope(self) -> None:
        messagebox.showinfo("Scope", format_status())

    def run(self) -> None:
        self.root.mainloop()


def run_settings() -> None:
    SettingsApp().run()
