import { useCallback, useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Celestia theme system
// Each theme id maps to a `[data-theme="<id>"]` block in App.css that overrides
// the palette tokens. We only store the id; the CSS does the rest. The swatch
// drives the picker preview: a hard two-tone split of ground | accent.
// ---------------------------------------------------------------------------

export type ThemeId =
  | "aurora"
  | "twilight"
  | "ember"
  | "slate"
  | "moss"
  | "daylight";

export type ThemeMeta = {
  id: ThemeId;
  label: string;
  tone: "dark" | "light";
  /** [ground, accent, moon] — the picker chip shows ground | accent. */
  swatch: [string, string, string];
  hint: string;
};

export const THEMES: ThemeMeta[] = [
  { id: "aurora",   label: "Aurora",   tone: "dark",  swatch: ["#151a1e", "#7fd1b9", "#f0d78c"], hint: "Night sky & aurora" },
  { id: "twilight", label: "Twilight", tone: "dark",  swatch: ["#17161f", "#a9b8f5", "#f0d9a0"], hint: "Dusk blue & starlight" },
  { id: "ember",    label: "Ember",    tone: "dark",  swatch: ["#1c1512", "#f0a868", "#f3d59c"], hint: "Hearth & amber" },
  { id: "slate",    label: "Slate",    tone: "dark",  swatch: ["#181b1f", "#9fbad8", "#d6ccb6"], hint: "Graphite & steel" },
  { id: "moss",     label: "Moss",     tone: "dark",  swatch: ["#151a13", "#a8cf8f", "#e2d48e"], hint: "Forest & sage" },
  { id: "daylight", label: "Daylight", tone: "light", swatch: ["#fbf9f5", "#2f6b5a", "#9a6c17"], hint: "Paper & pine" },
];

export const DEFAULT_THEME: ThemeId = "aurora";

const STORAGE_KEY = "celestia.shell.theme";

function isThemeId(v: string | null): v is ThemeId {
  return !!v && THEMES.some((t) => t.id === v);
}

export function getStoredTheme(): ThemeId {
  if (typeof window === "undefined") return DEFAULT_THEME;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isThemeId(stored)) return stored;
  } catch {
    /* ignore */
  }
  return DEFAULT_THEME;
}

/** Apply a theme to <html> and persist it. Safe to call before React mounts. */
export function applyTheme(id: ThemeId): void {
  if (typeof document !== "undefined") {
    const meta = THEMES.find((t) => t.id === id);
    document.documentElement.dataset.theme = id;
    document.documentElement.style.colorScheme = meta?.tone ?? "dark";
  }
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

/** Read the stored theme and apply it immediately (call once at startup). */
export function initTheme(): ThemeId {
  const id = getStoredTheme();
  applyTheme(id);
  return id;
}

export function useTheme(): [ThemeId, (id: ThemeId) => void] {
  const [theme, setThemeState] = useState<ThemeId>(getStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((id: ThemeId) => setThemeState(id), []);
  return [theme, setTheme];
}
