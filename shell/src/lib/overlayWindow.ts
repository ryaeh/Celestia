// ---------------------------------------------------------------------------
// Companion overlay bubble — Tauri window plumbing.
//
// The bubble is a second window (label "overlay", `?view=overlay`) declared in
// tauri.conf.json: frameless, transparent, always-on-top, hidden at start. These
// helpers are the only place that touches the Tauri window API for it, and all
// of them no-op outside Tauri (plain `vite` in a browser) so the shell still
// runs there.
// ---------------------------------------------------------------------------

import {
  LogicalSize,
  PhysicalPosition,
  Window,
  currentMonitor,
  getCurrentWindow,
} from "@tauri-apps/api/window";

export const OVERLAY_LABEL = "overlay";
const MAIN_LABEL = "main";

/** Logical sizes: the collapsed orb, and the expanded mini-chat card. */
export const COLLAPSED = { w: 88, h: 88 };
export const EXPANDED = { w: 340, h: 470 };

const POS_KEY = "celestia.overlay.pos";
const EDGE_MARGIN = 24; // physical px from the work-area edge for the default spot

export function inTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function isOverlayView(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("view") === "overlay";
}

async function byLabel(label: string): Promise<Window | null> {
  if (!inTauri()) return null;
  try {
    return await Window.getByLabel(label);
  } catch {
    return null;
  }
}

// ── From the main window ────────────────────────────────────────────────────

/** Show/hide the bubble (header button). Returns the new visibility. */
export async function toggleOverlay(): Promise<boolean> {
  const w = await byLabel(OVERLAY_LABEL);
  if (!w) return false;
  if (await w.isVisible()) {
    await w.hide();
    return false;
  }
  await w.show();
  return true;
}

/**
 * Closing the main window while the bubble is showing keeps Celestia alive in
 * the bubble (main just hides; "open full window" brings it back). With the
 * bubble hidden, close means quit — so destroy the hidden overlay too, or the
 * app would linger with no visible window.
 */
export async function installMainCloseHandler(): Promise<() => void> {
  if (!inTauri()) return () => {};
  const main = getCurrentWindow();
  const unlisten = await main.onCloseRequested(async (event) => {
    const overlay = await byLabel(OVERLAY_LABEL);
    if (overlay && (await overlay.isVisible())) {
      event.preventDefault();
      await main.hide();
      return;
    }
    try {
      await overlay?.destroy();
    } catch {
      /* already gone */
    }
  });
  return unlisten;
}

// ── From the overlay window ─────────────────────────────────────────────────

export async function showMainWindow(): Promise<void> {
  const main = await byLabel(MAIN_LABEL);
  if (!main) return;
  await main.show();
  await main.unminimize();
  await main.setFocus();
}

/** Hide the bubble. If the main window is hidden too, surface it instead of
 *  leaving Celestia running with nothing on screen. */
export async function hideOverlaySelf(): Promise<void> {
  if (!inTauri()) return;
  const main = await byLabel(MAIN_LABEL);
  if (main && !(await main.isVisible())) {
    await showMainWindow();
  }
  await getCurrentWindow().hide();
}

export async function setOverlayVisible(visible: boolean): Promise<void> {
  if (!inTauri()) return;
  const self = getCurrentWindow();
  if (visible) await self.show();
  else await hideOverlaySelf();
}

export async function isOverlayVisible(): Promise<boolean> {
  if (!inTauri()) return true;
  return getCurrentWindow().isVisible();
}

type SavedPos = { x: number; y: number };

function loadPos(): SavedPos | null {
  try {
    const raw = localStorage.getItem(POS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as SavedPos;
    return Number.isFinite(p.x) && Number.isFinite(p.y) ? p : null;
  } catch {
    return null;
  }
}

function savePos(p: SavedPos): void {
  try {
    localStorage.setItem(POS_KEY, JSON.stringify(p));
  } catch {
    /* ignore */
  }
}

/** Clamp a physical top-left so a w×h (physical) window stays in the work area. */
function clampToWorkArea(
  x: number,
  y: number,
  w: number,
  h: number,
  area: { position: { x: number; y: number }; size: { width: number; height: number } },
): SavedPos {
  const minX = area.position.x;
  const minY = area.position.y;
  const maxX = area.position.x + area.size.width - w;
  const maxY = area.position.y + area.size.height - h;
  return {
    x: Math.round(Math.min(Math.max(x, minX), Math.max(minX, maxX))),
    y: Math.round(Math.min(Math.max(y, minY), Math.max(minY, maxY))),
  };
}

/** Put the collapsed bubble where the user last left it (or bottom-right). */
export async function placeCollapsed(): Promise<void> {
  if (!inTauri()) return;
  const self = getCurrentWindow();
  await self.setSize(new LogicalSize(COLLAPSED.w, COLLAPSED.h));
  const mon = await currentMonitor();
  if (!mon) return;
  const s = mon.scaleFactor;
  const w = COLLAPSED.w * s;
  const h = COLLAPSED.h * s;
  const saved = loadPos();
  const area = mon.workArea;
  const target = saved
    ? clampToWorkArea(saved.x, saved.y, w, h, area)
    : clampToWorkArea(
        area.position.x + area.size.width - w - EDGE_MARGIN,
        area.position.y + area.size.height - h - EDGE_MARGIN,
        w,
        h,
        area,
      );
  await self.setPosition(new PhysicalPosition(target.x, target.y));
}

/** Remember where the user drags the collapsed bubble. */
export async function trackCollapsedPosition(isCollapsed: () => boolean): Promise<() => void> {
  if (!inTauri()) return () => {};
  return getCurrentWindow().onMoved(({ payload }) => {
    if (isCollapsed()) savePos({ x: payload.x, y: payload.y });
  });
}

/**
 * Grow into the mini-chat card, keeping the bubble's corner nearest the screen
 * edge anchored (a bubble parked bottom-right opens up-and-left), clamped to
 * the work area.
 */
export async function expandFromBubble(): Promise<void> {
  if (!inTauri()) return;
  const self = getCurrentWindow();
  const mon = await currentMonitor();
  const pos = await self.outerPosition();
  if (mon) {
    const s = mon.scaleFactor;
    const cw = COLLAPSED.w * s;
    const ch = COLLAPSED.h * s;
    const ew = EXPANDED.w * s;
    const eh = EXPANDED.h * s;
    const area = mon.workArea;
    const centerX = area.position.x + area.size.width / 2;
    const centerY = area.position.y + area.size.height / 2;
    const x = pos.x + cw / 2 > centerX ? pos.x + cw - ew : pos.x;
    const y = pos.y + ch / 2 > centerY ? pos.y + ch - eh : pos.y;
    const t = clampToWorkArea(x, y, ew, eh, area);
    await self.setPosition(new PhysicalPosition(t.x, t.y));
  }
  await self.setSize(new LogicalSize(EXPANDED.w, EXPANDED.h));
  await self.setFocus();
}

export async function startDrag(): Promise<void> {
  if (!inTauri()) return;
  await getCurrentWindow().startDragging();
}
